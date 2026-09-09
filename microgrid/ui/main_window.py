"""Main application window for Dong Microgrid EMS."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..data import (
    SCENARIO_NAMES,
    generate_typical_day,
    list_50hertz_dates,
    load_50hertz_day,
    load_scenario_csv,
    locate_50hertz_csv,
)
from ..io_utils import export_dispatch_csv, export_summary_json
from ..models import MicrogridConfig, ScenarioData, default_config
from ..project import ProjectDocument, load_project, save_project
from ..reporting import export_report_bundle
from ..scheduler import DispatchResult, run_all_strategies, run_baseline
from .charts import ComparisonChart, DispatchChart
from .dialogs import AboutModelDialog, ComponentDialog
from .animations import animate_sections, fade_in, install_button_feedback, install_tab_fade, pulse
from .lab_page import LabPage
from .replay_page import ReplayPage
from .report_page import ReportPage
from .rolling_page import RollingPage
from .theme import APP_STYLE, COLORS
from .topology import TopologyView


class KpiCard(QFrame):
    def __init__(self, title: str, accent: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setStyleSheet(f"QFrame#kpiCard {{ border-left-color: {accent}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 11, 9)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("kpiLabel")
        self.value = QLabel("--")
        self.value.setObjectName("kpiValue")
        self.hint = QLabel("等待运行")
        self.hint.setObjectName("kpiHint")
        layout.addWidget(label)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_data(self, value: str, hint: str) -> None:
        self.value.setText(value)
        self.hint.setText(hint)
        pulse(self, 170)


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.config: MicrogridConfig = default_config()
        self.data: ScenarioData = generate_typical_day(SCENARIO_NAMES[0], self.config)
        self.hertz_path = locate_50hertz_csv(project_root)
        self.hertz_dates = list_50hertz_dates(self.hertz_path) if self.hertz_path else []
        self.results: dict[str, DispatchResult] = {}
        self.current_result: DispatchResult | None = None
        self.baseline_result: DispatchResult | None = None
        self.monte_carlo_result = None
        self.sensitivity_result = None
        self.custom_data = False
        self.project_name = "未命名微电网项目"
        self.project_path: Path | None = None
        self.modified = False
        self._analysis_invalidated = True
        self._building = True

        self.setWindowTitle("Dong 微电网能源管理系统 v1.4")
        self.setMinimumSize(1180, 760)
        self.resize(1500, 920)
        self.setStyleSheet(APP_STYLE)
        self._build_actions()
        self._build_ui()
        self._building = False
        install_tab_fade(self.tabs)
        install_button_feedback(self)
        self._refresh_topology()
        QTimer.singleShot(100, self.run_dispatch)

    def _build_actions(self) -> None:
        self.new_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), "新建", self)
        self.new_action.setShortcut(QKeySequence("Ctrl+N"))
        self.new_action.setToolTip("新建微电网项目（Ctrl+N）")
        self.new_action.triggered.connect(self.new_project)
        self.open_project_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "打开", self)
        self.open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        self.open_project_action.setToolTip("打开 .dong 项目（Ctrl+O）")
        self.open_project_action.triggered.connect(self.open_project_file)
        self.save_project_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "保存", self)
        self.save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_project_action.setToolTip("保存 .dong 项目（Ctrl+S）")
        self.save_project_action.triggered.connect(self.save_project_file)
        self.save_as_action = QAction("项目另存为", self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.triggered.connect(lambda: self.save_project_file(save_as=True))
        self.import_action = QAction("导入 CSV", self)
        self.import_action.setShortcut(QKeySequence("Ctrl+I"))
        self.import_action.triggered.connect(self.import_csv)
        self.export_action = QAction("导出结果", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self.export_results)
        self.run_action = QAction("运行调度", self)
        self.run_action.setShortcut(QKeySequence("Ctrl+R"))
        self.run_action.triggered.connect(self.run_dispatch)
        self.about_action = QAction("模型说明", self)
        self.about_action.setShortcut(QKeySequence("F1"))
        self.about_action.triggered.connect(self.show_model_help)
        for action in (
            self.new_action,
            self.open_project_action,
            self.save_project_action,
            self.save_as_action,
            self.import_action,
            self.export_action,
            self.run_action,
            self.about_action,
        ):
            self.addAction(action)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_sidebar())
        content.addWidget(self._build_workspace(), 1)
        content_host = QWidget()
        content_host.setLayout(content)
        outer.addWidget(content_host, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel("就绪")
        status.addWidget(self.status_label, 1)
        self.balance_label = QLabel("功率平衡：--")
        status.addPermanentWidget(self.balance_label)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("appHeader")
        header.setFixedHeight(67)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 9, 20, 9)
        layout.setSpacing(12)
        mark = QLabel("DG")
        mark.setFixedSize(38, 38)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("background:#E4B344;color:#173B36;font-weight:800;border-radius:5px;font-size:14px;")
        layout.addWidget(mark)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("Dong 微电网能源管理系统")
        title.setObjectName("brandTitle")
        subtitle = QLabel("96 时段经济调度 · 光伏不确定性 · 实时功率平衡")
        subtitle.setObjectName("brandSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)
        layout.addStretch()
        self.project_meta = QLabel()
        self.project_meta.setObjectName("headerMeta")
        layout.addWidget(self.project_meta)
        for action in (self.new_action, self.open_project_action, self.save_project_action):
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setObjectName("headerAction")
            button.setFixedHeight(34)
            layout.addWidget(button)
        help_button = QPushButton("?")
        help_button.setObjectName("iconButton")
        help_button.setToolTip("查看模型与策略说明（F1）")
        help_button.clicked.connect(self.show_model_help)
        layout.addWidget(help_button)
        self._refresh_window_title()
        return header

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        panel.setFixedWidth(292)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 16, 15, 14)
        layout.setSpacing(12)

        source = self._section("数据与场景")
        source_layout = source.layout()
        source_layout.addWidget(self._field_label("数据来源"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("内置典型日", "builtin")
        self.source_combo.addItem("50Hertz 德国光伏 2025", "50hertz")
        self.source_combo.setToolTip("选择可复现的内置场景，或使用 50Hertz 2025 区域光伏曲线")
        self.source_combo.currentIndexChanged.connect(self.on_source_changed)
        if not self.hertz_dates:
            self.source_combo.model().item(1).setEnabled(False)
            self.source_combo.setItemData(1, "未找到 sample_data/Solarenergie_Hochrechnung_2025.csv", Qt.ItemDataRole.ToolTipRole)
        source_layout.addWidget(self.source_combo)
        source_layout.addWidget(self._field_label("50Hertz 日期"))
        self.hertz_date_combo = QComboBox()
        self.hertz_date_combo.addItems(self.hertz_dates or ["无可用日期"])
        self.hertz_date_combo.setToolTip("50Hertz 年度文件中的具体日期；夏令时日期会重采样到 96 点")
        self.hertz_date_combo.currentTextChanged.connect(self.on_hertz_date_changed)
        self.hertz_date_combo.setEnabled(False)
        source_layout.addWidget(self.hertz_date_combo)
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(SCENARIO_NAMES)
        self.scenario_combo.setToolTip("选择内置的 96 点典型日数据")
        self.scenario_combo.currentTextChanged.connect(self.on_scenario_changed)
        source_layout.addWidget(self._field_label("典型日场景"))
        source_layout.addWidget(self.scenario_combo)
        self.source_label = QLabel(self.data.source_name)
        self.source_label.setObjectName("muted")
        self.source_label.setWordWrap(True)
        source_layout.addWidget(self.source_label)
        import_button = QPushButton("导入 CSV 数据")
        import_button.setToolTip("需要 96 行：time、load_kw、pv_forecast_kw、price_yuan_kwh（Ctrl+I）")
        import_button.clicked.connect(self.import_csv)
        source_layout.addWidget(import_button)
        layout.addWidget(source)

        strategy = self._section("调度策略")
        strategy_layout = strategy.layout()
        strategy_layout.addWidget(self._field_label("运行模式"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem("确定性调度 P50", "deterministic")
        self.strategy_combo.addItem("风险感知调度 P下界", "risk_aware")
        self.strategy_combo.addItem("滚动预测调度（4h MPC）", "rolling_predictive")
        self.strategy_combo.currentIndexChanged.connect(self.on_strategy_view_changed)
        strategy_layout.addWidget(self.strategy_combo)
        strategy_layout.addWidget(self._field_label("光伏置信度"))
        confidence_row = QHBoxLayout()
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setRange(50, 99)
        self.confidence_slider.setValue(90)
        self.confidence_slider.setToolTip("置信度越高，风险感知计划越保守")
        self.confidence_value = QLabel("90%")
        self.confidence_value.setFixedWidth(38)
        self.confidence_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.confidence_slider.valueChanged.connect(self.on_confidence_changed)
        confidence_row.addWidget(self.confidence_slider, 1)
        confidence_row.addWidget(self.confidence_value)
        strategy_layout.addLayout(confidence_row)
        run_button = QPushButton("运行全天调度")
        run_button.setObjectName("primaryButton")
        run_button.setToolTip("计算确定性、风险感知和滚动预测三套策略（Ctrl+R）")
        run_button.clicked.connect(self.run_dispatch)
        strategy_layout.addWidget(run_button)
        layout.addWidget(strategy)

        model = self._section("模型参数")
        model_layout = model.layout()
        self.param_summary = QLabel()
        self.param_summary.setObjectName("muted")
        self.param_summary.setWordWrap(True)
        model_layout.addWidget(self.param_summary)
        edit_button = QPushButton("打开组件参数")
        edit_button.clicked.connect(lambda: self.edit_component("battery"))
        model_layout.addWidget(edit_button)
        layout.addWidget(model)

        layout.addStretch()
        export_button = QPushButton("导出当前结果")
        export_button.setToolTip("导出 UTF-8 CSV 与 JSON 摘要（Ctrl+E）")
        export_button.clicked.connect(self.export_results)
        layout.addWidget(export_button)
        return panel

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(11)

        kpis = QGridLayout()
        kpis.setHorizontalSpacing(9)
        self.kpi_cost = KpiCard("实际运行成本", COLORS["grid"])
        self.kpi_grid = KpiCard("主网购电", COLORS["grid"])
        self.kpi_pv = KpiCard("光伏消纳率", COLORS["pv"])
        self.kpi_soc = KpiCard("日末储能 SOC", COLORS["battery"])
        self.kpi_carbon = KpiCard("估算碳排放", COLORS["diesel"])
        for column, card in enumerate((self.kpi_cost, self.kpi_grid, self.kpi_pv, self.kpi_soc, self.kpi_carbon)):
            kpis.addWidget(card, 0, column)
            kpis.setColumnStretch(column, 1)
        layout.addLayout(kpis)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_overview_tab(), "运行总览")
        self.replay_page = ReplayPage()
        self.tabs.addTab(self.replay_page, "实时仿真")
        self.rolling_page = RollingPage()
        self.tabs.addTab(self.rolling_page, "滚动调度中心")
        self.tabs.addTab(self._build_topology_tab(), "微电网拓扑")
        self.tabs.addTab(self._build_comparison_tab(), "策略对比")
        self.lab_page = LabPage()
        self.lab_page.monte_carlo_completed.connect(self._on_monte_carlo_completed)
        self.lab_page.sensitivity_completed.connect(self._on_sensitivity_completed)
        self.tabs.addTab(self.lab_page, "场景实验室")
        self.tabs.addTab(self._build_table_tab(), "96 时段明细")
        self.report_page = ReportPage()
        self.report_page.export_requested.connect(self.export_report)
        self.tabs.addTab(self.report_page, "运行报告")
        layout.addWidget(self.tabs, 1)
        return workspace

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        panel = QFrame()
        panel.setObjectName("chartPanel")
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(12, 10, 12, 8)
        header = QHBoxLayout()
        title = QLabel("全天运行曲线")
        title.setObjectName("sectionTitle")
        self.strategy_badge = QLabel("等待计算")
        self.strategy_badge.setStyleSheet("color:#18785C;background:#E6F2EE;padding:4px 8px;border-radius:3px;font-weight:700;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.strategy_badge)
        inner.addLayout(header)
        self.dispatch_chart = DispatchChart()
        inner.addWidget(self.dispatch_chart, 1)
        layout.addWidget(panel, 1)
        return page

    def _build_topology_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        panel = QFrame()
        panel.setObjectName("chartPanel")
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(14, 12, 14, 12)
        title_row = QHBoxLayout()
        title = QLabel("微电网结构与组件")
        title.setObjectName("sectionTitle")
        hint = QLabel("右键组件打开参数窗口")
        hint.setObjectName("muted")
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(hint)
        inner.addLayout(title_row)
        self.topology = TopologyView()
        self.topology.edit_requested.connect(self.edit_component)
        inner.addWidget(self.topology, 1)
        layout.addWidget(panel, 1)
        return page

    def _build_comparison_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        panel = QFrame()
        panel.setObjectName("chartPanel")
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(14, 12, 14, 10)
        title = QLabel("日前计划与滚动调度策略")
        title.setObjectName("sectionTitle")
        inner.addWidget(title)
        description = QLabel("三套策略使用同一组光伏实测曲线执行：确定性 P50、风险感知 P下界，以及每小时更新预测并重调度的滚动预测策略。")
        description.setObjectName("muted")
        description.setWordWrap(True)
        inner.addWidget(description)
        self.comparison_chart = ComparisonChart()
        inner.addWidget(self.comparison_chart)
        self.comparison_table = QTableWidget(0, 4)
        self.comparison_table.setHorizontalHeaderLabels(["指标", "确定性 P50", "风险感知", "滚动预测 4h"])
        self.comparison_table.verticalHeader().setVisible(False)
        self.comparison_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.comparison_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.comparison_table.setFixedHeight(222)
        inner.addWidget(self.comparison_table)
        layout.addWidget(panel, 1)
        return page

    def _build_table_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        panel = QFrame()
        panel.setObjectName("tablePanel")
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(12, 10, 12, 12)
        title = QLabel("15 分钟调度结果")
        title.setObjectName("sectionTitle")
        inner.addWidget(title)
        self.detail_table = QTableWidget()
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.detail_table.horizontalHeader().setStretchLastSection(True)
        inner.addWidget(self.detail_table, 1)
        layout.addWidget(panel, 1)
        return page

    @staticmethod
    def _section(title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("section")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(7)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        return frame

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _refresh_topology(self) -> None:
        self.topology.update_config(self.config)
        self.param_summary.setText(
            f"光伏 {self.config.pv.capacity_kw:.0f} kW  ·  "
            f"储能 {self.config.battery.capacity_kwh:.0f} kWh\n"
            f"柴油机 {self.config.diesel.max_power_kw:.0f} kW  ·  "
            f"主网 {self.config.grid.import_limit_kw:.0f} kW"
        )

    def _refresh_window_title(self) -> None:
        marker = " *" if self.modified else ""
        self.setWindowTitle(f"{self.project_name}{marker} - Dong 微电网能源管理系统 v1.4")
        if hasattr(self, "project_meta"):
            state = "未保存" if self.modified else "已保存"
            if self.project_path is None and not self.modified:
                state = "新项目"
                self.project_meta.setText(f"{self.project_name}{marker}  |  {state}  |  v1.4")

    def _set_modified(self, modified: bool = True) -> None:
        if self._building:
            return
        self.modified = modified
        self._refresh_window_title()

    def _invalidate_analysis(self) -> None:
        self.monte_carlo_result = None
        self.sensitivity_result = None
        self._analysis_invalidated = True

    def _refresh_source_label(self) -> None:
        metadata = self.data.metadata or {}
        if metadata.get("kind") == "50hertz":
            points = metadata.get("raw_points", "?")
            dst = "；已按夏令时重采样" if metadata.get("dst_resampled") else ""
            self.source_label.setText(
                f"{self.data.source_name}\n原始点数：{points}{dst}\n"
                "预测：过去14天同一时刻中位数（非官方预测）"
            )
        else:
            self.source_label.setText(self.data.source_name)

    def _load_hertz_date(self, date_key: str) -> None:
        if not self.hertz_path or date_key not in self.hertz_dates:
            return
        self.data = load_50hertz_day(self.hertz_path, date_key, self.config)
        self.custom_data = True
        self._refresh_source_label()
        self._invalidate_analysis()
        self._set_modified()
        self.run_dispatch()

    def on_source_changed(self, index: int) -> None:
        if self._building:
            return
        source_key = self.source_combo.currentData()
        if source_key == "50hertz":
            self.scenario_combo.setEnabled(False)
            self.hertz_date_combo.setEnabled(bool(self.hertz_dates))
            if self.hertz_dates:
                self._load_hertz_date(self.hertz_date_combo.currentText())
            return
        self.scenario_combo.setEnabled(True)
        self.hertz_date_combo.setEnabled(False)
        self.custom_data = False
        self.data = generate_typical_day(self.scenario_combo.currentText(), self.config)
        self._refresh_source_label()
        self._invalidate_analysis()
        self._set_modified()
        self.run_dispatch()

    def on_hertz_date_changed(self, date_key: str) -> None:
        if self._building or self.source_combo.currentData() != "50hertz":
            return
        self._load_hertz_date(date_key)

    def on_scenario_changed(self, name: str) -> None:
        if self._building:
            return
        self.custom_data = False
        self.data = generate_typical_day(name, self.config)
        self._refresh_source_label()
        self._invalidate_analysis()
        self._set_modified()
        self.run_dispatch()

    def on_confidence_changed(self, value: int) -> None:
        self.confidence_value.setText(f"{value}%")
        if not self._building:
            self._invalidate_analysis()
            self._set_modified()
            # Debounce the expensive dynamic-programming refresh.
            QTimer.singleShot(220, self._run_if_confidence_still_matches(value))

    def _run_if_confidence_still_matches(self, value: int):
        def callback() -> None:
            if self.confidence_slider.value() == value:
                self.run_dispatch()
        return callback

    def on_strategy_view_changed(self) -> None:
        if self.results:
            self.current_result = self.results[self.strategy_combo.currentData()]
            self._render_current_result()
        self._set_modified()

    def edit_component(self, component: str) -> None:
        dialog = ComponentDialog(self.config, component, self)
        if dialog.exec():
            self.config = dialog.config
            if self.data.metadata.get("kind") == "50hertz" and self.hertz_path:
                self.data = load_50hertz_day(
                    self.hertz_path,
                    self.data.metadata.get("selected_date", self.hertz_dates[0]),
                    self.config,
                )
            elif not self.custom_data:
                self.data = generate_typical_day(self.scenario_combo.currentText(), self.config)
            self._invalidate_analysis()
            self._set_modified()
            self._refresh_topology()
            self.run_dispatch()

    def run_dispatch(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_label.setText("正在计算 96 时段调度...")
        QApplication.processEvents()
        try:
            self.baseline_result = run_baseline(self.data, self.config)
            self.results = run_all_strategies(
                self.data,
                self.config,
                float(self.confidence_slider.value()),
            )
            self.current_result = self.results[self.strategy_combo.currentData()]
            self._render_current_result()
            self._render_comparison()
            self.rolling_page.set_result(self.results["rolling_predictive"])
            animate_sections(self.tabs.currentWidget(), delay_ms=24)
            fade_in(self.dispatch_chart, 210)
            pulse(self.status_label, 150)
            self.lab_page.set_context(
                self.data,
                self.config,
                float(self.confidence_slider.value()),
                clear_results=self._analysis_invalidated,
            )
            if self._analysis_invalidated:
                self._analysis_invalidated = False
            self.report_page.set_results(
                self.baseline_result,
                self.results,
                self.monte_carlo_result,
            )
            self.status_label.setText(f"计算完成  |  数据源：{self.data.source_name}")
        except Exception as exc:
            QMessageBox.critical(self, "调度失败", str(exc))
            self.status_label.setText("计算失败，请检查参数和数据")
        finally:
            QApplication.restoreOverrideCursor()

    def _render_current_result(self) -> None:
        result = self.current_result
        if result is None:
            return
        m = result.metrics
        deterministic = self.results.get("deterministic")
        delta_hint = "实际执行值"
        if deterministic and result.strategy_key in {"risk_aware", "rolling_predictive"}:
            delta = m["total_cost_yuan"] - deterministic.metrics["total_cost_yuan"]
            delta_hint = f"较确定性 {delta:+.1f} 元"
        self.kpi_cost.set_data(f"¥ {m['total_cost_yuan']:.1f}", delta_hint)
        self.kpi_grid.set_data(f"{m['grid_import_kwh']:.1f} kWh", f"峰值 {m['peak_grid_import_kw']:.1f} kW")
        self.kpi_pv.set_data(f"{m['renewable_utilization_pct']:.1f}%", f"弃光 {m['curtailment_kwh']:.1f} kWh")
        self.kpi_soc.set_data(f"{m['final_soc_pct']:.1f}%", "日初日末约束")
        self.kpi_carbon.set_data(f"{m['carbon_kg']:.1f} kg", "电网 + 柴油估算")
        self.strategy_badge.setText(f"{result.strategy_name}  ·  {result.confidence_pct:.0f}%")
        self.dispatch_chart.update_result(result)
        self.replay_page.set_result(result, self.config)
        self._fill_detail_table(result)
        max_error = result.frame.power_balance_error_kw.abs().max()
        self.balance_label.setText(f"功率平衡误差 ≤ {max_error:.3e} kW")

    def _render_comparison(self) -> None:
        if not self.results:
            return
        self.comparison_chart.update_results(self.results)
        deterministic = self.results["deterministic"].metrics
        risk = self.results["risk_aware"].metrics
        rolling = self.results["rolling_predictive"].metrics
        rows = [
            ("实际运行成本 / 元", "total_cost_yuan", 1),
            ("主网购电 / kWh", "grid_import_kwh", 1),
            ("柴油发电 / kWh", "diesel_energy_kwh", 1),
            ("储能吞吐 / kWh", "battery_throughput_kwh", 1),
            ("弃光 / kWh", "curtailment_kwh", 2),
            ("失负荷 / kWh", "unserved_kwh", 3),
        ]
        self.comparison_table.setRowCount(len(rows))
        for row, (label, key, digits) in enumerate(rows):
            values = [label, f"{deterministic[key]:.{digits}f}", f"{risk[key]:.{digits}f}", f"{rolling[key]:.{digits}f}"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.comparison_table.setItem(row, column, item)

    def _fill_detail_table(self, result: DispatchResult) -> None:
        columns = [
            ("time", "时间", 0),
            ("load_kw", "负荷 kW", 2),
            ("pv_forecast_kw", "光伏预测 kW", 2),
            ("rolling_forecast_kw", "滚动预测 kW", 2),
            ("pv_actual_kw", "光伏实测 kW", 2),
            ("battery_kw", "储能 kW", 2),
            ("soc_pct", "SOC %", 1),
            ("diesel_kw", "柴油机 kW", 2),
            ("grid_import_kw", "购电 kW", 2),
            ("grid_export_kw", "上网 kW", 2),
            ("price_yuan_kwh", "电价 元/kWh", 2),
            ("forecast_bias_kw", "EWMA偏差 kW", 2),
            ("grid_loading_pct", "主网负载率 %", 1),
            ("grid_status", "电网状态", 0),
            ("replan_flag", "重优化", 0),
        ]
        frame = result.frame
        self.detail_table.setUpdatesEnabled(False)
        self.detail_table.setRowCount(len(frame))
        self.detail_table.setColumnCount(len(columns))
        self.detail_table.setHorizontalHeaderLabels([item[1] for item in columns])
        for row in range(len(frame)):
            for column, (key, _, digits) in enumerate(columns):
                raw = frame.iloc[row][key]
                if key in {"time", "grid_status", "replan_flag"}:
                    value = str(raw) if key != "replan_flag" else ("是" if int(raw) else "否")
                else:
                    value = f"{float(raw):.{digits}f}"
                item = QTableWidgetItem(value)
                if key != "time":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.detail_table.setItem(row, column, item)
        self.detail_table.setUpdatesEnabled(True)

    def _confirm_project_change(self) -> bool:
        if not self.modified:
            return True
        choice = QMessageBox.question(
            self,
            "保存项目更改",
            f"“{self.project_name}”有尚未保存的修改。是否先保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self.save_project_file()
        return True

    def new_project(self) -> None:
        if not self._confirm_project_change():
            return
        self._building = True
        self.config = default_config()
        self.data = generate_typical_day(SCENARIO_NAMES[0], self.config)
        self.project_name = "未命名微电网项目"
        self.project_path = None
        self.custom_data = False
        self.scenario_combo.setCurrentIndex(0)
        self.source_combo.setCurrentIndex(0)
        self.hertz_date_combo.setEnabled(False)
        self.strategy_combo.setCurrentIndex(0)
        self.confidence_slider.setValue(90)
        self.confidence_value.setText("90%")
        self._refresh_source_label()
        self._building = False
        self._invalidate_analysis()
        self._refresh_topology()
        self.modified = False
        self._refresh_window_title()
        self.run_dispatch()
        self.status_label.setText("已新建项目")

    def _build_project_document(self) -> ProjectDocument:
        return ProjectDocument(
            project_name=self.project_name,
            config=deepcopy(self.config),
            scenario=deepcopy(self.data),
            strategy_key=self.strategy_combo.currentData(),
            confidence_pct=float(self.confidence_slider.value()),
        )

    def save_project_file(self, checked: bool = False, save_as: bool = False) -> bool:
        target = self.project_path
        if save_as or target is None:
            default_name = self.project_name if self.project_name != "未命名微电网项目" else "Dong示例项目"
            path, _ = QFileDialog.getSaveFileName(
                self,
                "保存 Dong 项目",
                str(self.project_root / "sample_data" / f"{default_name}.dong"),
                "Dong 项目 (*.dong)",
            )
            if not path:
                return False
            target = Path(path)
        try:
            if self.project_name == "未命名微电网项目":
                self.project_name = target.stem
            saved = save_project(self._build_project_document(), target)
            self.project_path = saved
            self.modified = False
            self._refresh_window_title()
            self.status_label.setText(f"项目已保存：{saved.name}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "保存项目失败", str(exc))
            return False

    def open_project_file(self) -> None:
        if not self._confirm_project_change():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开 Dong 项目",
            str(self.project_root / "sample_data"),
            "Dong 项目 (*.dong)",
        )
        if not path:
            return
        try:
            document = load_project(path)
        except Exception as exc:
            QMessageBox.warning(self, "打开项目失败", str(exc))
            return

        self._building = True
        self.config = document.config
        self.data = document.scenario
        self.project_name = document.project_name
        self.project_path = Path(path)
        self.custom_data = True
        metadata_kind = self.data.metadata.get("kind") if self.data.metadata else None
        source_index = self.source_combo.findData("50hertz" if metadata_kind == "50hertz" else "builtin")
        if source_index >= 0:
            self.source_combo.setCurrentIndex(source_index)
        if metadata_kind == "50hertz":
            selected = str(self.data.metadata.get("selected_date", ""))
            date_index = self.hertz_date_combo.findText(selected)
            if date_index >= 0:
                self.hertz_date_combo.setCurrentIndex(date_index)
        strategy_index = self.strategy_combo.findData(document.strategy_key)
        self.strategy_combo.setCurrentIndex(max(0, strategy_index))
        self.confidence_slider.setValue(int(round(document.confidence_pct)))
        self.confidence_value.setText(f"{document.confidence_pct:.0f}%")
        self._refresh_source_label()
        self._building = False
        self._invalidate_analysis()
        self._refresh_topology()
        self.modified = False
        self._refresh_window_title()
        self.run_dispatch()
        self.status_label.setText(f"已打开项目：{self.project_path.name}")

    def _on_monte_carlo_completed(self, result) -> None:
        self.monte_carlo_result = result
        self.report_page.set_monte_carlo(result)
        self.status_label.setText(f"Monte Carlo 完成：{result.settings.sample_count} 个场景")

    def _on_sensitivity_completed(self, result) -> None:
        self.sensitivity_result = result
        self.status_label.setText(f"容量敏感性分析完成：{result.settings.points} 个方案点")

    def export_report(self) -> None:
        if self.baseline_result is None or not self.results:
            QMessageBox.information(self, "尚无结果", "请先运行调度。")
            return
        base = self.project_root / "output"
        base.mkdir(parents=True, exist_ok=True)
        directory = QFileDialog.getExistingDirectory(self, "选择报告包保存位置", str(base))
        if not directory:
            return
        target = Path(directory) / f"Dong_report_{datetime.now():%Y%m%d_%H%M%S}"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            bundle = export_report_bundle(
                target,
                self.project_name,
                self.data,
                self.config,
                self.baseline_result,
                self.results,
                self.strategy_combo.currentData(),
                self.monte_carlo_result,
                self.sensitivity_result,
            )
            self.status_label.setText(f"报告包已导出：{bundle.directory.name}")
            QMessageBox.information(self, "报告导出完成", f"报告包已保存到：\n{bundle.directory}")
        except Exception as exc:
            QMessageBox.critical(self, "导出报告失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def prepare_screenshot_tab(self, tab_name: str) -> int:
        """Select and prepare a tab for CLI screenshot smoke tests."""

        indices = {
            "overview": 0,
            "replay": 1,
            "rolling": 2,
            "topology": 3,
            "comparison": 4,
            "lab": 5,
            "details": 6,
            "report": 7,
        }
        self.tabs.setCurrentIndex(indices.get(tab_name, 0))
        if tab_name == "replay":
            self.replay_page.select_midday()
        elif tab_name in {"lab", "report"} and self.lab_page.monte_carlo_result is None:
            self.lab_page.mc_samples.setValue(20)
            self.lab_page.start_monte_carlo()
            return 18000
        return 5500

    def import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 96 时段场景数据",
            str(self.project_root / "sample_data"),
            "CSV 文件 (*.csv)",
        )
        if not path:
            return
        try:
            self.data = load_scenario_csv(path, self.config)
            self.custom_data = True
            if self.data.metadata.get("kind") == "50hertz":
                source_index = self.source_combo.findData("50hertz")
                if source_index >= 0:
                    self._building = True
                    self.source_combo.setCurrentIndex(source_index)
                    date_index = self.hertz_date_combo.findText(str(self.data.metadata.get("selected_date", "")))
                    if date_index >= 0:
                        self.hertz_date_combo.setCurrentIndex(date_index)
                    self._building = False
            self._refresh_source_label()
            self._invalidate_analysis()
            self._set_modified()
            self.run_dispatch()
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    def export_results(self) -> None:
        if self.current_result is None:
            QMessageBox.information(self, "尚无结果", "请先运行调度。")
            return
        default_name = f"dispatch_{self.current_result.strategy_key}_{datetime.now():%Y%m%d_%H%M}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前调度结果",
            str(self.project_root / "output" / default_name),
            "CSV 文件 (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        csv_path = export_dispatch_csv(self.current_result, path)
        json_path = export_summary_json(self.current_result, csv_path.with_suffix(".json"))
        self.status_label.setText(f"已导出：{csv_path.name} 和 {json_path.name}")
        QMessageBox.information(self, "导出完成", f"已保存：\n{csv_path}\n{json_path}")

    def show_model_help(self) -> None:
        AboutModelDialog(self).exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_project_change():
            event.ignore()
            return
        self.replay_page.pause()
        self.lab_page.close_threads()
        event.accept()
