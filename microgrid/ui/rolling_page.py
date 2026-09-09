"""Rolling forecast centre for the offline real-time dispatch replay."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..scheduler import DispatchResult
from .charts import _style_axis
from .theme import COLORS


class RollingChart(FigureCanvasQTAgg):
    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(8.6, 4.4), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(300)

    def update_result(self, result: DispatchResult) -> None:
        frame = result.frame
        x = np.arange(len(frame)) / 4.0
        self.figure.clear()
        axes = self.figure.subplots(2, 1, sharex=True, gridspec_kw={"hspace": 0.28})
        axes[0].plot(x, frame.pv_actual_kw, color=COLORS["pv"], lw=1.5, label="光伏实测")
        axes[0].plot(x, frame.rolling_forecast_kw, color="#2B6CB0", lw=1.7, label="滚动修正预测")
        axes[0].plot(x, frame.pv_forecast_kw, color="#99A5AE", lw=1.0, ls="--", label="日前预测")
        axes[0].fill_between(x, frame.rolling_lower_kw, frame.rolling_forecast_kw, color="#DDEFE9", alpha=0.7, label="修正下界")
        for mark in frame.index[frame.replan_flag.astype(bool)].to_numpy() / 4.0:
            axes[0].axvline(mark, color="#E4B344", lw=0.8, alpha=0.55)
        axes[0].set_ylabel("kW")
        axes[0].set_title("日前预测与滚动修正", loc="left", fontsize=10, fontweight="bold")
        axes[0].legend(frameon=False, fontsize=7.5, ncols=4, loc="upper left")
        axes[1].step(x, frame.grid_loading_pct, where="mid", color="#2B6CB0", lw=1.5, label="主网负载率")
        axes[1].axhline(82, color="#C46731", lw=1.0, ls="--", label="82% 判断线")
        axes[1].plot(x, frame.forecast_bias_kw, color="#18785C", lw=1.15, label="EWMA 偏差 / kW")
        axes[1].set_ylabel("% / kW")
        axes[1].set_xlabel("时刻 / h")
        axes[1].set_title("主网负载率与预测偏差", loc="left", fontsize=10, fontweight="bold")
        axes[1].legend(frameon=False, fontsize=7.5, ncols=3, loc="upper left")
        axes[1].set_xlim(0, 23.75)
        for axis in axes:
            _style_axis(axis)
        self.figure.subplots_adjust(left=0.07, right=0.98, top=0.94, bottom=0.10)
        self.draw_idle()


class RollingPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result: DispatchResult | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel("滚动调度中心")
        title.setObjectName("sectionTitle")
        badge = QLabel("离线滚动仿真 · 4h 预测窗口 · 每小时重规划")
        badge.setStyleSheet("color:#18785C;background:#E6F2EE;padding:4px 8px;border-radius:3px;font-weight:700;")
        badge.setToolTip("模型只使用已经发生的光伏偏差，不代表真实硬件在线控制")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(badge)
        layout.addLayout(heading)
        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        self.mode = self._card("当前控制模式")
        self.status = self._card("电网状态")
        self.bias = self._card("当前 EWMA 偏差")
        self.replans = self._card("重优化次数")
        for idx, card in enumerate((self.mode, self.status, self.bias, self.replans)):
            cards.addWidget(card, 0, idx)
        layout.addLayout(cards)
        panel = QFrame()
        panel.setObjectName("chartPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 6, 8, 4)
        self.chart = RollingChart()
        panel_layout.addWidget(self.chart)
        layout.addWidget(panel, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["时刻", "滚动预测 kW", "EWMA 偏差 kW", "电网判断 / 控制原因"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setFixedHeight(170)
        layout.addWidget(self.table)

    def _card(self, title: str) -> QLabel:
        card = QLabel(f"{title}\n--")
        card.setObjectName("rollingCard")
        card.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        card.setMinimumHeight(48)
        card.setStyleSheet("QLabel#rollingCard{background:#FFFFFF;border:1px solid #DCE5E8;border-left:4px solid #18785C;border-radius:4px;padding:7px 10px;color:#273442;font-weight:700;}")
        return card

    def set_result(self, result: DispatchResult) -> None:
        self.result = result
        frame = result.frame
        self.chart.update_result(result)
        latest = frame.iloc[0]
        self.mode.setText(f"当前控制模式\n{latest.control_mode}")
        self.status.setText(f"电网状态\n{latest.grid_status}")
        self.bias.setText(f"当前 EWMA 偏差\n{latest.forecast_bias_kw:+.1f} kW")
        self.replans.setText(f"重优化次数\n{int(frame.replan_flag.sum())} 次")
        indices = list(frame.index[frame.replan_flag.astype(bool)])[-8:]
        self.table.setRowCount(len(indices))
        for row, idx in enumerate(indices):
            item = frame.iloc[idx]
            values = (str(item.time), f"{item.rolling_forecast_kw:.1f}", f"{item.forecast_bias_kw:+.1f}", f"{item.grid_status} · {item.replan_reason}")
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col in (1, 2):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)
