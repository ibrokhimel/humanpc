"""Train the movement model on recorded sessions (GPU if available).

    humanpc train-model                     # everything under ~/.humanpc/training
    humanpc train-model --size base --epochs 80

Checkpoints go to ``<data-dir>/model/``: ``model.pt`` (best validation loss),
``train_log.json``. The detector evaluation runs afterwards unless ``--no-eval``.
"""

from __future__ import annotations

import json
import random
import time
import zlib
from pathlib import Path

import numpy as np
import torch

from .model import ModelConfig, MoveModel, losses, save
from .segments import Segment, load_all

ARRAY_KEYS = ("inputs", "dxdy", "moved", "click", "wheel", "end")
PAD_TO = 64  # round batch lengths up: few distinct shapes keep the CUDA allocator from fragmenting
GPU_CACHE_STEPS = 4_000_000  # up to this many steps (~0.7 GB) the whole dataset lives on the GPU


def is_val(seg: Segment, frac: int = 10) -> bool:
    """Deterministic ~1/frac validation split (stable across runs and new data)."""
    return zlib.crc32(f"{seg.session}:{seg.t0}".encode()) % frac == 0


def mirrored(seg: Segment) -> Segment:
    """Top-bottom mirror in the rotated frame (flip every y-like quantity)."""
    from dataclasses import replace

    from .segments import GEN_KINDS, STEP_DIM
    a = {k: v.copy() for k, v in seg.arrays.items()}
    a["inputs"][:, 1] *= -1  # previous dy
    a["inputs"][:, STEP_DIM + 1] *= -1  # ry / d
    a["inputs"][:, STEP_DIM + 3] *= -1  # slog(ry)
    a["dxdy"][:, 1] *= -1
    a["cond"][len(GEN_KINDS) + 2] *= -1  # sin(direction)
    return replace(seg, arrays=a, session=seg.session + ":mirror")


def auto_size(total_steps: int) -> str:
    return "small" if total_steps < 400_000 else "base" if total_steps < 4_000_000 else "large"


