"""Parameter editing and model explanation dialogs."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..models import MicrogridConfig


def _number(minimum: float, maximum: float, value: float, suffix: str, decimals: int = 1) -> QDoubleSpinBox:
    editor = QDoubleSpinBox()
    editor.setRange(minimum, maximum)
    editor.setDecimals(decimals)
    editor.setSingleStep(1.0 if decimals else 1)
    editor.setValue(value)
    editor.setSuffix(suffix)
    return editor


class ComponentDialog(QDialog):
    """Edit physical component properties in one consistent dialog."""

    def __init__(self, config: MicrogridConfig, component: str, parent=None) -> None:
        super().__init__(parent)
        self._original = config
        self.config = deepcopy(config)
        self.component = component
        titles = {
            "pv": "光伏阵列参数",
            "battery": "储能系统参数",
            "diesel": "柴油发电机参数",
            "grid": "公共电网参数",
            "load": "园区负荷参数",
        }
        self.setWindowTitle(titles[component])
        self.setModal(True)
        self.setMinimumWidth(410)
        layout = QVBoxLayout(self)
        intro = QLabel("修改后点击“应用”。调度结果将自动重新计算。")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(11)
        self.editors: dict[str, QDoubleSpinBox] = {}
        self._build_form(form)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("应用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add(self, form: QFormLayout, key: str, label: str, widget: QDoubleSpinBox) -> None:
        self.editors[key] = widget
        form.addRow(label, widget)

    def _build_form(self, form: QFormLayout) -> None:
        c = self.config
        if self.component == "pv":
            self._add(form, "capacity_kw", "装机容量", _number(10, 1000, c.pv.capacity_kw, " kW"))
            self._add(form, "uncertainty_pct", "预测不确定度", _number(0, 60, c.pv.uncertainty_pct, " %"))
        elif self.component == "battery":
            self._add(form, "capacity_kwh", "额定容量", _number(10, 2000, c.battery.capacity_kwh, " kWh"))
            self._add(form, "max_charge_kw", "最大充电功率", _number(1, 500, c.battery.max_charge_kw, " kW"))
            self._add(form, "max_discharge_kw", "最大放电功率", _number(1, 500, c.battery.max_discharge_kw, " kW"))
            self._add(form, "initial_soc", "初始 SOC", _number(11, 89, c.battery.initial_soc * 100, " %"))
            self._add(form, "min_soc", "最小 SOC", _number(0, 80, c.battery.min_soc * 100, " %"))
            self._add(form, "max_soc", "最大 SOC", _number(20, 100, c.battery.max_soc * 100, " %"))
        elif self.component == "diesel":
            self._add(form, "max_power_kw", "最大功率", _number(1, 1000, c.diesel.max_power_kw, " kW"))
            self._add(form, "fuel_cost_yuan_kwh", "发电成本", _number(0.1, 5.0, c.diesel.fuel_cost_yuan_kwh, " 元/kWh", 2))
        elif self.component == "grid":
            self._add(form, "import_limit_kw", "购电功率上限", _number(1, 2000, c.grid.import_limit_kw, " kW"))
            self._add(form, "export_limit_kw", "上网功率上限", _number(0, 1000, c.grid.export_limit_kw, " kW"))
            self._add(form, "sell_price_yuan_kwh", "上网电价", _number(0, 2.0, c.grid.sell_price_yuan_kwh, " 元/kWh", 2))
        else:
            self._add(form, "scale", "负荷倍率", _number(0.2, 3.0, c.load.scale, " 倍", 2))

    def _accept(self) -> None:
        target = getattr(self.config, self.component)
        for key, editor in self.editors.items():
            value = editor.value()
            if key.endswith("soc"):
                value /= 100.0
            setattr(target, key, value)
        try:
            self.config.validate()
        except ValueError as exc:
            self.editors[next(iter(self.editors))].setFocus()
            self.setWindowTitle(f"参数有误 - {exc}")
            return
        self.accept()


class AboutModelDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("模型与策略说明")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._text_page(self._algorithm_text()), "调度算法")
        tabs.addTab(self._text_page(self._uncertainty_text()), "光伏不确定性")
        tabs.addTab(self._text_page(self._experiment_text()), "实验与项目")
        tabs.addTab(self._text_page(self._sign_text()), "符号约定")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _text_page(html: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser)
        return page

    @staticmethod
    def _algorithm_text() -> str:
        return """
        <h2>96 时段确定性调度</h2>
        <p>每 15 分钟为一个时段，以储能能量为状态量，枚举满足充放电功率和 SOC
        约束的状态转移，通过动态规划求全天运行费用最低的路径。</p>
        <p><b>目标：</b>最小化购电费用 + 柴油发电费用 + 储能循环成本 - 上网收益。</p>
        <p><b>约束：</b>逐时功率平衡、SOC 上下限、充放电功率、主网交换功率、柴油机功率，
        并要求日末 SOC 回到日初水平，保证不同策略可公平比较。</p>
        <p>当分时购电价高于柴油发电边际成本时，柴油机优先；否则主网购电优先。</p>
        """

    @staticmethod
    def _uncertainty_text() -> str:
        return """
        <h2>光伏不确定性策略</h2>
        <p>根据光伏预测值和组件不确定度构造正态近似置信区间。风险感知策略使用置信
        下界 P<sub>lower</sub> 做日前计划，并提高最低可用 SOC，预留调节能力。</p>
        <p>实时运行中，每 15 分钟比较实际光伏与计划光伏。光伏短缺时储能优先增加放电，
        光伏超发时优先充电；达到功率或 SOC 边界后，再由柴油机和主网完成平衡。</p>
        <p>置信度越高，下界越保守，抗预测偏差能力通常越强，但日前计划成本可能上升。</p>
        """

    @staticmethod
    def _sign_text() -> str:
        return """
        <h2>图表与数据符号</h2>
        <ul>
          <li>储能功率为正：放电；为负：充电。</li>
          <li>主网净功率为正：购电；为负：向主网上网。</li>
          <li>实测光伏仅用于模拟实时误差；日前优化不会提前使用实测值。</li>
          <li>功率单位为 kW，15 分钟能量 = 功率 x 0.25 h。</li>
        </ul>
        """

    @staticmethod
    def _experiment_text() -> str:
        return """
        <h2>随机实验与容量分析</h2>
        <p>Monte Carlo 分析先固定确定性和风险感知两套日前计划，再让两套计划在完全相同的
        相关光伏误差场景下执行。结果给出均值、P5、P50、P95 和超限概率。</p>
        <p>容量敏感性分析会在给定范围内生成等距储能或光伏容量点，每个点重新优化，比较运行
        成本、主网购电、碳排放、光伏消纳率和弃光。</p>
        <h2>项目与报告</h2>
        <p><code>.dong</code> 项目文件保存组件参数、96 点场景、策略和置信度，不保存计算缓存；
        打开后会重新计算。运行报告包包含 Markdown、CSV、JSON 和 PNG 图表。</p>
        """
