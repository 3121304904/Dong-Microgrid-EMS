"""Scenario laboratory page for Monte Carlo and capacity experiments."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import (
    MonteCarloResult,
    MonteCarloSettings,
    SensitivityResult,
    SensitivitySettings,
)
from ..models import MicrogridConfig, ScenarioData
from .charts import _style_axis
from .workers import AnalysisWorker, CancellationToken


class MonteCarloChart(FigureCanvasQTAgg):
    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(8.5, 3.0), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(245)
        self.show_empty()

    def show_empty(self) -> None:
        self.figure.clear()
        axis = self.figure.subplots()
        axis.text(0.5, 0.5, "运行 Monte Carlo 后显示成本分布与分位区间", ha="center", va="center", color="#637083")
        axis.set_axis_off()
        self.draw_idle()

    def update_result(self, result: MonteCarloResult) -> None:
        self.figure.clear()
        axes = self.figure.subplots(1, 2, gridspec_kw={"wspace": 0.34})
        strategies = (("deterministic", "确定性 P50", "#2B6CB0"), ("risk_aware", "风险感知", "#18785C"))
        cost_values = [
            result.samples.loc[result.samples.strategy_key == key, "total_cost_yuan"].to_numpy()
            for key, _, _ in strategies
        ]
        boxes = axes[0].boxplot(cost_values, patch_artist=True, widths=0.52)
        axes[0].set_xticks([1, 2], [item[1] for item in strategies])
        for patch, (_, _, color) in zip(boxes["boxes"], strategies):
            patch.set_facecolor(color)
            patch.set_alpha(0.78)
        axes[0].set_title("运行成本分布", loc="left", fontsize=10, fontweight="bold")
        axes[0].set_ylabel("元", fontsize=8)
        _style_axis(axes[0])

        summary = result.summary[result.summary.metric == "grid_import_kwh"]
        y = np.arange(len(strategies))
        p05 = summary.p05.to_numpy(dtype=float)
        p50 = summary.p50.to_numpy(dtype=float)
        p95 = summary.p95.to_numpy(dtype=float)
        colors = [item[2] for item in strategies]
        axes[1].hlines(y, p05, p95, colors=colors, linewidth=8, alpha=0.30)
        axes[1].scatter(p50, y, color=colors, s=42, zorder=3)
        axes[1].set_yticks(y, [item[1] for item in strategies])
        axes[1].set_xlabel("主网购电 / kWh", fontsize=8)
        axes[1].set_title("P5–P50–P95 分位区间", loc="left", fontsize=10, fontweight="bold")
        axes[1].invert_yaxis()
        _style_axis(axes[1])
        self.figure.subplots_adjust(left=0.08, right=0.97, top=0.86, bottom=0.20)
        self.draw_idle()


class SensitivityChart(FigureCanvasQTAgg):
    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(8.5, 3.0), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(245)
        self.show_empty()

    def show_empty(self) -> None:
        self.figure.clear()
        axis = self.figure.subplots()
        axis.text(0.5, 0.5, "运行容量敏感性分析后显示四项指标趋势", ha="center", va="center", color="#637083")
        axis.set_axis_off()
        self.draw_idle()

    def update_result(self, result: SensitivityResult) -> None:
        frame = result.points
        x = frame.parameter_value.to_numpy(dtype=float)
        x_label = "储能容量 / kWh" if result.settings.variable == "battery_capacity_kwh" else "光伏容量 / kW"
        specs = (
            ("total_cost_yuan", "运行成本", "元", "#18785C"),
            ("grid_import_kwh", "主网购电", "kWh", "#2B6CB0"),
            ("carbon_kg", "碳排放", "kgCO2", "#C46731"),
            ("renewable_utilization_pct", "光伏消纳率", "%", "#D69B21"),
        )
        self.figure.clear()
        axes = self.figure.subplots(2, 2, gridspec_kw={"hspace": 0.55, "wspace": 0.32})
        for axis, (key, title, unit, color) in zip(axes.flat, specs):
            axis.plot(x, frame[key], color=color, marker="o", linewidth=1.8, markersize=4)
            axis.set_title(title, loc="left", fontsize=9, fontweight="bold")
            axis.set_ylabel(unit, fontsize=7)
            axis.set_xlabel(x_label, fontsize=7)
            _style_axis(axis)
        self.figure.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.15)
        self.draw_idle()


class LabPage(QWidget):
    monte_carlo_completed = Signal(object)
    sensitivity_completed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.data: ScenarioData | None = None
        self.config: MicrogridConfig | None = None
        self.confidence_pct = 90.0
        self.monte_carlo_result: MonteCarloResult | None = None
        self.sensitivity_result: SensitivityResult | None = None
        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None
        self._token: CancellationToken | None = None
        self._context_version = 0
        self._job_context_version = -1
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(7)
        heading = QHBoxLayout()
        title = QLabel("场景实验室")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("基于同一调度内核进行随机误差与容量方案实验")
        subtitle.setObjectName("muted")
        heading.addWidget(title)
        heading.addSpacing(10)
        heading.addWidget(subtitle)
        heading.addStretch()
        layout.addLayout(heading)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_monte_carlo_tab(), "Monte Carlo 光伏不确定性")
        self.tabs.addTab(self._build_sensitivity_tab(), "容量敏感性")
        layout.addWidget(self.tabs, 1)

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("等待实验")
        self.progress_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(20)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setToolTip("在当前样本或方案点结束后取消分析")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        progress_row.addWidget(self.progress_label)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.cancel_button)
        layout.addLayout(progress_row)

    def _build_monte_carlo_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("样本数"))
        self.mc_samples = QSpinBox()
        self.mc_samples.setRange(20, 2000)
        self.mc_samples.setValue(200)
        self.mc_samples.setSingleStep(20)
        self.mc_samples.setToolTip("每个样本都执行确定性和风险感知两套固定日前计划")
        controls.addWidget(self.mc_samples)
        controls.addWidget(QLabel("随机种子"))
        self.mc_seed = QSpinBox()
        self.mc_seed.setRange(0, 999999999)
        self.mc_seed.setValue(2026)
        self.mc_seed.setToolTip("相同场景、参数和种子可复现相同结果")
        controls.addWidget(self.mc_seed)
        controls.addStretch()
        self.mc_run_button = QPushButton("运行 Monte Carlo")
        self.mc_run_button.setObjectName("primaryButton")
        self.mc_run_button.setToolTip("在后台生成相关光伏误差场景并公平比较两种计划")
        self.mc_run_button.clicked.connect(self.start_monte_carlo)
        controls.addWidget(self.mc_run_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Vertical)
        panel = QFrame()
        panel.setObjectName("chartPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 6, 8, 4)
        self.mc_chart = MonteCarloChart()
        panel_layout.addWidget(self.mc_chart)
        splitter.addWidget(panel)
        self.mc_table = self._result_table(
            ["策略", "指标", "均值", "P5", "P50", "P95", "超限概率"]
        )
        splitter.addWidget(self.mc_table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([300, 190])
        layout.addWidget(splitter, 1)
        return page

    def _build_sensitivity_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        controls = QGridLayout()
        controls.addWidget(QLabel("分析变量"), 0, 0)
        self.sensitivity_variable = QComboBox()
        self.sensitivity_variable.addItem("储能容量", "battery_capacity_kwh")
        self.sensitivity_variable.addItem("光伏容量", "pv_capacity_kw")
        self.sensitivity_variable.currentIndexChanged.connect(self._set_default_sensitivity_range)
        controls.addWidget(self.sensitivity_variable, 0, 1)
        controls.addWidget(QLabel("最小值"), 0, 2)
        self.sensitivity_min = self._capacity_spin(60.0)
        controls.addWidget(self.sensitivity_min, 0, 3)
        controls.addWidget(QLabel("最大值"), 0, 4)
        self.sensitivity_max = self._capacity_spin(300.0)
        controls.addWidget(self.sensitivity_max, 0, 5)
        controls.addWidget(QLabel("方案点"), 0, 6)
        self.sensitivity_points = QSpinBox()
        self.sensitivity_points.setRange(3, 15)
        self.sensitivity_points.setValue(7)
        controls.addWidget(self.sensitivity_points, 0, 7)
        self.sensitivity_run_button = QPushButton("运行容量分析")
        self.sensitivity_run_button.setObjectName("primaryButton")
        self.sensitivity_run_button.setToolTip("使用等距容量点重新优化并比较成本、购电、碳排和消纳率")
        self.sensitivity_run_button.clicked.connect(self.start_sensitivity)
        controls.addWidget(self.sensitivity_run_button, 0, 8)
        controls.setColumnStretch(9, 1)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Vertical)
        panel = QFrame()
        panel.setObjectName("chartPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 6, 8, 4)
        self.sensitivity_chart = SensitivityChart()
        panel_layout.addWidget(self.sensitivity_chart)
        splitter.addWidget(panel)
        self.sensitivity_table = self._result_table(
            ["容量值", "成本/元", "购电/kWh", "碳排/kg", "消纳率/%", "弃光/kWh"]
        )
        splitter.addWidget(self.sensitivity_table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([300, 190])
        layout.addWidget(splitter, 1)
        return page

    @staticmethod
    def _capacity_spin(value: float) -> QDoubleSpinBox:
        editor = QDoubleSpinBox()
        editor.setRange(10.0, 2000.0)
        editor.setValue(value)
        editor.setDecimals(0)
        editor.setSingleStep(20.0)
        editor.setSuffix(" kW(h)")
        return editor

    @staticmethod
    def _result_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def set_context(self, data: ScenarioData, config: MicrogridConfig, confidence_pct: float, clear_results: bool = False) -> None:
        self.data = data
        self.config = config
        self.confidence_pct = confidence_pct
        if clear_results:
            self._context_version += 1
            if self._thread is not None and self._thread.isRunning():
                self.cancel_analysis()
            self.monte_carlo_result = None
            self.sensitivity_result = None
            self.mc_table.setRowCount(0)
            self.sensitivity_table.setRowCount(0)
            self.mc_chart.show_empty()
            self.sensitivity_chart.show_empty()

    def _set_default_sensitivity_range(self) -> None:
        if self.sensitivity_variable.currentData() == "pv_capacity_kw":
            self.sensitivity_min.setValue(60.0)
            self.sensitivity_max.setValue(240.0)
        else:
            self.sensitivity_min.setValue(60.0)
            self.sensitivity_max.setValue(300.0)

    def start_monte_carlo(self) -> None:
        settings = MonteCarloSettings(self.mc_samples.value(), self.mc_seed.value())
        self._start_worker("monte_carlo", settings)

    def start_sensitivity(self) -> None:
        settings = SensitivitySettings(
            variable=self.sensitivity_variable.currentData(),
            minimum=self.sensitivity_min.value(),
            maximum=self.sensitivity_max.value(),
            points=self.sensitivity_points.value(),
        )
        self._start_worker("sensitivity", settings)

    def _start_worker(self, kind: str, settings: MonteCarloSettings | SensitivitySettings) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, "实验正在运行", "请等待当前实验完成或先取消。")
            return
        if self.data is None or self.config is None:
            QMessageBox.warning(self, "缺少场景", "请先运行一次全天调度。")
            return
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self._token = CancellationToken()
        self._job_context_version = self._context_version
        self._thread = QThread(self)
        self._worker = AnalysisWorker(
            kind,
            deepcopy(self.data),
            deepcopy(self.config),
            self.confidence_pct,
            settings,
            self._token,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.completed.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._release_thread)
        self._set_running(True, "正在生成随机光伏场景..." if kind == "monte_carlo" else "正在计算容量方案点...")
        self._thread.start()

    def _set_running(self, running: bool, label: str) -> None:
        self.mc_run_button.setEnabled(not running)
        self.sensitivity_run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.progress_label.setText(label)
        if running:
            self.progress.setValue(0)

    def cancel_analysis(self) -> None:
        if self._token is not None:
            self._token.cancelled = True
            self.progress_label.setText("正在取消，请等待当前计算点结束...")
            self.cancel_button.setEnabled(False)

    def _release_thread(self) -> None:
        self._thread = None
        self._worker = None
        self._token = None

    def _on_completed(self, kind: str, result: object) -> None:
        try:
            if self._job_context_version != self._context_version:
                self._set_running(False, "输入已变化，旧实验结果已丢弃")
                return
            self.progress.setValue(100)
            if kind == "monte_carlo":
                self.monte_carlo_result = result
                self._render_monte_carlo(result)
                self.progress_label.setText(f"Monte Carlo 完成：{result.settings.sample_count} 个场景")
                self.monte_carlo_completed.emit(result)
            else:
                self.sensitivity_result = result
                self._render_sensitivity(result)
                self.progress_label.setText(f"容量分析完成：{result.settings.points} 个方案点")
                self.sensitivity_completed.emit(result)
            self._set_running(False, self.progress_label.text())
        except Exception as exc:
            self._on_failed(f"结果渲染失败：{exc}")

    def _on_failed(self, message: str) -> None:
        self.progress_label.setText("实验失败")
        self._set_running(False, "实验失败")
        QMessageBox.critical(self, "场景实验失败", message)

    def _on_cancelled(self) -> None:
        self.progress_label.setText("实验已取消")
        self._set_running(False, "实验已取消")

    def _render_monte_carlo(self, result: MonteCarloResult) -> None:
        self.mc_chart.update_result(result)
        frame = result.summary.reset_index(drop=True)
        self.mc_table.setRowCount(len(frame))
        for row_index, row in frame.iterrows():
            values = (
                row.strategy_name,
                row.metric_name,
                f"{row['mean']:.2f}",
                f"{row.p05:.2f}",
                f"{row.p50:.2f}",
                f"{row.p95:.2f}",
                f"{row.exceedance_pct:.1f}%",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.mc_table.setItem(row_index, column, item)

    def _render_sensitivity(self, result: SensitivityResult) -> None:
        self.sensitivity_chart.update_result(result)
        frame = result.points.reset_index(drop=True)
        self.sensitivity_table.setRowCount(len(frame))
        for row_index, row in frame.iterrows():
            values = (
                f"{row.parameter_value:.1f}",
                f"{row.total_cost_yuan:.1f}",
                f"{row.grid_import_kwh:.1f}",
                f"{row.carbon_kg:.1f}",
                f"{row.renewable_utilization_pct:.1f}",
                f"{row.curtailment_kwh:.2f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sensitivity_table.setItem(row_index, column, item)

    def close_threads(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.cancel_analysis()
            self._thread.quit()
            self._thread.wait(3000)
