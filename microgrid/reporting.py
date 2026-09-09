"""Deterministic Markdown report bundle export for course demonstrations."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from matplotlib import font_manager, rcParams
from matplotlib.figure import Figure

from .analysis import MonteCarloResult, SensitivityResult
from .models import MicrogridConfig, ScenarioData
from .scheduler import DispatchResult


@dataclass(frozen=True)
class ReportBundle:
    directory: Path
    markdown_path: Path
    summary_json_path: Path
    chart_paths: tuple[Path, ...]


def _configure_font() -> None:
    for family in ("Microsoft YaHei", "SimHei", "DengXian", "SimSun"):
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
        rcParams["axes.unicode_minus"] = False
        return


_configure_font()


def _safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", name.strip())
    return cleaned or "Dong_report"


def build_report_conclusion(
    baseline: DispatchResult,
    results: dict[str, DispatchResult],
    monte_carlo: MonteCarloResult | None = None,
) -> str:
    deterministic = results["deterministic"]
    risk = results["risk_aware"]
    cheapest = min((deterministic, risk), key=lambda item: item.metrics["total_cost_yuan"])
    saving = baseline.metrics["total_cost_yuan"] - cheapest.metrics["total_cost_yuan"]
    saving_pct = 100.0 * saving / max(baseline.metrics["total_cost_yuan"], 1e-9)
    parts = [
        f"当前场景下，{cheapest.strategy_name}的实际运行成本最低，为 "
        f"{cheapest.metrics['total_cost_yuan']:.1f} 元；相对无储能基础方案节省 "
        f"{saving:.1f} 元（{saving_pct:.1f}%）。",
        f"该策略光伏消纳率为 {cheapest.metrics['renewable_utilization_pct']:.1f}%，"
        f"主网购电量为 {cheapest.metrics['grid_import_kwh']:.1f} kWh，"
        f"全天失负荷为 {cheapest.metrics['unserved_kwh']:.3f} kWh。",
    ]
    if monte_carlo is not None:
        row = monte_carlo.summary[
            (monte_carlo.summary.strategy_key == "risk_aware")
            & (monte_carlo.summary.metric == "total_cost_yuan")
        ]
        if not row.empty:
            value = row.iloc[0]
            parts.append(
                f"在 {monte_carlo.settings.sample_count} 个随机光伏场景中，风险感知策略成本"
                f"中位数为 {value.p50:.1f} 元，P95 为 {value.p95:.1f} 元。"
            )
    return "".join(parts)


def _comparison_chart(
    baseline: DispatchResult,
    results: dict[str, DispatchResult],
    target: Path,
) -> None:
    ordered = [baseline, results["deterministic"], results["risk_aware"]]
    labels = ["基础方案", "确定性 P50", "风险感知"]
    colors = ["#7B8794", "#2B6CB0", "#18785C"]
    specs = [
        ("total_cost_yuan", "运行成本", "元"),
        ("grid_import_kwh", "主网购电", "kWh"),
        ("carbon_kg", "碳排放", "kgCO2"),
    ]
    figure = Figure(figsize=(11, 3.8), dpi=150, facecolor="white")
    axes = figure.subplots(1, 3)
    for axis, (metric, title, unit) in zip(axes, specs):
        values = [item.metrics[metric] for item in ordered]
        bars = axis.bar(labels, values, color=colors, width=0.62)
        axis.bar_label(bars, fmt="%.1f", padding=3, fontsize=8)
        axis.set_title(title, loc="left", fontsize=11, fontweight="bold")
        axis.set_ylabel(unit, fontsize=9)
        axis.grid(axis="y", color="#E7ECEF")
        axis.spines[["top", "right"]].set_visible(False)
        axis.tick_params(axis="x", labelsize=8)
        axis.set_ylim(0, max(values) * 1.22 if max(values) > 0 else 1)
    figure.tight_layout()
    figure.savefig(target, bbox_inches="tight")


def _dispatch_chart(result: DispatchResult, target: Path) -> None:
    frame = result.frame
    x = np.arange(len(frame)) / 4.0
    figure = Figure(figsize=(11, 6.5), dpi=150, facecolor="white")
    axes = figure.subplots(3, 1, sharex=True)
    axes[0].fill_between(x, frame.pv_lower_kw, frame.pv_upper_kw, color="#F4D98B", alpha=0.5)
    axes[0].plot(x, frame.load_kw, color="#273442", label="负荷")
    axes[0].plot(x, frame.pv_actual_kw, color="#18785C", label="光伏实测")
    axes[0].set_ylabel("kW")
    axes[0].legend(frameon=False, ncols=2)
    axes[1].step(x, frame.net_grid_kw, where="mid", color="#2B6CB0", label="主网")
    axes[1].step(x, frame.battery_kw, where="mid", color="#18785C", label="储能")
    axes[1].step(x, frame.diesel_kw, where="mid", color="#C46731", label="柴油机")
    axes[1].axhline(0, color="#AAB6BD", linewidth=0.8)
    axes[1].set_ylabel("kW")
    axes[1].legend(frameon=False, ncols=3)
    axes[2].plot(x, frame.soc_pct, color="#18785C")
    axes[2].fill_between(x, 0, frame.soc_pct, color="#DDEFE9")
    axes[2].set_ylabel("SOC / %")
    axes[2].set_xlabel("时刻 / h")
    axes[2].set_ylim(0, 100)
    for axis in axes:
        axis.grid(axis="y", color="#E7ECEF")
        axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle(f"{result.strategy_name}全天运行曲线", fontsize=13, fontweight="bold")
    figure.tight_layout()
    figure.savefig(target, bbox_inches="tight")


def _monte_carlo_chart(result: MonteCarloResult, target: Path) -> None:
    figure = Figure(figsize=(9, 4.2), dpi=150, facecolor="white")
    axis = figure.subplots()
    groups = [
        result.samples[result.samples.strategy_key == key].total_cost_yuan.to_numpy()
        for key in ("deterministic", "risk_aware")
    ]
    box = axis.boxplot(groups, tick_labels=["确定性 P50", "风险感知"], patch_artist=True)
    for patch, color in zip(box["boxes"], ("#7DB0E2", "#68B79F")):
        patch.set_facecolor(color)
    axis.set_title("Monte Carlo 运行成本分布", loc="left", fontweight="bold")
    axis.set_ylabel("元")
    axis.grid(axis="y", color="#E7ECEF")
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(target, bbox_inches="tight")


def _sensitivity_chart(result: SensitivityResult, target: Path) -> None:
    points = result.points
    x = points.parameter_value.to_numpy()
    figure = Figure(figsize=(9, 4.2), dpi=150, facecolor="white")
    axis = figure.subplots()
    axis.plot(x, points.total_cost_yuan, marker="o", color="#18785C", label="运行成本")
    axis.set_ylabel("成本 / 元", color="#18785C")
    axis.set_xlabel("储能容量 / kWh" if result.settings.variable == "battery_capacity_kwh" else "光伏容量 / kW")
    second = axis.twinx()
    second.plot(x, points.grid_import_kwh, marker="s", color="#2B6CB0", label="主网购电")
    second.set_ylabel("主网购电 / kWh", color="#2B6CB0")
    axis.set_title("容量敏感性分析", loc="left", fontweight="bold")
    axis.grid(axis="y", color="#E7ECEF")
    axis.spines["top"].set_visible(False)
    second.spines["top"].set_visible(False)
    figure.tight_layout()
    figure.savefig(target, bbox_inches="tight")


def export_report_bundle(
    output_directory: str | Path,
    project_name: str,
    data: ScenarioData,
    config: MicrogridConfig,
    baseline: DispatchResult,
    results: dict[str, DispatchResult],
    selected_strategy: str = "risk_aware",
    monte_carlo: MonteCarloResult | None = None,
    sensitivity: SensitivityResult | None = None,
) -> ReportBundle:
    """Export Markdown, raw tables, JSON summary and PNG figures."""

    target = Path(output_directory)
    target.mkdir(parents=True, exist_ok=True)
    charts_dir = target / "charts"
    charts_dir.mkdir(exist_ok=True)
    selected = results[selected_strategy]

    comparison_path = charts_dir / "strategy_comparison.png"
    dispatch_path = charts_dir / "dispatch_overview.png"
    _comparison_chart(baseline, results, comparison_path)
    _dispatch_chart(selected, dispatch_path)
    chart_paths = [comparison_path, dispatch_path]

    for key, result in results.items():
        result.frame.to_csv(
            target / f"dispatch_{key}.csv",
            index=False,
            encoding="utf-8-sig",
            float_format="%.4f",
        )
    baseline.frame.to_csv(
        target / "dispatch_baseline.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.4f",
    )
    if monte_carlo is not None:
        monte_carlo.samples.to_csv(target / "monte_carlo_samples.csv", index=False, encoding="utf-8-sig")
        monte_carlo.summary.to_csv(target / "monte_carlo_summary.csv", index=False, encoding="utf-8-sig")
        path = charts_dir / "monte_carlo_cost.png"
        _monte_carlo_chart(monte_carlo, path)
        chart_paths.append(path)
    if sensitivity is not None:
        sensitivity.points.to_csv(target / "sensitivity.csv", index=False, encoding="utf-8-sig")
        path = charts_dir / "sensitivity.png"
        _sensitivity_chart(sensitivity, path)
        chart_paths.append(path)

    comparison_rows = []
    for item in (baseline, results["deterministic"], results["risk_aware"]):
        m = item.metrics
        comparison_rows.append(
            f"| {item.strategy_name} | {m['total_cost_yuan']:.1f} | "
            f"{m['grid_import_kwh']:.1f} | {m['renewable_utilization_pct']:.1f}% | "
            f"{m['carbon_kg']:.1f} | {m['unserved_kwh']:.3f} |"
        )
    conclusion = build_report_conclusion(baseline, results, monte_carlo)
    markdown = f"""# {_safe_name(project_name)}运行报告

