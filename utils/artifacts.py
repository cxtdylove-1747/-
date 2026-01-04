from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _safe_name(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    return s[:80] if len(s) > 80 else s


def make_run_dir(
    base_dir: str,
    mode: str,
    executor_type: str,
    engines: list,
    test_name: Optional[str] = None,
    suite: Optional[str] = None,
) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    parts = [ts, _safe_name(mode), _safe_name(executor_type)]
    if engines:
        parts.append(_safe_name("-".join([str(x) for x in engines])))
    if suite:
        parts.append(_safe_name(suite))
    if test_name:
        parts.append(_safe_name(test_name))
    run_id = "_".join([p for p in parts if p])
    out = Path(base_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    return obj


def write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_to_jsonable(data), f, ensure_ascii=False, indent=2, default=str)