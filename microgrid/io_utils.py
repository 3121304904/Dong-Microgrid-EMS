"""Result and summary export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .scheduler import DispatchResult


def export_dispatch_csv(result: DispatchResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.frame.to_csv(target, index=False, encoding="utf-8-sig", float_format="%.4f")
    return target


def export_summary_json(result: DispatchResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "strategy": result.strategy_name,
        "confidence_pct": result.confidence_pct,
        "metrics": result.metrics,
        "cost_breakdown": result.cost_breakdown,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
