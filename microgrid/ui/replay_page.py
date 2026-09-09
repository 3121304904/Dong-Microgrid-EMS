"""Interactive replay page for one simulated dispatch day."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSlider,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import INTERVAL_HOURS, MicrogridConfig
from ..scheduler import DispatchResult
from .theme import COLORS


class ReplayFlowView(QWidget):
    """Paint a compact live topology with directional power-flow arrows."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 330)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)
        self._values = {
            "pv": 0.0,
            "battery": 0.0,
            "diesel": 0.0,
            "grid": 0.0,
            "load": 0.0,
            "soc": 0.0,
        }

    def set_values(self, **values: float) -> None:
        self._values.update(values)
        self.update()

    @staticmethod
    def _node_rect(center: QPointF) -> QRectF:
        return QRectF(center.x() - 72, center.y() - 30, 144, 60)

    def _draw_node(
        self,
        painter: QPainter,
        center: QPointF,
        title: str,
        value: str,
        color: str,
    ) -> None:
        rect = self._node_rect(center)
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.setPen(QPen(QColor("#CCD6DC"), 1.2))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color)))
        painter.drawRoundedRect(QRectF(rect.left() + 9, rect.top() + 10, 7, 40), 3, 3)
        painter.setPen(QPen(QColor("#17212B")))
        font = QFont("Microsoft YaHei UI", 9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left() + 24, rect.top() + 8, 111, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        painter.setPen(QPen(QColor("#637083")))
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left() + 24, rect.top() + 30, 111, 21),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            value,
        )

    def _draw_flow(
        self,
        painter: QPainter,
        start: QPointF,
        end: QPointF,
        magnitude: float,
        color: str,
        label: str,
    ) -> None:
        power = abs(float(magnitude))
        width = 1.4 + min(5.4, power / 32.0)
        line_color = QColor(color if power > 0.05 else "#C7D0D5")
        painter.setPen(QPen(line_color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(start, end)

        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max(1.0, math.hypot(dx, dy))
        ux, uy = dx / length, dy / length
        point = QPointF(start.x() + dx * 0.56, start.y() + dy * 0.56)
        size = 7.0 + min(4.0, width)
        left = QPointF(point.x() - ux * size - uy * size * 0.62, point.y() - uy * size + ux * size * 0.62)
        right = QPointF(point.x() - ux * size + uy * size * 0.62, point.y() - uy * size - ux * size * 0.62)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(line_color))
        painter.drawPolygon(QPolygonF([point, left, right]))

        font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        label_width = metrics.horizontalAdvance(label) + 10
        label_rect = QRectF(
            start.x() + dx * 0.36 - label_width / 2,
            start.y() + dy * 0.36 - 10,
            label_width,
            20,
        )
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.setPen(QPen(QColor("#DDE4E8"), 0.8))
        painter.drawRoundedRect(label_rect, 3, 3)
        painter.setPen(QPen(QColor("#384755")))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        width, height = self.width(), self.height()
        pv = QPointF(width * 0.17, height * 0.19)
        grid = QPointF(width * 0.83, height * 0.19)
        battery = QPointF(width * 0.17, height * 0.75)
        diesel = QPointF(width * 0.83, height * 0.75)
        bus = QPointF(width * 0.50, height * 0.45)
        load = QPointF(width * 0.50, height * 0.82)

        values = self._values
        self._draw_flow(painter, pv, bus, values["pv"], COLORS["pv"], f"{values['pv']:.1f} kW")
        if values["grid"] >= 0:
            self._draw_flow(painter, grid, bus, values["grid"], COLORS["grid"], f"{values['grid']:.1f} kW")
        else:
            self._draw_flow(painter, bus, grid, -values["grid"], COLORS["grid"], f"上网 {-values['grid']:.1f} kW")
        if values["battery"] >= 0:
            self._draw_flow(painter, battery, bus, values["battery"], COLORS["battery"], f"放电 {values['battery']:.1f}")
        else:
            self._draw_flow(painter, bus, battery, -values["battery"], COLORS["battery"], f"充电 {-values['battery']:.1f}")
        self._draw_flow(painter, diesel, bus, values["diesel"], COLORS["diesel"], f"{values['diesel']:.1f} kW")
        self._draw_flow(painter, bus, load, values["load"], "#273442", f"{values['load']:.1f} kW")

        painter.setBrush(QBrush(QColor("#173B36")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(bus, 8, 8)
        self._draw_node(painter, pv, "光伏阵列", f"实际 {values['pv']:.1f} kW", COLORS["pv"])
        self._draw_node(painter, grid, "公共电网", f"净功率 {values['grid']:.1f} kW", COLORS["grid"])
        self._draw_node(painter, battery, "储能系统", f"SOC {values['soc']:.1f}%", COLORS["battery"])
        self._draw_node(painter, diesel, "柴油发电机", f"出力 {values['diesel']:.1f} kW", COLORS["diesel"])
        self._draw_node(painter, load, "园区综合负荷", f"需求 {values['load']:.1f} kW", "#273442")


class ReplayMetric(QWidget):
    def __init__(self, title: str, color: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 5)
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("muted")
        self.value_label = QLabel("--")
        self.value_label.setStyleSheet(f"color:{color};font-size:16px;font-weight:700;")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class ReplayPage(QWidget):
    """Playback controls, live values, power topology, and event history."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result: DispatchResult | None = None
        self.config: MicrogridConfig | None = None
        self.current_index = 0
        self._events: list[tuple[int, str, str]] = []
        self._cumulative_cost = np.zeros(96)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step_forward)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)

        heading = QHBoxLayout()
        title = QLabel("实时仿真回放")
        title.setObjectName("sectionTitle")
        self.time_label = QLabel("--:--  ·  第 0/96 时段")
        self.time_label.setStyleSheet("font-size:15px;font-weight:700;color:#273442;")
        badge = QLabel("离线仿真数据")
        badge.setStyleSheet("color:#9A4B1F;background:#FCEBDD;padding:4px 8px;border-radius:3px;font-weight:700;")
        badge.setToolTip("本页回放调度模型生成的数据，不表示真实设备在线状态")
        heading.addWidget(title)
        heading.addSpacing(12)
        heading.addWidget(self.time_label)
        heading.addStretch()
        heading.addWidget(badge)
        layout.addLayout(heading)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        self.play_button = self._tool_button(QStyle.StandardPixmap.SP_MediaPlay, "播放仿真回放")
        self.pause_button = self._tool_button(QStyle.StandardPixmap.SP_MediaPause, "暂停回放")
        self.step_button = self._tool_button(QStyle.StandardPixmap.SP_MediaSkipForward, "前进一个 15 分钟时段")
        self.reset_button = self._tool_button(QStyle.StandardPixmap.SP_BrowserReload, "复位到 00:00")
        self.play_button.clicked.connect(self.play)
        self.pause_button.clicked.connect(self.pause)
        self.step_button.clicked.connect(self.step_forward)
        self.reset_button.clicked.connect(self.reset)
        controls.addWidget(self.play_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.step_button)
        controls.addWidget(self.reset_button)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 95)
        self.position_slider.setToolTip("拖动到任意 15 分钟时段")
        self.position_slider.valueChanged.connect(self.set_index)
        controls.addWidget(self.position_slider, 1)
        controls.addWidget(QLabel("速度"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1x", "4x", "8x", "16x"])
        self.speed_combo.setCurrentText("4x")
        self.speed_combo.setFixedWidth(72)
        self.speed_combo.setToolTip("调整仿真回放速度")
        self.speed_combo.currentTextChanged.connect(self._update_timer_interval)
        controls.addWidget(self.speed_combo)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        flow_panel = QFrame()
        flow_panel.setObjectName("chartPanel")
        flow_layout = QVBoxLayout(flow_panel)
        flow_layout.setContentsMargins(10, 8, 10, 8)
        self.flow_view = ReplayFlowView()
        flow_layout.addWidget(self.flow_view, 1)
        splitter.addWidget(flow_panel)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(6, 0, 0, 0)
        side_layout.setSpacing(7)
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(1)
        self.metrics = {
            "load": ReplayMetric("当前负荷", "#273442"),
            "pv": ReplayMetric("实际光伏", COLORS["pv"]),
            "battery": ReplayMetric("储能功率", COLORS["battery"]),
            "diesel": ReplayMetric("柴油机", COLORS["diesel"]),
            "grid": ReplayMetric("主网净功率", COLORS["grid"]),
            "soc": ReplayMetric("储能 SOC", COLORS["battery"]),
            "price": ReplayMetric("当前电价", COLORS["diesel"]),
            "cost": ReplayMetric("累计运行成本", COLORS["grid"]),
        }
        for index, metric in enumerate(self.metrics.values()):
            metrics.addWidget(metric, index // 2, index % 2)
        side_layout.addLayout(metrics)
        event_title = QHBoxLayout()
        label = QLabel("运行事件")
        label.setObjectName("sectionTitle")
        self.event_count = QLabel("0 条")
        self.event_count.setObjectName("muted")
        event_title.addWidget(label)
        event_title.addStretch()
        event_title.addWidget(self.event_count)
        side_layout.addLayout(event_title)
        self.event_table = QTableWidget(0, 3)
        self.event_table.setHorizontalHeaderLabels(["时刻", "类型", "说明"])
        self.event_table.verticalHeader().setVisible(False)
        self.event_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.event_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        side_layout.addWidget(self.event_table, 1)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 360])
        layout.addWidget(splitter, 1)
        self._set_controls_enabled(False)

    def _tool_button(self, icon: QStyle.StandardPixmap, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(tooltip)
        button.setFixedSize(34, 34)
        return button

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (self.play_button, self.pause_button, self.step_button, self.reset_button, self.position_slider, self.speed_combo):
            widget.setEnabled(enabled)

    def set_result(self, result: DispatchResult, config: MicrogridConfig) -> None:
        self.pause()
        self.result = result
        self.config = config
        frame = result.frame
        interval_cost = INTERVAL_HOURS * (
            frame.grid_import_kw.to_numpy() * frame.price_yuan_kwh.to_numpy()
            + frame.diesel_kw.to_numpy() * config.diesel.fuel_cost_yuan_kwh
            + frame.battery_kw.abs().to_numpy() * config.battery.cycle_cost_yuan_kwh
            + frame.unserved_kw.to_numpy() * 20.0
            + frame.curtailment_kw.to_numpy() * 0.01
            - frame.grid_export_kw.to_numpy() * config.grid.sell_price_yuan_kwh
        )
        self._cumulative_cost = np.cumsum(interval_cost)
        self._events = self._build_events()
        self._set_controls_enabled(True)
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(0)
        self.position_slider.blockSignals(False)
        self.set_index(0)

    def _build_events(self) -> list[tuple[int, str, str]]:
        if self.result is None or self.config is None:
            return []
        frame = self.result.frame
        events: list[tuple[int, str, str]] = []
        previous_diesel = 0.0
        low_soc_active = high_grid_active = curtailment_active = False
        for index, row in frame.iterrows():
            deviation = float(row.pv_actual_kw - row.pv_forecast_kw)
            threshold = max(8.0, float(row.pv_forecast_kw) * 0.22)
            if abs(deviation) > threshold:
                state = "高于" if deviation > 0 else "低于"
                events.append((index, "光伏偏差", f"实测{state}预测 {abs(deviation):.1f} kW"))
            diesel = float(row.diesel_kw)
            if previous_diesel <= 0.05 < diesel:
                events.append((index, "柴油机", f"启动，出力 {diesel:.1f} kW"))
            elif previous_diesel > 0.05 >= diesel:
                events.append((index, "柴油机", "停止运行"))
            previous_diesel = diesel

            low_soc = float(row.soc_pct) <= self.config.battery.min_soc * 100.0 + 3.0
            if low_soc and not low_soc_active:
                events.append((index, "SOC 低位", f"SOC 降至 {row.soc_pct:.1f}%"))
            low_soc_active = low_soc
            high_grid = float(row.grid_import_kw) >= self.config.grid.import_limit_kw * 0.80
            if high_grid and not high_grid_active:
                events.append((index, "主网高负荷", f"购电达到 {row.grid_import_kw:.1f} kW"))
            high_grid_active = high_grid
            curtailment = float(row.curtailment_kw) > 1e-6
            if curtailment and not curtailment_active:
                events.append((index, "弃光", f"弃光功率 {row.curtailment_kw:.1f} kW"))
            curtailment_active = curtailment
            if float(row.unserved_kw) > 1e-6:
                events.append((index, "失负荷", f"未供电 {row.unserved_kw:.1f} kW"))
        return events

    def _update_timer_interval(self) -> None:
        speed = int(self.speed_combo.currentText().rstrip("x"))
        self.timer.setInterval(max(55, int(800 / speed)))

    def play(self) -> None:
        if self.result is None:
            return
        if self.current_index >= 95:
            self.set_index(0)
        self._update_timer_interval()
        self.timer.start()

    def pause(self) -> None:
        self.timer.stop()

    def reset(self) -> None:
        self.pause()
        self.set_index(0)

    def step_forward(self) -> None:
        if self.result is None:
            return
        if self.current_index >= 95:
            self.pause()
            return
        self.set_index(self.current_index + 1)

    def set_index(self, index: int) -> None:
        if self.result is None:
            return
        self.current_index = max(0, min(95, int(index)))
        if self.position_slider.value() != self.current_index:
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(self.current_index)
            self.position_slider.blockSignals(False)
        row = self.result.frame.iloc[self.current_index]
        time_text = str(row.time)
        self.time_label.setText(f"{time_text}  ·  第 {self.current_index + 1}/96 时段")
        battery_label = f"{row.battery_kw:+.1f} kW"
        grid_net = float(row.grid_import_kw - row.grid_export_kw)
        self.metrics["load"].set_value(f"{row.load_kw:.1f} kW")
        self.metrics["pv"].set_value(f"{row.pv_actual_kw:.1f} kW")
        self.metrics["battery"].set_value(battery_label)
        self.metrics["diesel"].set_value(f"{row.diesel_kw:.1f} kW")
        self.metrics["grid"].set_value(f"{grid_net:+.1f} kW")
        self.metrics["soc"].set_value(f"{row.soc_pct:.1f}%")
        self.metrics["price"].set_value(f"¥ {row.price_yuan_kwh:.2f}/kWh")
        self.metrics["cost"].set_value(f"¥ {self._cumulative_cost[self.current_index]:.1f}")
        self.flow_view.set_values(
            pv=float(row.pv_actual_kw - row.curtailment_kw),
            battery=float(row.battery_kw),
            diesel=float(row.diesel_kw),
            grid=grid_net,
            load=float(row.load_kw - row.unserved_kw),
            soc=float(row.soc_pct),
        )
        self._render_events()

    def _render_events(self) -> None:
        visible = [event for event in self._events if event[0] <= self.current_index]
        visible = visible[-30:]
        self.event_table.setRowCount(len(visible))
        assert self.result is not None
        for row_index, (time_index, event_type, message) in enumerate(visible):
            values = (str(self.result.frame.iloc[time_index].time), event_type, message)
            for column, value in enumerate(values):
                self.event_table.setItem(row_index, column, QTableWidgetItem(value))
        self.event_count.setText(f"{len([e for e in self._events if e[0] <= self.current_index])} 条")
        if visible:
            self.event_table.scrollToBottom()

    def select_midday(self) -> None:
        """Convenience used by automated screenshots and live demonstrations."""

        self.set_index(52)
