"""Portable .dong project documents for sharing complete simulation inputs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .models import (
    BatteryStorage,
    DieselGenerator,
    ElectricalLoad,
    MainGrid,
    MicrogridConfig,
    PhotovoltaicArray,
    ScenarioData,
)


PROJECT_SCHEMA_VERSION = 1


def _timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class ProjectDocument:
    project_name: str
    config: MicrogridConfig
    scenario: ScenarioData
    strategy_key: str = "deterministic"
    confidence_pct: float = 90.0
    schema_version: int = PROJECT_SCHEMA_VERSION
    created_at: str = ""
    modified_at: str = ""

    def __post_init__(self) -> None:
        now = _timestamp()
        self.created_at = self.created_at or now
        self.modified_at = self.modified_at or now
        self.validate()

    def validate(self) -> None:
        if self.schema_version != PROJECT_SCHEMA_VERSION:
            raise ValueError(
                f"不支持的项目版本 {self.schema_version}，当前仅支持 {PROJECT_SCHEMA_VERSION}"
            )
        if not self.project_name.strip():
            raise ValueError("项目名称不能为空")
        if self.strategy_key not in {"deterministic", "risk_aware"}:
            raise ValueError("项目中的调度策略无效")
        if not 50 <= self.confidence_pct <= 99:
            raise ValueError("项目中的光伏置信度必须在 50% 到 99% 之间")
        self.config.validate()
        self.scenario.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "strategy_key": self.strategy_key,
            "confidence_pct": self.confidence_pct,
            "config": asdict(self.config),
            "scenario": {
                "time_labels": self.scenario.time_labels.tolist(),
                "load_kw": self.scenario.load_kw.tolist(),
                "pv_forecast_kw": self.scenario.pv_forecast_kw.tolist(),
                "pv_actual_kw": self.scenario.pv_actual_kw.tolist(),
                "buy_price_yuan_kwh": self.scenario.buy_price_yuan_kwh.tolist(),
                "source_name": self.scenario.source_name,
                "metadata": self.scenario.metadata,
            },
        }


def _require_mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"项目文件缺少对象字段：{name}")
    return value


def project_from_dict(payload: dict[str, Any]) -> ProjectDocument:
    if not isinstance(payload, dict):
        raise ValueError("项目文件根节点必须是 JSON 对象")
    required = {
        "schema_version",
        "project_name",
        "strategy_key",
        "confidence_pct",
        "config",
        "scenario",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"项目文件缺少字段：{', '.join(missing)}")
    schema_version = payload["schema_version"]
    if schema_version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"不支持的项目版本 {schema_version}，当前仅支持 {PROJECT_SCHEMA_VERSION}"
        )

    config_data = _require_mapping(payload, "config")
    component_names = ("pv", "battery", "diesel", "grid", "load")
    missing_components = [name for name in component_names if name not in config_data]
    if missing_components:
        raise ValueError(f"项目配置缺少组件：{', '.join(missing_components)}")
    try:
        config = MicrogridConfig(
            pv=PhotovoltaicArray(**config_data["pv"]),
            battery=BatteryStorage(**config_data["battery"]),
            diesel=DieselGenerator(**config_data["diesel"]),
            grid=MainGrid(**config_data["grid"]),
            load=ElectricalLoad(**config_data["load"]),
            reserve_soc_margin=float(config_data.get("reserve_soc_margin", 0.10)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"项目组件参数无效：{exc}") from exc

    scenario_data = _require_mapping(payload, "scenario")
    scenario_fields = {
        "time_labels",
        "load_kw",
        "pv_forecast_kw",
        "pv_actual_kw",
        "buy_price_yuan_kwh",
        "source_name",
    }
    missing_scenario = sorted(scenario_fields - scenario_data.keys())
    if missing_scenario:
        raise ValueError(f"项目场景缺少字段：{', '.join(missing_scenario)}")
    try:
        scenario = ScenarioData(
            time_labels=np.asarray(scenario_data["time_labels"], dtype=str),
            load_kw=np.asarray(scenario_data["load_kw"], dtype=float),
            pv_forecast_kw=np.asarray(scenario_data["pv_forecast_kw"], dtype=float),
            pv_actual_kw=np.asarray(scenario_data["pv_actual_kw"], dtype=float),
            buy_price_yuan_kwh=np.asarray(
                scenario_data["buy_price_yuan_kwh"], dtype=float
            ),
            source_name=str(scenario_data["source_name"]),
            metadata=dict(scenario_data.get("metadata", {})),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"项目场景数据无效：{exc}") from exc

    return ProjectDocument(
        project_name=str(payload["project_name"]),
        config=config,
        scenario=scenario,
        strategy_key=str(payload["strategy_key"]),
        confidence_pct=float(payload["confidence_pct"]),
        schema_version=int(schema_version),
        created_at=str(payload.get("created_at", "")),
        modified_at=str(payload.get("modified_at", "")),
    )


def save_project(document: ProjectDocument, path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".dong":
        target = target.with_suffix(".dong")
    target.parent.mkdir(parents=True, exist_ok=True)
    document.modified_at = _timestamp()
    target.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_project(path: str | Path) -> ProjectDocument:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"项目文件不存在：{source}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"无法读取项目文件：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"项目文件不是有效 JSON：第 {exc.lineno} 行") from exc
    return project_from_dict(payload)
