"""Interactive, explainable rolling forecast replay page."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSlider, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..scheduler import DispatchResult
from .charts import _style_axis
from .theme import COLORS


class RollingChart(FigureCanvasQTAgg):
    """Full-day chart with an animated current-time marker and horizon shading."""

    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(9.5, 4.5), dpi=100, facecolor="#FFFFFF")
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(300)
        self._result: DispatchResult | None = None
        self._index = 0
        self._draw()

    def update_result(self, result: DispatchResult, index: int = 0) -> None:
        self._result = result
        self._index = max(0, min(95, int(index)))
        self._draw()

    def set_index(self, index: int) -> None:
        self._index = max(0, min(95, int(index)))
        self._draw()

    def _draw(self) -> None:
        self.figure.clear()
        axes = self.figure.subplots(2, 1, sharex=True, gridspec_kw={"hspace": 0.30})
        if self._result is None:
            self.draw_idle()
            return
        frame = self._result.frame
        x = np.arange(len(frame)) / 4.0
        current = self._index
        ax0, ax1 = axes
        ax0.plot(x, frame.pv_actual_kw, color=COLORS["pv"], lw=1.45, label="光伏实测")
        ax0.plot(x, frame.pv_forecast_kw, color="#98A4AD", lw=1.05, ls="--", label="日前 P50")
        ax0.plot(x, frame.rolling_forecast_kw, color="#2B6CB0", lw=1.8, label="滚动预测")
        sigma = frame.forecast_sigma_kw.to_numpy() if "forecast_sigma_kw" in frame else np.zeros(len(frame))
        ax0.fill_between(x, np.maximum(0, frame.rolling_forecast_kw.to_numpy()-sigma), frame.rolling_forecast_kw.to_numpy()+sigma, color="#DDEFE9", alpha=0.58, label="误差带")
        ax0.axvline(x[current], color="#C46731", lw=1.8, alpha=0.95)
        horizon_end = int(frame.horizon_end_index.iloc[current]) if "horizon_end_index" in frame else min(95,current+15)
        if horizon_end >= current:
            ax0.axvspan(x[current], x[horizon_end], color="#E4B344", alpha=0.12, label="当前预测窗")
        ax0.scatter([x[current]], [frame.pv_actual_kw.iloc[current]], color="#C46731", s=26, zorder=5)
        ax0.set_ylabel("kW")
        ax0.set_title("滚动预测回放：过去观测、当前时刻与未来 4 小时", loc="left", fontsize=10, fontweight="bold")
        ax0.legend(frameon=False, fontsize=7.2, ncols=4, loc="upper left")
        ax1.step(x, frame.grid_loading_pct, where="mid", color="#2B6CB0", lw=1.45, label="主网负载率")
        ax1.axhline(82, color="#C46731", lw=1.0, ls="--", label="82% 判断线")
        ax1.plot(x, frame.forecast_bias_kw, color="#18785C", lw=1.15, label="EWMA 偏差")
        ax1.plot(x, frame.forecast_error_kw, color="#7B61A8", lw=0.95, alpha=0.68, label="上一时段误差") if "forecast_error_kw" in frame else None
        ax1.axvline(x[current], color="#C46731", lw=1.8, alpha=0.95)
        ax1.set_ylabel("% / kW")
        ax1.set_xlabel("时间 / h")
        ax1.set_title("电网判断与误差状态", loc="left", fontsize=10, fontweight="bold")
        ax1.legend(frameon=False, fontsize=7.2, ncols=4, loc="upper left")
        ax1.set_xlim(0, 23.75)
        for axis in axes:
            _style_axis(axis)
        self.figure.subplots_adjust(left=0.065, right=0.98, top=0.94, bottom=0.10)
        self.draw_idle()


class RollingStrategyExplainer(QFrame):
    """Five-step flow plus equations used by the rolling controller."""

    # Keep formula captions in plain ASCII. Some Windows fallback fonts lack
    # mathematical subscript/accent glyphs and render them as square boxes.
    STEPS = (("01", "读取新实测", "error = P_actual - P_day", "#2B6CB0"), ("02", "EWMA 更新", "bias = 0.35 error + 0.65 old_bias", "#18785C"), ("03", "修正预测", "P_roll = P_day + bias x decay", "#D69B21"), ("04", "滚动 DP", "enumerate E(t) to E(t+1)", "#C46731"), ("05", "执行窗口", "只执行当前 1h", "#7B61A8"))

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("rollingExplainer")
        self.setToolTip("离线滚动仿真只使用当前时刻以前的实测光伏数据")
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 8, 12, 8); layout.setSpacing(5)
        head = QHBoxLayout(); title=QLabel("滚动预测逻辑"); title.setObjectName("sectionTitle"); self.example=QLabel("每小时重算未来 4 小时，只执行当前 1 小时"); self.example.setObjectName("muted"); self.example.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); head.addWidget(title); head.addStretch(); head.addWidget(self.example); layout.addLayout(head)
        flow=QHBoxLayout(); flow.setSpacing(5)
        for i,(number, title_text, detail, color) in enumerate(self.STEPS):
            box=QFrame(); box.setObjectName("rollingStep"); box.setStyleSheet(f"QFrame#rollingStep{{background:#FFFFFF;border:1px solid #DCE5E8;border-top:3px solid {color};border-radius:4px;}}")
            row=QHBoxLayout(box); row.setContentsMargins(7,5,7,5); row.setSpacing(6)
            marker=QLabel(number); marker.setAlignment(Qt.AlignmentFlag.AlignCenter); marker.setFixedSize(27,27); marker.setStyleSheet(f"background:{color};color:#FFFFFF;border-radius:13px;font-weight:700;")
            txt=QLabel(f"{title_text}\n{detail}"); txt.setStyleSheet("color:#273442;font-size:11px;font-weight:600;"); txt.setWordWrap(True); row.addWidget(marker); row.addWidget(txt,1); flow.addWidget(box,1)
            if i<4: arrow=QLabel("→"); arrow.setObjectName("rollingArrow"); arrow.setAlignment(Qt.AlignmentFlag.AlignCenter); arrow.setFixedWidth(15); flow.addWidget(arrow)
        layout.addLayout(flow)

    def set_example(self, result: DispatchResult) -> None:
        trace = result.diagnostics.get("rolling_trace", []) if result.diagnostics else []
        if trace:
            first=trace[0]; self.example.setText(f"首个重算窗口：{first['start_index']/4:.2f}–{(first['end_index']+1)/4:.2f} h · 偏差 {first['bias_kw']:+.1f} kW · σ {first['sigma_kw']:.1f} kW")


class RollingPage(QWidget):
    """Animated playback of the rolling forecast and receding-horizon dispatch."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result: DispatchResult | None = None
        self.current_index = 0
        self.timer = QTimer(self); self.timer.timeout.connect(self.step_forward)
        self._build_ui()

    def _build_ui(self) -> None:
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget(); layout=QVBoxLayout(content); layout.setContentsMargins(0,10,0,0); layout.setSpacing(8)
        heading=QHBoxLayout(); title=QLabel("滚动调度中心"); title.setObjectName("sectionTitle"); self.time_label=QLabel("--:-- · 第 0/96 时段"); self.time_label.setStyleSheet("font-size:14px;font-weight:700;color:#273442;"); badge=QLabel("离线滚动仿真"); badge.setStyleSheet("color:#18785C;background:#E6F2EE;padding:4px 8px;border-radius:3px;font-weight:700;"); badge.setToolTip("展示算法回放，不代表真实硬件在线控制"); heading.addWidget(title); heading.addSpacing(14); heading.addWidget(self.time_label); heading.addStretch(); heading.addWidget(badge); layout.addLayout(heading)
        controls=QHBoxLayout(); controls.setSpacing(6)
        self.play_btn=QPushButton("▶ 播放"); self.pause_btn=QPushButton("Ⅱ 暂停"); self.step_btn=QPushButton("⏭ 单步"); self.reset_btn=QPushButton("↺ 复位")
        for b in (self.play_btn,self.pause_btn,self.step_btn,self.reset_btn): b.setToolTip("滚动预测演示控制"); controls.addWidget(b)
        self.play_btn.clicked.connect(self.play); self.pause_btn.clicked.connect(self.pause); self.step_btn.clicked.connect(self.step_forward); self.reset_btn.clicked.connect(self.reset)
        controls.addWidget(QLabel("时间游标")); self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(0,95); self.slider.valueChanged.connect(self.set_index); controls.addWidget(self.slider,1)
        controls.addWidget(QLabel("速度")); self.speed=QComboBox(); self.speed.addItems(["1x","4x","8x","16x"]); self.speed.setCurrentText("4x"); self.speed.setFixedWidth(62); self.speed.currentTextChanged.connect(self._update_interval); controls.addWidget(self.speed); layout.addLayout(controls)
        self.explainer=RollingStrategyExplainer(); layout.addWidget(self.explainer)
        cards=QGridLayout(); cards.setHorizontalSpacing(8); self.cards={k:self._card(title) for k,title in (("mode","控制模式"),("status","电网状态"),("bias","EWMA 偏差"),("sigma","误差 σ"),("window","当前预测窗"),("action","当前动作"))};
        for i,k in enumerate(self.cards): cards.addWidget(self.cards[k], i // 3, i % 3)
        layout.addLayout(cards)
        panel=QFrame(); panel.setObjectName("chartPanel"); pl=QVBoxLayout(panel); pl.setContentsMargins(8,5,8,4); self.chart=RollingChart(); pl.addWidget(self.chart); layout.addWidget(panel,1)
        formula=QFrame(); formula.setObjectName("rollingExplainer"); fl=QHBoxLayout(formula); fl.setContentsMargins(12,7,12,7); self.formula=QLabel("误差 error = 实测光伏 - 日前预测\nEWMA bias = 0.35 x error + 0.65 x old_bias\n滚动预测 P_roll(t+k) = clip(P_day + bias x 0.82^(k/4))"); self.formula.setStyleSheet("color:#273442;font-size:12px;font-weight:600;"); fl.addWidget(self.formula); self.matrix=QLabel("DP 状态：E(t)\n转移：E(t) -> E(t+1)\n约束：SOC、P_charge、P_discharge"); self.matrix.setStyleSheet("color:#637083;font-size:12px;"); fl.addWidget(self.matrix); layout.addWidget(formula)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["时刻","误差","EWMA","预测窗","动作 / 判断"]); self.table.verticalHeader().setVisible(False); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.table.horizontalHeader().setStretchLastSection(True); self.table.setFixedHeight(145); layout.addWidget(self.table)
        scroll.setWidget(content); outer.addWidget(scroll); self._set_enabled(False)

    def _card(self,title:str)->QLabel:
        card=QLabel(f"{title}\n--"); card.setObjectName("rollingCard"); card.setMinimumHeight(44); card.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); return card

    def _set_enabled(self,enabled:bool)->None:
        for w in (self.play_btn,self.pause_btn,self.step_btn,self.reset_btn,self.slider,self.speed): w.setEnabled(enabled)

    def _update_interval(self)->None:
        speed=int(self.speed.currentText().rstrip("x")); self.timer.setInterval(max(55,int(800/speed)))

    def set_result(self,result:DispatchResult)->None:
        self.pause(); self.result=result; self.current_index=0; self._set_enabled(True); self.explainer.set_example(result); self.chart.update_result(result,0); self.slider.blockSignals(True); self.slider.setValue(0); self.slider.blockSignals(False); self.set_index(0)

    def play(self)->None:
        if self.result is None:return
        if self.current_index>=95:self.set_index(0)
        self._update_interval(); self.timer.start()

    def pause(self)->None:self.timer.stop()

    def reset(self)->None:self.pause(); self.set_index(0)

    def step_forward(self)->None:
        if self.result is None:return
        if self.current_index>=95:self.pause(); return
        self.set_index(self.current_index+1)

    def set_index(self,index:int)->None:
        if self.result is None:return
        self.current_index=max(0,min(95,int(index))); self.slider.blockSignals(True); self.slider.setValue(self.current_index); self.slider.blockSignals(False)
        row=self.result.frame.iloc[self.current_index]; f=self.result.frame; self.chart.set_index(self.current_index)
        end=int(row.horizon_end_index) if "horizon_end_index" in f else min(95,self.current_index+15); time=str(row.time); self.time_label.setText(f"{time} · 第 {self.current_index+1}/96 时段")
        self.cards["mode"].setText(f"控制模式\n{row.control_mode}"); self.cards["status"].setText(f"电网状态\n{row.grid_status}"); self.cards["bias"].setText(f"EWMA 偏差\n{row.forecast_bias_kw:+.1f} kW"); self.cards["sigma"].setText(f"误差 σ\n{float(row.forecast_sigma_kw):.1f} kW" if "forecast_sigma_kw" in f else "误差 σ\n--"); self.cards["window"].setText(f"当前预测窗\n{time}–{f.iloc[end].time}"); self.cards["action"].setText(f"当前动作\n储能 {row.battery_kw:+.1f} kW · 主网 {row.grid_import_kw:.1f} kW")
        self.formula.setText(f"误差 error = {row.forecast_error_kw:+.1f} kW\nEWMA bias = 0.35 x error + 0.65 x old_bias = {row.forecast_bias_kw:+.1f} kW\n滚动预测窗：{time} 至 {f.iloc[end].time}") if "forecast_error_kw" in f else None
        indices=list(f.index[f.replan_flag.astype(bool)]); visible=[i for i in indices if i<=self.current_index][-8:]; self.table.setRowCount(len(visible))
        for r,idx in enumerate(visible):
            x=f.iloc[idx]; vals=(str(x.time),f"{x.forecast_error_kw:+.1f}",f"{x.forecast_bias_kw:+.1f}",f"{x.time}–{f.iloc[int(x.horizon_end_index)].time}",f"{x.grid_status} · {x.replan_reason}")
            for c,v in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(v))

    def close(self)->None:
        self.pause(); super().close()
