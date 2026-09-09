"""Uncertainty and capacity experiments built on reusable dispatch plans."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .models import TIME_STEPS, MicrogridConfig, ScenarioData
from .scheduler import (
    DispatchResult,
    execute_dispatch_plan,
    prepare_dispatch_plan,
    run_strategy,
)


ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class AnalysisCancelled(RuntimeError):
    """Raised when a background analysis is cancelled by the user."""


@dataclass(frozen=True)
class MonteCarloSettings:
    sample_count: int = 200
    seed: int = 2026
    correlation: float = 0.86

    def validate(self) -> None:
        if not 20 <= self.sample_count <= 2000:
            raise ValueError("Monte Carlo 样本数必须在 20 到 2000 之间")
        if not 0 <= self.correlation < 1:
            raise ValueError("误差相关系数必须在 [0, 1) 范围内")


@dataclass
class MonteCarloResult:
    settings: MonteCarloSettings
    samples: pd.DataFrame
    summary: pd.DataFrame


@dataclass(frozen=True)
class SensitivitySettings:
    variable: str = "battery_capacity_kwh"
    minimum: float = 60.0
    maximum: float = 300.0
    points: int = 7
    strategy_key: str = "risk_aware"

    def validate(self) -> None:
        if self.variable not in {"battery_capacity_kwh", "pv_capacity_kw"}:
            raise ValueError("敏感性变量必须是储能容量或光伏容量")
        if self.minimum <= 0 or self.maximum <= self.minimum:
            raise ValueError("分析范围必须满足 0 < 最小值 < 最大值")
        if not 3 <= self.points <= 15:
            raise ValueError("方案点数必须在 3 到 15 之间")
        if self.strategy_key not in {"deterministic", "risk_aware"}:
            raise ValueError("敏感性分析策略无效")


@dataclass
class SensitivityResult:
    settings: SensitivitySettings
    points: pd.DataFrame


def _scenario_with_actual(data: ScenarioData, actual_kw: np.ndarray, name: str) -> ScenarioData:
    return ScenarioData(
        time_labels=data.time_labels.copy(),
        load_kw=data.load_kw.copy(),
        pv_forecast_kw=data.pv_forecast_kw.copy(),
        pv_actual_kw=np.asarray(actual_kw, dtype=float).copy(),
        buy_price_yuan_kwh=data.buy_price_yuan_kwh.copy(),
        source_name=name,
        metadata=dict(data.metadata),
    )


def _generate_correlated_pv_samples(
    data: ScenarioData,
    config: MicrogridConfig,
    settings: MonteCarloSettings,
) -> np.ndarray:
    rng = np.random.default_rng(settings.seed)
    relative = config.pv.uncertainty_pct / 100.0
    sigma = relative * data.pv_forecast_kw + 0.018 * config.pv.capacity_kw
    daylight = data.pv_forecast_kw > 1e-9
    samples = np.zeros((settings.sample_count, TIME_STEPS))
    innovation_scale = np.sqrt(1.0 - settings.correlation**2)
    for sample_index in range(settings.sample_count):
        standardized = np.zeros(TIME_STEPS)
        standardized[0] = rng.normal()
        innovations = rng.normal(size=TIME_STEPS - 1)
        for t in range(1, TIME_STEPS):
            standardized[t] = (
                settings.correlation * standardized[t - 1]
                + innovation_scale * innovations[t - 1]
            )
        actual = np.clip(
            data.pv_forecast_kw + standardized * sigma,
            0.0,
            config.pv.capacity_kw,
        )
        actual[~daylight] = 0.0
        samples[sample_index] = actual
    return samples


def run_monte_carlo(
    data: ScenarioData,
    config: MicrogridConfig,
    confidence_pct: float = 90.0,
    settings: MonteCarloSettings | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> MonteCarloResult:
    """Execute both fixed day-ahead plans against identical random PV paths."""

    settings = settings or MonteCarloSettings()
    settings.validate()
    data.validate()
    config.validate()
    plans = {
        key: prepare_dispatch_plan(data, config, key, confidence_pct)
        for key in ("deterministic", "risk_aware")
    }
    nominal = {
        key: execute_dispatch_plan(data, config, plan)
        for key, plan in plans.items()
    }
    pv_samples = _generate_correlated_pv_samples(data, config, settings)
    rows: list[dict[str, float | int | str]] = []
    total = settings.sample_count
    if progress_callback:
        progress_callback(0, total)
    for index, actual_kw in enumerate(pv_samples):
        if cancel_check and cancel_check():
            raise AnalysisCancelled("Monte Carlo 分析已取消")
        sample_data = _scenario_with_actual(
            data,
            actual_kw,
            f"Monte Carlo / {index + 1}",
        )
        for key, plan in plans.items():
            metrics = execute_dispatch_plan(sample_data, config, plan).metrics
            rows.append(
                {
                    "sample": index + 1,
                    "strategy_key": key,
                    "strategy_name": plan.strategy_name,
                    "total_cost_yuan": metrics["total_cost_yuan"],
                    "grid_import_kwh": metrics["grid_import_kwh"],
                    "min_soc_pct": metrics["min_soc_pct"],
                    "curtailment_kwh": metrics["curtailment_kwh"],
                    "unserved_kwh": metrics["unserved_kwh"],
                    "carbon_kg": metrics["carbon_kg"],
                }
            )
        if progress_callback:
            progress_callback(index + 1, total)

    samples = pd.DataFrame(rows)
    summary_rows: list[dict[str, float | str]] = []
    metric_names = {
        "total_cost_yuan": "运行成本 / 元",
        "grid_import_kwh": "主网购电 / kWh",
        "min_soc_pct": "最低 SOC / %",
        "curtailment_kwh": "弃光 / kWh",
        "unserved_kwh": "失负荷 / kWh",
        "carbon_kg": "碳排放 / kgCO2",
    }
    for key in ("deterministic", "risk_aware"):
        subset = samples[samples.strategy_key == key]
        for metric, label in metric_names.items():
            values = subset[metric].to_numpy(dtype=float)
            if metric == "min_soc_pct":
                threshold = config.battery.min_soc * 100.0 + 2.0
                exceedance = 100.0 * float(np.mean(values < threshold))
                rule = f"低于 {threshold:.1f}%"
            elif metric in {"curtailment_kwh", "unserved_kwh"}:
                threshold = 0.0
                exceedance = 100.0 * float(np.mean(values > threshold + 1e-9))
                rule = "大于 0"
            else:
                threshold = nominal[key].metrics[metric] * 1.10
                exceedance = 100.0 * float(np.mean(values > threshold))
                rule = "高于名义值 10%"
            summary_rows.append(
                {
                    "strategy_key": key,
                    "strategy_name": plans[key].strategy_name,
                    "metric": metric,
                    "metric_name": label,
                    "mean": float(np.mean(values)),
                    "p05": float(np.quantile(values, 0.05)),
                    "p50": float(np.quantile(values, 0.50)),
                    "p95": float(np.quantile(values, 0.95)),
                    "threshold": threshold,
                    "exceedance_pct": exceedance,
                    "exceedance_rule": rule,
                }
            )
    return MonteCarloResult(settings=settings, samples=samples, summary=pd.DataFrame(summary_rows))


def _scale_pv_scenario(
    data: ScenarioData,
    old_capacity_kw: float,
    new_capacity_kw: float,
) -> ScenarioData:
    ratio = new_capacity_kw / old_capacity_kw
    return ScenarioData(
        time_labels=data.time_labels.copy(),
        load_kw=data.load_kw.copy(),
        pv_forecast_kw=np.clip(data.pv_forecast_kw * ratio, 0.0, new_capacity_kw),
        pv_actual_kw=np.clip(data.pv_actual_kw * ratio, 0.0, new_capacity_kw),
        buy_price_yuan_kwh=data.buy_price_yuan_kwh.copy(),
        source_name=f"容量分析 / 光伏 {new_capacity_kw:.0f} kW",
        metadata={**data.metadata, "capacity_analysis_pv_kw": float(new_capacity_kw)},
    )


def run_sensitivity_analysis(
    data: ScenarioData,
    config: MicrogridConfig,
    confidence_pct: float = 90.0,
    settings: SensitivitySettings | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> SensitivityResult:
    """Evaluate one strategy over a battery or PV capacity range."""

    settings = settings or SensitivitySettings()
    settings.validate()
    data.validate()
    config.validate()
    values = np.linspace(settings.minimum, settings.maximum, settings.points)
    rows: list[dict[str, float | str]] = []
    if progress_callback:
        progress_callback(0, len(values))
    for index, value in enumerate(values):
        if cancel_check and cancel_check():
            raise AnalysisCancelled("容量敏感性分析已取消")
        point_config = deepcopy(config)
        point_data = _scenario_with_actual(data, data.pv_actual_kw, data.source_name)
        if settings.variable == "battery_capacity_kwh":
            point_config.battery.capacity_kwh = float(value)
        else:
            old_capacity = point_config.pv.capacity_kw
            point_config.pv.capacity_kw = float(value)
            point_data = _scale_pv_scenario(data, old_capacity, float(value))
        result: DispatchResult = run_strategy(
            point_data,
            point_config,
            settings.strategy_key,
            confidence_pct,
        )
        rows.append(
            {
                "variable": settings.variable,
                "parameter_value": float(value),
                "strategy_key": settings.strategy_key,
                "total_cost_yuan": result.metrics["total_cost_yuan"],
                "grid_import_kwh": result.metrics["grid_import_kwh"],
                "carbon_kg": result.metrics["carbon_kg"],
                "renewable_utilization_pct": result.metrics["renewable_utilization_pct"],
                "curtailment_kwh": result.metrics["curtailment_kwh"],
            }
        )
        if progress_callback:
            progress_callback(index + 1, len(values))
    return SensitivityResult(settings=settings, points=pd.DataFrame(rows))
