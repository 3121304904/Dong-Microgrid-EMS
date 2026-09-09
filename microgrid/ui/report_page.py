"""In-app operating report and export entry point."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..analysis import MonteCarloResult
from ..reporting import build_report_conclusion
from ..scheduler import DispatchResult
from .charts import _style_axis


class ReportChart(FigureCanvasQTAgg):
    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(8.5, 4.0), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(220)

    def update_results(self, baseline: DispatchResult, results: dict[str, DispatchResult]) -> None:
        ordered = (baseline, results["deterministic"], results["risk_aware"])
        labels = ("无储能基础", "确定性 P50", "风险感知")
        self.figure.clear()
        axes = self.figure.subplots(1, 2, gridspec_kw={"wspace": 0.34})

        categories = (("电网购电", "#2B6CB0"), ("柴油发电", "#C46731"), ("储能损耗", "#18785C"))
        bottom = np.zeros(3)
        for category, color in categories:
            values = np.array([max(0.0, item.cost_breakdown.get(category, 0.0)) for item in ordered])
            axes[0].bar(labels, values, bottom=bottom, label=category, color=color, width=0.58)
            bottom += values
        totals = [item.metrics["total_cost_yuan"] for item in ordered]
        axes[0].plot(labels, totals, color="#17212B", marker="o", linewidth=1.4, label="净运行成本")
        axes[0].set_title("费用构成", loc="left", fontsize=10, fontweight="bold")
        axes[0].set_ylabel("元", fontsize=8)
        axes[0].set_ylim(0, max(bottom) * 1.28 if max(bottom) > 0 else 1)
        axes[0].legend(frameon=False, fontsize=6.8, ncols=2, loc="upper right")
        axes[0].tick_params(axis="x", labelrotation=0)
        _style_axis(axes[0])

        source_specs = (
            ("光伏消纳", "#D69B21", [item.metrics["pv_energy_kwh"] - item.metrics["curtailment_kwh"] for item in ordered]),
            ("主网购电", "#2B6CB0", [item.metrics["grid_import_kwh"] for item in ordered]),
            ("柴油发电", "#C46731", [item.metrics["diesel_energy_kwh"] for item in ordered]),
        )
        source_bottom = np.zeros(3)
        for name, color, values in source_specs:
            numeric = np.asarray(values, dtype=float)
            axes[1].bar(labels, numeric, bottom=source_bottom, label=name, color=color, width=0.58)
            source_bottom += numeric
        axes[1].set_title("能源来源", loc="left", fontsize=10, fontweight="bold")
        axes[1].set_ylabel("kWh", fontsize=8)
        axes[1].set_ylim(0, max(source_bottom) * 1.28 if max(source_bottom) > 0 else 1)
        axes[1].legend(frameon=False, fontsize=6.8, ncols=3, loc="upper right")
        _style_axis(axes[1])
        self.figure.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.17)
        self.draw_idle()


class ReportPage(QWidget):
    export_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.baseline: DispatchResult | None = None
        self.results: dict[str, DispatchResult] = {}
        self.monte_carlo: MonteCarloResult | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel("运行报告")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("基础方案、确定性与风险感知策略的统一结论视图")
        subtitle.setObjectName("muted")
        self.risk_badge = QLabel("风险实验未运行")
        self.risk_badge.setStyleSheet("color:#637083;background:#EDF2F3;padding:4px 8px;border-radius:3px;font-weight:700;")
        export_button = QPushButton("导出报告包")
        export_button.setObjectName("primaryButton")
        export_button.setToolTip("导出 Markdown、CSV、JSON 与 PNG 图表")
        export_button.clicked.connect(self.export_requested.emit)
        heading.addWidget(title)
        heading.addSpacing(10)
        heading.addWidget(subtitle)
        heading.addStretch()
        heading.addWidget(self.risk_badge)
        heading.addWidget(export_button)
        layout.addLayout(heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        chart_panel = QFrame()
        chart_panel.setObjectName("chartPanel")
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(8, 7, 8, 5)
        self.chart = ReportChart()
        chart_layout.addWidget(self.chart)
        splitter.addWidget(chart_panel)

        summary_panel = QFrame()
        summary_panel.setObjectName("chartPanel")
        summary_layout = QVBoxLayout(summary_panel)
        summary_layout.setContentsMargins(12, 10, 12, 10)
        summary_title = QLabel("自动结论摘要")
        summary_title.setObjectName("sectionTitle")
        summary_layout.addWidget(summary_title)
        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(False)
        self.summary.setFrameShape(QFrame.Shape.NoFrame)
        self.summary.setStyleSheet("QTextBrowser{background:#FFFFFF;color:#384755;line-height:1.5;}")
        self.summary.setText("等待调度结果。")
        summary_layout.addWidget(self.summary, 1)
        self.risk_details = QLabel("Monte Carlo 风险指标将在实验完成后自动同步。")
        self.risk_details.setObjectName("muted")
        self.risk_details.setWordWrap(True)
        summary_layout.addWidget(self.risk_details)
        splitter.addWidget(summary_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 360])
        layout.addWidget(splitter, 1)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["指标", "无储能基础", "确定性 P50", "风险感知"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(188)
        layout.addWidget(self.table)

    def set_results(
        self,
        baseline: DispatchResult,
        results: dict[str, DispatchResult],
        monte_carlo: MonteCarloResult | None = None,
    ) -> None:
        self.baseline = baseline
        self.results = results
        self.monte_carlo = monte_carlo
        self.chart.update_results(baseline, results)
        conclusion = build_report_conclusion(baseline, results, monte_carlo)
        self.summary.setMarkdown(conclusion)
        self._render_table()
        self._render_risk()

    def set_monte_carlo(self, result: MonteCarloResult) -> None:
        self.monte_carlo = result
        if self.baseline is not None and self.results:
            self.set_results(self.baseline, self.results, result)

    def _render_table(self) -> None:
        if self.baseline is None or not self.results:
            return
        ordered = (self.baseline, self.results["deterministic"], self.results["risk_aware"])
        rows = (
            ("实际运行成本 / 元", "total_cost_yuan", 1),
            ("主网购电 / kWh", "grid_import_kwh", 1),
            ("柴油发电 / kWh", "diesel_energy_kwh", 1),
            ("光伏消纳率 / %", "renewable_utilization_pct", 1),
            ("碳排放 / kgCO2", "carbon_kg", 1),
            ("最低 SOC / %", "min_soc_pct", 1),
            ("失负荷 / kWh", "unserved_kwh", 3),
        )
        self.table.setRowCount(len(rows))
        for row_index, (label, key, digits) in enumerate(rows):
            values = [label] + [f"{item.metrics[key]:.{digits}f}" for item in ordered]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_index, column, item)

    def _render_risk(self) -> None:
        if self.monte_carlo is None:
            self.risk_badge.setText("风险实验未运行")
            self.risk_details.setText("Monte Carlo 风险指标将在实验完成后自动同步。")
            return
        summary = self.monte_carlo.summary
        risk_cost = summary[(summary.strategy_key == "risk_aware") & (summary.metric == "total_cost_yuan")].iloc[0]
        det_cost = summary[(summary.strategy_key == "deterministic") & (summary.metric == "total_cost_yuan")].iloc[0]
        risk_unserved = summary[(summary.strategy_key == "risk_aware") & (summary.metric == "unserved_kwh")].iloc[0]
        self.risk_badge.setText(f"{self.monte_carlo.settings.sample_count} 个随机场景")
        self.risk_badge.setStyleSheet("color:#18785C;background:#E6F2EE;padding:4px 8px;border-radius:3px;font-weight:700;")
        self.risk_details.setText(
            f"成本 P95：确定性 {det_cost.p95:.1f} 元，风险感知 {risk_cost.p95:.1f} 元；"
            f"风险感知失负荷发生概率 {risk_unserved.exceedance_pct:.1f}%。"
        )