def batches(segs: list[Segment], people: list[str], token_budget: int, *, shuffle: bool, device):
    """Length-bucketed, right-padded batches as tensors on ``device``."""
    order = sorted(range(len(segs)), key=lambda i: len(segs[i].arrays["end"]))
    groups, cur, cur_max = [], [], 0
    for i in order:
        n = -(-len(segs[i].arrays["end"]) // PAD_TO) * PAD_TO
        if cur and max(cur_max, n) * (len(cur) + 1) > token_budget:
            groups.append(cur)
            cur, cur_max = [], 0
        cur.append(i)
        cur_max = max(cur_max, n)
    if cur:
        groups.append(cur)
    if shuffle:
        random.shuffle(groups)
    pid = {p: k for k, p in enumerate(people)}
    for g in groups:
        t = -(-max(len(segs[i].arrays["end"]) for i in g) // PAD_TO) * PAD_TO
        b = {}
        for k in ARRAY_KEYS:
            a0 = segs[g[0]].arrays[k]
            buf = np.zeros((len(g), t) + a0.shape[1:], a0.dtype)
            for j, i in enumerate(g):
                a = segs[i].arrays[k]
                buf[j, :len(a)] = a
            b[k] = torch.from_numpy(buf).to(device, non_blocking=True)
        mask = np.zeros((len(g), t), np.float32)
        for j, i in enumerate(g):
            mask[j, :len(segs[i].arrays["end"])] = 1
        b["mask"] = torch.from_numpy(mask).to(device)
        b["cond"] = torch.from_numpy(np.stack([segs[i].arrays["cond"] for i in g])).to(device)
        b["person"] = torch.tensor([pid.get(segs[i].person, 0) for i in g], device=device)
        yield b


def run_epoch(model, cached: list[dict], opt, sched, *, device, train: bool, amp_dtype):
    """One pass over batches already on ``device`` (built once; only their order changes)."""
    model.train(train)
    totals, count = {}, 0
    if train:
        random.shuffle(cached)
    for b in cached:
        b = {k: v.to(device, non_blocking=True) for k, v in b.items()}  # no-op when already there
        with torch.set_grad_enabled(train), torch.autocast(device.type, dtype=amp_dtype,
                                                           enabled=device.type == "cuda"):
            out = model(b["inputs"], b["cond"], b["person"])
            ls = losses(out, b)
        if train:
            opt.zero_grad(set_to_none=True)
            ls["total"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            if sched:
                sched.step()
        w = float(b["mask"].sum())
        for k, v in ls.items():
            totals[k] = totals.get(k, 0.0) + float(v.detach()) * w
        count += w
    return {k: v / max(count, 1) for k, v in totals.items()}


def train(data_dir: Path, out_dir: Path | None = None, *, epochs: int = 1000, size: str = "auto",
          token_budget: int = 32_768, lr: float = 3e-4, patience: int = 15, plateau: int = 5, seed: int = 0,
          cpu: bool = False, mirror: bool = True, max_sessions: int | None = None, log=print) -> dict:
    """Train until validation stops improving (``epochs`` is only an upper bound).

    The learning rate warms up, then halves whenever validation hasn't improved for
    ``plateau`` epochs; training stops after ``patience`` epochs without a new best.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    data_dir = Path(data_dir)
    out_dir = Path(out_dir) if out_dir else data_dir / "model"
    out_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() and not cpu else "cpu")

    segs = load_all(data_dir, max_sessions=max_sessions)
    if len(segs) < 20:
        raise ValueError(f"only {len(segs)} usable movements - record more with 'humanpc trainer' first")
    people = sorted({s.person for s in segs})
    tr = [s for s in segs if not is_val(s)]
    va = [s for s in segs if is_val(s)] or tr[: max(1, len(tr) // 10)]
    if mirror:
        tr = tr + [mirrored(s) for s in tr]
    total_steps = sum(len(s.arrays["end"]) for s in tr)
    size = auto_size(total_steps) if size == "auto" else size
    model = MoveModel(ModelConfig.preset(size, len(people))).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    log(f"device {device}{' (' + torch.cuda.get_device_name(0) + ')' if device.type == 'cuda' else ''}"
        f" | {len(tr)} train / {len(va)} val movements, {total_steps:,} steps | people: {', '.join(people)}")
    log(f"model '{size}': {n_params / 1e6:.2f}M parameters")

    amp_dtype = torch.bfloat16 if device.type == "cuda" and torch.cuda.is_bf16_supported() else torch.float16
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05, betas=(0.9, 0.95))
    home = device if total_steps <= GPU_CACHE_STEPS else torch.device("cpu")
    tr_b = list(batches(tr, people, token_budget, shuffle=False, device=home))
    va_b = list(batches(va, people, token_budget, shuffle=False, device=home))
    warm = min(200, 5 * len(tr_b) + 1)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm))

    best, best_epoch, history = float("inf"), -1, []
    t_start = time.time()
    for ep in range(1, epochs + 1):
        t0 = time.time()
        trl = run_epoch(model, tr_b, opt, sched, device=device, train=True, amp_dtype=amp_dtype)
        with torch.no_grad():
            val = run_epoch(model, va_b, opt, None, device=device, train=False, amp_dtype=amp_dtype)
        history.append({"epoch": ep, "train": trl, "val": val, "seconds": round(time.time() - t0, 2),
                        "lr": opt.param_groups[0]["lr"]})
        mark = ""
        if val["total"] < best:
            best, best_epoch, mark = val["total"], ep, "  *best"
            save(model, out_dir / "model.pt", people=people, epoch=ep, val_loss=best, size=size)
        log(f"epoch {ep:3d}  train {trl['total']:.4f}  val {val['total']:.4f}  "
            f"(move {val['moved']:.3f} path {val['mdn']:.3f} click {val['click']:.3f} "
            f"wheel {val['wheel']:.3f} end {val['end']:.3f})  {time.time() - t0:.1f}s{mark}")
        if ep - best_epoch >= patience:
            log(f"no improvement for {patience} epochs - stopping early")
            break
        if not mark and (ep - best_epoch) % plateau == 0:
            sched.base_lrs = [b / 2 for b in sched.base_lrs]  # stuck: take smaller steps
            for g, b in zip(opt.param_groups, sched.base_lrs):
                g["lr"] = b * min(1.0, (sched.last_epoch + 1) / warm)
            log(f"no improvement for {plateau} epochs - learning rate halved to {sched.base_lrs[0]:.1e}")
    summary = {"best_val_loss": best, "best_epoch": best_epoch, "epochs_run": len(history),
               "size": size, "params": n_params, "train_movements": len(tr), "val_movements": len(va),
               "train_steps": total_steps, "people": people, "device": str(device),
               "minutes": round((time.time() - t_start) / 60, 2), "model": str(out_dir / "model.pt")}
    (out_dir / "train_log.json").write_text(json.dumps({"summary": summary, "history": history}, indent=1))
    return summary
