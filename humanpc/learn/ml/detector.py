"""Measure humanness: can a detector tell your real movement from generated?

For each real movement the model generates one of its own under the same
condition (same start, target, size, scroll amount, person). A bidirectional
GRU classifier is trained on part of the pairs and tested on the rest (3-fold).

    humanness = 2 * (1 - detector accuracy)      # 100% = coin flip, 0% = always caught

Per-kind accuracies also update ``task_weights.json`` so the trainer asks for
more of the movements that get caught most.
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from ..dataset import WEIGHTS_FILE
from ..tasks import DEFAULT_WEIGHTS
from .generate import generate
from .model import load
from .segments import BIN_MS, COND_DIM, IN_DIM, load_all, pack

# generator kinds -> trainer task kinds they come from
TRAINER_KINDS = {"aim": ("point", "chain"), "aim_double": ("double",), "aim_right": ("right",),
                 "drag": ("drag",), "scroll": ("scroll",), "scroll_click": ("scroll_click",), "idle": ("read",)}


class Detector(nn.Module):
    def __init__(self, hidden: int = 64):
        super().__init__()
        self.gru = nn.GRU(IN_DIM + COND_DIM, hidden, batch_first=True, bidirectional=True)
        self.out = nn.Sequential(nn.Linear(4 * hidden, hidden), nn.GELU(), nn.Linear(hidden, 1))

    def forward(self, x, mask):
        h, _ = self.gru(x)
        m = mask[..., None]
        mean = (h * m).sum(1) / m.sum(1).clamp_min(1)
        mx = h.masked_fill(m == 0, -1e4).max(1).values
        return self.out(torch.cat([mean, mx], -1)).squeeze(-1)


def _tensor(items, device):
    t = max(len(a["inputs"]) for a in items)
    x = np.zeros((len(items), t, IN_DIM + COND_DIM), np.float32)
    mask = np.zeros((len(items), t), np.float32)
    for i, a in enumerate(items):
        n = len(a["inputs"])
        x[i, :n, :IN_DIM] = a["inputs"]
        x[i, :n, IN_DIM:] = a["cond"]
        mask[i, :n] = 1
    return torch.from_numpy(x).to(device), torch.from_numpy(mask).to(device)


def _fit_and_score(train, test, device, epochs=25, seed=0):
    torch.manual_seed(seed)
    det = Detector().to(device)
    opt = torch.optim.AdamW(det.parameters(), lr=2e-3, weight_decay=1e-3)
    lossf = nn.BCEWithLogitsLoss()
    rng = random.Random(seed)
    for _ in range(epochs):
        rng.shuffle(train)
        for i in range(0, len(train), 32):
            chunk = train[i:i + 32]
            x, m = _tensor([a for a, _ in chunk], device)
            y = torch.tensor([lab for _, lab in chunk], dtype=torch.float32, device=device)
            opt.zero_grad()
            lossf(det(x, m), y).backward()
            opt.step()
    det.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(test), 64):
            chunk = test[i:i + 64]
            x, m = _tensor([a for a, _ in chunk], device)
            preds += (det(x, m) > 0).long().tolist()
    return [int(p == lab) for p, (_, lab) in zip(preds, test)]


def _path_stats(dx, dy, click) -> dict:
    step = np.hypot(dx, dy)
    path = step.sum()
    end = float(np.hypot(dx.sum(), dy.sum()))
    return {"duration_ms": len(dx) * BIN_MS, "straightness": end / path if path > 0 else 1.0,
            "peak_speed": float(step.max() / BIN_MS) if len(step) else 0.0,
            "clicks": int((click > 0).sum())}


def evaluate(data_dir: Path, model_path: Path | None = None, *, max_pairs: int = 600,
             temperature: float = 1.0, folds: int = 3, cpu: bool = False, write_weights: bool = True,
             max_sessions: int | None = None, log=print) -> dict:
    data_dir = Path(data_dir)
    model_path = Path(model_path) if model_path else data_dir / "model" / "model.pt"
    device = torch.device("cuda" if torch.cuda.is_available() and not cpu else "cpu")
    model, ck = load(model_path, device)
    people = ck.get("people", ["me"])
    pid = {p: i for i, p in enumerate(people)}

    from .train import is_val
    segs = load_all(data_dir, max_sessions=max_sessions)
    held_out = [s for s in segs if is_val(s)]
    if len(held_out) >= 100:  # score only movements the model never trained on
        segs = held_out
    random.Random(0).shuffle(segs)
    segs = segs[:max_pairs]
    log(f"generating {len(segs)} movements to compare against your real ones...")
    fakes = []
    for i in range(0, len(segs), 128):
        chunk = segs[i:i + 128]
        jobs = [(replace(s, arrays={}), s.start) for s in chunk]
        fakes += generate(model, jobs, [pid.get(s.person, 0) for s in chunk], device=device,
                          temperature=temperature)
    pairs = []
    for s, g in zip(segs, fakes):
        if len(g["dx"]) >= 1:
            pairs.append((s, s.arrays, pack(s, s.start, g["dx"], g["dy"], g["click"], g["wheel"]), g))

    # k-fold: both halves of a pair always land on the same side
    correct, kinds = [], []
    for f in range(folds):
        test_idx = [i for i in range(len(pairs)) if i % folds == f]
        train_idx = [i for i in range(len(pairs)) if i % folds != f]
        train = [(pairs[i][1], 1) for i in train_idx] + [(pairs[i][2], 0) for i in train_idx]
        test = [(pairs[i][1], 1) for i in test_idx] + [(pairs[i][2], 0) for i in test_idx]
        correct += _fit_and_score(train, test, device, seed=f)
        kinds += [pairs[i][0].kind for i in test_idx] * 2
    acc = float(np.mean(correct)) if correct else 1.0
    by_kind = {}
    for k in sorted(set(kinds)):
        c = [ok for ok, kk in zip(correct, kinds) if kk == k]
        by_kind[k] = {"accuracy": round(float(np.mean(c)), 3), "n": len(c) // 2}

    real_stats = [_path_stats(p[1]["dxdy"][:, 0] * 10, p[1]["dxdy"][:, 1] * 10, p[1]["click"]) for p in pairs]
    fake_stats = [_path_stats(p[3]["dx"], p[3]["dy"], p[3]["click"]) for p in pairs]
    compare = {k: {"real": round(float(np.median([r[k] for r in real_stats])), 3),
                   "generated": round(float(np.median([g[k] for g in fake_stats])), 3)}
               for k in real_stats[0]} if pairs else {}
    humanness = max(0.0, min(1.0, 2 * (1 - acc))) * 100
    finished = float(np.mean([p[3]["finished"] for p in pairs])) if pairs else 0.0
    metrics = {"humanness_pct": round(humanness, 1), "detector_accuracy": round(acc, 3),
               "finished_pct": round(100 * finished, 1),
               "pairs": len(pairs), "by_kind": by_kind, "compare_medians": compare,
               "reliable": len(pairs) >= 150, "model": str(model_path), "model_epoch": ck.get("epoch")}
    (model_path.parent / "metrics.json").write_text(json.dumps(metrics, indent=1))
    if write_weights and by_kind:
        weights = dict(DEFAULT_WEIGHTS)
        for gk, info in by_kind.items():
            if info["n"] < 5:
                continue
            caught = max(0.0, min(1.0, (info["accuracy"] - 0.5) / 0.5))
            for tk in TRAINER_KINDS.get(gk, ()):
                weights[tk] = round(DEFAULT_WEIGHTS[tk] * (0.5 + 1.5 * caught), 2)
        (data_dir / WEIGHTS_FILE).write_text(json.dumps(weights, indent=1))
        metrics["task_weights"] = weights
    return metrics


def format_metrics(m: dict) -> str:
    lines = ["", "  Detector evaluation", "  " + "-" * 62,
             f"  Measured humanness   {m['humanness_pct']:.0f}%   "
             f"(detector accuracy {m['detector_accuracy'] * 100:.0f}% on {m['pairs']} real/generated pairs)"]
    lines.append(f"  Generated movements that completed their task: {m.get('finished_pct', 0):.0f}%")
    if not m["reliable"]:
        lines.append("  Few movements yet - treat this number as noisy.")
    lines += ["", f"    {'movement':<14}{'caught':>8}{'pairs':>7}"]
    for k, v in m["by_kind"].items():
        lines.append(f"    {k:<14}{v['accuracy'] * 100:>7.0f}%{v['n']:>7}")
    if m["compare_medians"]:
        lines += ["", f"    {'median':<16}{'you':>10}{'model':>10}"]
        for k, v in m["compare_medians"].items():
            lines.append(f"    {k:<16}{v['real']:>10}{v['generated']:>10}")
    if "task_weights" in m:
        lines += ["", "  Trainer will now ask for more of what gets caught most (task_weights.json)."]
    return "\n".join(lines) + "\n"
