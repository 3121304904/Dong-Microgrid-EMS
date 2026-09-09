"""Matplotlib widgets used by the desktop dashboard."""

from __future__ import annotations

import numpy as np
from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy

from ..scheduler import DispatchResult


def configure_chart_font() -> None:
    """Use an installed CJK font instead of Matplotlib's Latin default."""

    candidates = ("Microsoft YaHei", "SimHei", "DengXian", "SimSun")
    for family in candidates:
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
        rcParams["axes.unicode_minus"] = False
        return


configure_chart_font()


def _style_axis(axis) -> None:
    axis.set_facecolor("#FFFFFF")
    axis.grid(axis="y", color="#E7ECEF", linewidth=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines["left"].set_color("#C9D3D8")
    axis.spines["bottom"].set_color("#C9D3D8")
    axis.tick_params(colors="#637083", labelsize=8)
    axis.title.set_color("#273442")


class DispatchChart(FigureCanvasQTAgg):
    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(10.0, 6.0), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(410)

    def update_result(self, result: DispatchResult) -> None:
        frame = result.frame
        x = np.arange(len(frame)) / 4.0
        self.figure.clear()
        axes = self.figure.subplots(3, 1, sharex=True, gridspec_kw={"hspace": 0.34})
        ax1, ax2, ax3 = axes

        ax1.fill_between(
            x,
            frame.pv_lower_kw,
            frame.pv_upper_kw,
            color="#F4D98B",
            alpha=0.45,
            label=f"光伏 {result.confidence_pct:.0f}% 区间",
        )
        ax1.plot(x, frame.load_kw, color="#273442", linewidth=1.8, label="负荷")
        ax1.plot(x, frame.pv_forecast_kw, color="#D69B21", linewidth=1.6, label="光伏 P50")
        ax1.plot(x, frame.pv_actual_kw, color="#18785C", linewidth=1.4, label="光伏实测")
        ax1.set_ylabel("功率 / kW", fontsize=9)
        ax1.set_title("功率预测与不确定性", loc="left", fontsize=10, fontweight="bold")
        ax1.legend(loc="upper left", ncols=4, frameon=False, fontsize=8)

        ax2.axhline(0, color="#AAB6BD", linewidth=0.8)
        ax2.step(x, frame.net_grid_kw, where="mid", color="#2B6CB0", linewidth=1.4, label="主网净购电")
        ax2.step(x, frame.diesel_kw, where="mid", color="#C46731", linewidth=1.4, label="柴油机")
        ax2.step(x, frame.battery_kw, where="mid", color="#18785C", linewidth=1.4, label="储能(+放电)")
        ax2.set_ylabel("功率 / kW", fontsize=9)
        ax2.set_title("调度执行曲线", loc="left", fontsize=10, fontweight="bold")
        ax2.legend(loc="upper left", ncols=3, frameon=False, fontsize=8)

        ax3.plot(x, frame.soc_pct, color="#18785C", linewidth=1.8, label="SOC")
        ax3.fill_between(x, 0, frame.soc_pct, color="#DDEFE9", alpha=0.65)
        ax3.set_ylabel("SOC / %", fontsize=9)
        ax3.set_ylim(0, 100)
        price_axis = ax3.twinx()
        price_axis.step(x, frame.price_yuan_kwh, where="post", color="#C46731", alpha=0.75, label="购电价")
        price_axis.set_ylabel("元/kWh", color="#C46731", fontsize=9)
        price_axis.tick_params(colors="#C46731", labelsize=8)
        price_axis.spines["top"].set_visible(False)
        price_axis.spines["right"].set_color("#D5A07E")
        ax3.set_title("储能状态与分时电价", loc="left", fontsize=10, fontweight="bold")
        ax3.set_xlabel("时刻 / h", fontsize=9)
        ax3.set_xticks(np.arange(0, 25, 2))
        ax3.set_xlim(0, 23.75)

        for axis in axes:
            _style_axis(axis)
        self.figure.subplots_adjust(left=0.065, right=0.93, top=0.96, bottom=0.08)
        self.draw_idle()


class ComparisonChart(FigureCanvasQTAgg):
    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(9.0, 3.6), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(250)

    def update_results(self, results: dict[str, DispatchResult]) -> None:
        self.figure.clear()
        axes = self.figure.subplots(1, 3, gridspec_kw={"wspace": 0.38})
        ordered = [results["deterministic"], results["risk_aware"], results["rolling_predictive"]]
        labels = ["确定性 P50", "风险感知", "滚动预测"]
        colors = ["#2B6CB0", "#18785C", "#C46731"]
        specs = [
            ("total_cost_yuan", "实际运行成本", "元"),
            ("grid_import_kwh", "主网购电量", "kWh"),
            ("carbon_kg", "估算碳排放", "kgCO2"),
        ]
        for axis, (key, title, unit) in zip(axes, specs):
            values = [item.metrics[key] for item in ordered]
            bars = axis.bar(labels, values, color=colors, width=0.56)
            axis.bar_label(bars, labels=[f"{value:.1f}" for value in values], padding=3, fontsize=8)
            axis.set_title(title, loc="left", fontsize=10, fontweight="bold")
            axis.set_ylabel(unit, fontsize=8)
            axis.set_ylim(0, max(values) * 1.25 if max(values) > 0 else 1)
            axis.tick_params(axis="x", labelrotation=0)
            _style_axis(axis)
        self.figure.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.16)
        self.draw_idle()