生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}  
数据源：{data.source_name}  
当前展示策略：{selected.strategy_name}

## 结论摘要

{conclusion}

## 方案对比

| 方案 | 成本/元 | 主网购电/kWh | 光伏消纳率 | 碳排放/kgCO2 | 失负荷/kWh |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(comparison_rows)}

![方案对比](charts/strategy_comparison.png)

## 全天调度曲线

![全天调度曲线](charts/dispatch_overview.png)

## 关键参数

| 参数 | 数值 |
| --- | ---: |
| 光伏容量 | {config.pv.capacity_kw:.1f} kW |
| 光伏预测不确定度 | {config.pv.uncertainty_pct:.1f}% |
| 储能容量 | {config.battery.capacity_kwh:.1f} kWh |
| 储能充/放电功率 | {config.battery.max_charge_kw:.1f} / {config.battery.max_discharge_kw:.1f} kW |
| SOC 范围 | {config.battery.min_soc * 100:.1f}%–{config.battery.max_soc * 100:.1f}% |
| 柴油机容量 | {config.diesel.max_power_kw:.1f} kW |
| 主网购电上限 | {config.grid.import_limit_kw:.1f} kW |

## 随机与容量分析

{"Monte Carlo 统计及图表已包含在本报告包中。" if monte_carlo is not None else "尚未运行 Monte Carlo 分析。"}

{"容量敏感性数据及图表已包含在本报告包中。" if sensitivity is not None else "尚未运行容量敏感性分析。"}

## 文件说明

- `dispatch_*.csv`：三种方案的 96 时段明细。
- `summary.json`：配置、指标和费用构成。
- `monte_carlo_*.csv`：随机场景样本与分位数统计（如已运行）。
- `sensitivity.csv`：容量方案点数据（如已运行）。
- `charts/`：报告引用的 PNG 图表。
"""
    markdown_path = target / "RUN_REPORT.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    summary_payload = {
        "project_name": project_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_name": data.source_name,
        "config": asdict(config),
        "metrics": {
            "baseline": baseline.metrics,
            "deterministic": results["deterministic"].metrics,
            "risk_aware": results["risk_aware"].metrics,
        },
        "cost_breakdown": {
            "baseline": baseline.cost_breakdown,
            "deterministic": results["deterministic"].cost_breakdown,
            "risk_aware": results["risk_aware"].cost_breakdown,
        },
        "conclusion": conclusion,
    }
    summary_json_path = target / "summary.json"
    summary_json_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ReportBundle(
        directory=target,
        markdown_path=markdown_path,
        summary_json_path=summary_json_path,
        chart_paths=tuple(chart_paths),
    )
