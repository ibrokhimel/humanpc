"""Conditional event Transformer for mouse movement (torch).

Causal Transformer over ``BIN_MS`` steps. A condition vector (task kind,
distance, direction, target size, scroll amount, ...) and a per-person style
embedding are added to every position. Heads per step:

* ``moved``  — Bernoulli: does the cursor move in this step?
* ``mdn``    — K-component bivariate Gaussian mixture over (dx, dy) if it moves
* ``click``  — 5-way: none / left down / left up / right down / right up
* ``wheel``  — 7-way: -3..+3 notches
* ``end``    — Bernoulli: is this the segment's last step?

Blocks carry a KV cache so generation is O(n) per step.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from .segments import CLICK_CLASSES, COND_DIM, IN_DIM, MAX_STEPS, WHEEL_CLASSES


@dataclass
class ModelConfig:
    n_people: int = 1
    d_model: int = 256
    n_layers: int = 6
    n_heads: int = 8
    mixtures: int = 8
    dropout: float = 0.1
    max_steps: int = MAX_STEPS
    pos_embedding: bool = False  # off: with little data it memorises by step index (elapsed time is an input)

    @classmethod
    def preset(cls, size: str, n_people: int) -> "ModelConfig":
        sizes = {"small": (128, 4, 4), "base": (256, 6, 8), "large": (384, 8, 8)}
        d, n, h = sizes[size]
        return cls(n_people=n_people, d_model=d, n_layers=n, n_heads=h,
                   dropout=0.2 if size == "small" else 0.1)


class Block(nn.Module):
    def __init__(self, d: int, heads: int, dropout: float):
        super().__init__()
        self.heads = heads
        self.ln1, self.ln2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.qkv, self.proj = nn.Linear(d, 3 * d), nn.Linear(d, d)
        self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d), nn.Dropout(dropout))
        self.drop = nn.Dropout(dropout)
        self.p = dropout

    def forward(self, x, cache=None, start: int = 0):
        b, t, d = x.shape
        q, k, v = self.qkv(self.ln1(x)).split(d, dim=2)
        q, k, v = (z.view(b, t, self.heads, d // self.heads).transpose(1, 2) for z in (q, k, v))
        if cache is not None:
            if len(cache) == 3:  # preallocated (k_buf, v_buf, "fixed"): write in place, no reallocation
                cache[0][:, :, start:start + t] = k
                cache[1][:, :, start:start + t] = v
                k, v = cache[0][:, :, :start + t], cache[1][:, :, :start + t]
            else:
                if cache[0] is not None:
                    k, v = torch.cat([cache[0], k], 2), torch.cat([cache[1], v], 2)
                cache = (k, v)
        causal = t > 1  # with a cache, t == 1 attends to everything before it
        y = F.scaled_dot_product_attention(q, k, v, is_causal=causal,
                                           dropout_p=self.p if self.training else 0.0)
        x = x + self.drop(self.proj(y.transpose(1, 2).reshape(b, t, d)))
        return x + self.mlp(self.ln2(x)), cache


class MoveModel(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        d = cfg.d_model
        self.inp = nn.Linear(IN_DIM, d)
        self.cond = nn.Sequential(nn.Linear(COND_DIM, d), nn.GELU(), nn.Linear(d, d))
        self.person = nn.Embedding(max(1, cfg.n_people), d)
        self.pos = nn.Embedding(cfg.max_steps, d)
        self.blocks = nn.ModuleList(Block(d, cfg.n_heads, cfg.dropout) for _ in range(cfg.n_layers))
        self.ln = nn.LayerNorm(d)
        k = cfg.mixtures
        self.head = nn.Linear(d, 1 + 6 * k + CLICK_CLASSES + WHEEL_CLASSES + 1)
        self.apply(self._init)

    @staticmethod
    def _init(m):
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, std=0.02)
            nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, std=0.02)

    def forward(self, inputs, cond, person, *, cache=None, start: int = 0):
        """inputs (B,T,IN_DIM), cond (B,COND_DIM), person (B,) -> head dict [, cache]."""
        t = inputs.shape[1]
        pos = torch.arange(start, start + t, device=inputs.device).clamp_max(self.cfg.max_steps - 1)
        x = self.inp(inputs) + (self.cond(cond) + self.person(person))[:, None]
        if self.cfg.pos_embedding:
            x = x + self.pos(pos)[None]
        new_cache = []
        for i, blk in enumerate(self.blocks):
            x, c = blk(x, None if cache is None else cache[i], start)
            new_cache.append(c)
        out = self.split(self.head(self.ln(x)).float())
        return (out, new_cache) if cache is not None else out

    def split(self, h):
        k = self.cfg.mixtures
        i = 0

        def take(n):
            nonlocal i
            s = h[..., i:i + n]
            i += n
            return s
        return {"moved": take(1).squeeze(-1), "pi": take(k), "mu": take(2 * k).unflatten(-1, (k, 2)),
                "log_sigma": take(2 * k).unflatten(-1, (k, 2)).clamp(-6, 4), "rho": torch.tanh(take(k)) * 0.95,
                "click": take(CLICK_CLASSES), "wheel": take(WHEEL_CLASSES), "end": take(1).squeeze(-1)}

    def empty_cache(self, batch: int | None = None, max_len: int | None = None, device=None):
        """Growing cache by default; with ``batch`` + ``max_len`` a preallocated one (fast, no fragmentation)."""
        if batch is None:
            return [(None, None) for _ in self.blocks]
        d, h = self.cfg.d_model, self.cfg.n_heads
        w = next(self.parameters())
        shape = (batch, h, max_len, d // h)
        return [(torch.empty(shape, device=device or w.device, dtype=w.dtype),
                 torch.empty(shape, device=device or w.device, dtype=w.dtype), "fixed") for _ in self.blocks]

    @staticmethod
    def select_cache(cache, rows):
        """Keep only batch ``rows`` (a LongTensor) of a cache."""
        return [tuple(z[rows] if torch.is_tensor(z) else z for z in c) for c in cache]

    def config_dict(self) -> dict:
        return asdict(self.cfg)


def mdn_nll(out, xy):
    """Negative log-likelihood of xy (...,2) under the mixture."""
    mu, ls, rho = out["mu"], out["log_sigma"], out["rho"]
    s = ls.exp()
    z = (xy.unsqueeze(-2) - mu) / s
    one_m = 1 - rho ** 2
    log_n = (-(z[..., 0] ** 2 + z[..., 1] ** 2 - 2 * rho * z[..., 0] * z[..., 1]) / (2 * one_m)
             - ls.sum(-1) - 0.5 * torch.log(one_m) - math.log(2 * math.pi))
    return -torch.logsumexp(F.log_softmax(out["pi"], -1) + log_n, -1)


def losses(out, batch) -> dict:
    mask = batch["mask"]
    n = mask.sum().clamp_min(1)
    mv = batch["moved"]
    moved = (F.binary_cross_entropy_with_logits(out["moved"], mv, reduction="none") * mask).sum() / n
    mdn = (mdn_nll(out, batch["dxdy"]) * mask * mv).sum() / (mask * mv).sum().clamp_min(1)
    click = (F.cross_entropy(out["click"].transpose(1, 2), batch["click"], reduction="none") * mask).sum() / n
    wheel = (F.cross_entropy(out["wheel"].transpose(1, 2), batch["wheel"], reduction="none") * mask).sum() / n
    end = (F.binary_cross_entropy_with_logits(out["end"], batch["end"], reduction="none") * mask).sum() / n
    total = moved + 0.25 * mdn + click + wheel + end
    return {"total": total, "moved": moved, "mdn": mdn, "click": click, "wheel": wheel, "end": end}


@torch.no_grad()
def sample(out, temperature: float = 1.0, click_mask=None):
    """One step per batch row from the last position's heads -> dict of tensors.

    ``click_mask`` (B, 5) bool marks click classes that are physically possible
    (can't release an unheld button or press a held one).
    """
    last = {k: v[:, -1] for k, v in out.items()}
    if click_mask is not None:
        last["click"] = last["click"].masked_fill(~click_mask, float("-inf"))
    moved = torch.bernoulli(torch.sigmoid(last["moved"]))
    comp = torch.distributions.Categorical(logits=last["pi"] / temperature).sample()
    idx = comp[:, None, None].expand(-1, 1, 2)
    mu = last["mu"].gather(1, idx).squeeze(1)
    s = last["log_sigma"].gather(1, idx).squeeze(1).exp() * math.sqrt(temperature)
    rho = last["rho"].gather(1, comp[:, None]).squeeze(1)
    e1, e2 = torch.randn_like(rho), torch.randn_like(rho)
    xy = torch.stack([mu[:, 0] + s[:, 0] * e1,
                      mu[:, 1] + s[:, 1] * (rho * e1 + torch.sqrt(1 - rho ** 2) * e2)], -1)
    return {"moved": moved, "dxdy": xy * moved[:, None],
            "click": torch.distributions.Categorical(logits=last["click"] / temperature).sample(),
            "wheel": torch.distributions.Categorical(logits=last["wheel"] / temperature).sample(),
            "end": torch.bernoulli(torch.sigmoid(last["end"]))}


def save(model: MoveModel, path, **extra) -> None:
    torch.save({"config": model.config_dict(), "state": model.state_dict(), **extra}, path)


def load(path, device="cpu") -> tuple[MoveModel, dict]:
    ck = torch.load(path, map_location=device, weights_only=False)
    model = MoveModel(ModelConfig(**ck["config"])).to(device)
    model.load_state_dict(ck["state"])
    model.eval()
    return model, ck
