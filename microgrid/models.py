"""Domain models for the microgrid.

The course brief asks for every physical component to be represented as a
class.  These dataclasses are deliberately independent from the GUI so that
the scheduling algorithm can also be tested or reused from a console script.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


TIME_STEPS = 96
INTERVAL_HOURS = 0.25


@dataclass
class PhotovoltaicArray:
    name: str = "屋顶光伏阵列"
    capacity_kw: float = 120.0
    uncertainty_pct: float = 18.0


@dataclass
class BatteryStorage:
    name: str = "磷酸铁锂储能"
    capacity_kwh: float = 180.0
    max_charge_kw: float = 70.0
    max_discharge_kw: float = 70.0
    min_soc: float = 0.10
    max_soc: float = 0.90
    initial_soc: float = 0.55
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    cycle_cost_yuan_kwh: float = 0.035


@dataclass
class DieselGenerator:
    name: str = "备用柴油发电机"
    max_power_kw: float = 90.0
    fuel_cost_yuan_kwh: float = 1.05
    carbon_kg_kwh: float = 0.78


@dataclass
class MainGrid:
    name: str = "公共电网"
    import_limit_kw: float = 180.0
    export_limit_kw: float = 80.0
    sell_price_yuan_kwh: float = 0.32
    carbon_kg_kwh: float = 0.58


@dataclass
class ElectricalLoad:
    name: str = "园区综合负荷"
    scale: float = 1.0


@dataclass
class MicrogridConfig:
    pv: PhotovoltaicArray = field(default_factory=PhotovoltaicArray)
    battery: BatteryStorage = field(default_factory=BatteryStorage)
    diesel: DieselGenerator = field(default_factory=DieselGenerator)
    grid: MainGrid = field(default_factory=MainGrid)
    load: ElectricalLoad = field(default_factory=ElectricalLoad)
    reserve_soc_margin: float = 0.10

    def validate(self) -> None:
        positive = {
            "光伏容量": self.pv.capacity_kw,
            "储能容量": self.battery.capacity_kwh,
            "储能充电功率": self.battery.max_charge_kw,
            "储能放电功率": self.battery.max_discharge_kw,
            "柴油机容量": self.diesel.max_power_kw,
            "主网购电上限": self.grid.import_limit_kw,
            "负荷倍率": self.load.scale,
        }
        bad = [name for name, value in positive.items() if value <= 0]
        if bad:
            raise ValueError(f"参数必须大于零：{', '.join(bad)}")
        b = self.battery
        if not 0 <= b.min_soc < b.initial_soc < b.max_soc <= 1:
            raise ValueError("储能 SOC 必须满足 0 <= 最小值 < 初始值 < 最大值 <= 1")
        if not 0 < b.charge_efficiency <= 1 or not 0 < b.discharge_efficiency <= 1:
            raise ValueError("充放电效率必须在 (0, 1] 范围内")
        if not 0 <= self.reserve_soc_margin < b.max_soc - b.min_soc:
            raise ValueError("备用 SOC 裕度超出可用范围")


@dataclass
class ScenarioData:
    time_labels: np.ndarray
    load_kw: np.ndarray
    pv_forecast_kw: np.ndarray
    pv_actual_kw: np.ndarray
    buy_price_yuan_kwh: np.ndarray
    source_name: str
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        arrays = {
            "时间": self.time_labels,
            "负荷": self.load_kw,
            "光伏预测": self.pv_forecast_kw,
            "光伏实测": self.pv_actual_kw,
            "购电价格": self.buy_price_yuan_kwh,
        }
        wrong = [name for name, values in arrays.items() if len(values) != TIME_STEPS]
        if wrong:
            raise ValueError(f"以下数据列必须包含 {TIME_STEPS} 个 15 分钟点：{', '.join(wrong)}")
        for name, values in arrays.items():
            if name == "时间":
                continue
            numeric = np.asarray(values, dtype=float)
            if not np.isfinite(numeric).all():
                raise ValueError(f"{name}包含空值或非数字")
            if (numeric < 0).any():
                raise ValueError(f"{name}不能包含负数")


def default_config() -> MicrogridConfig:
    """Return a fresh configuration object with demonstrable defaults."""

    return MicrogridConfig()
