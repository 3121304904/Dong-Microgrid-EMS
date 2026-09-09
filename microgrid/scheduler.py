"""Day-ahead optimization and real-time uncertainty compensation.

The day-ahead problem is solved with dynamic programming.  Stored energy is
the state, and every feasible charge/discharge transition is evaluated over
96 intervals.  This keeps the implementation transparent for a course
defence while still producing a genuine minimum-cost schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from .models import INTERVAL_HOURS, TIME_STEPS, MicrogridConfig, ScenarioData


@dataclass
class ForecastEnvelope:
    lower_kw: np.ndarray
    median_kw: np.ndarray
    upper_kw: np.ndarray
    confidence_pct: float


@dataclass
class DispatchResult:
    strategy_key: str
    strategy_name: str
    frame: pd.DataFrame
    metrics: dict[str, float]
    cost_breakdown: dict[str, float]
    confidence_pct: float


@dataclass
class DispatchPlan:
    """Reusable day-ahead plan that can be executed against many PV outcomes."""

    strategy_key: str
    strategy_name: str
    confidence_pct: float
    envelope: ForecastEnvelope
    pv_for_plan_kw: np.ndarray
    schedule: dict[str, np.ndarray | float]
    risk_aware: bool


@dataclass(frozen=True)
class RollingPredictiveSettings:
    """Settings for the explainable hourly rolling re-dispatch controller."""

    horizon_steps: int = 16
    replan_interval_steps: int = 4
    ewma_alpha: float = 0.35
    forecast_decay_per_hour: float = 0.82


def build_forecast_envelope(
    data: ScenarioData,
    config: MicrogridConfig,
    confidence_pct: float,
) -> ForecastEnvelope:
    confidence = float(np.clip(confidence_pct, 50.0, 99.0))
    z_value = NormalDist().inv_cdf(0.5 + confidence / 200.0)
    daylight = data.pv_forecast_kw > 1e-6
    sigma = np.zeros(TIME_STEPS)
    relative = config.pv.uncertainty_pct / 100.0
    sigma[daylight] = (
        relative * data.pv_forecast_kw[daylight]
        + 0.018 * config.pv.capacity_kw
    )
    lower = np.clip(data.pv_forecast_kw - z_value * sigma, 0.0, config.pv.capacity_kw)
    upper = np.clip(data.pv_forecast_kw + z_value * sigma, 0.0, config.pv.capacity_kw)
    return ForecastEnvelope(lower, data.pv_forecast_kw.copy(), upper, confidence)


def _supply_cost(
    residual_kw: float,
    price: float,
    config: MicrogridConfig,
) -> tuple[float, float, float, float, float, float]:
    """Return diesel, import, export, curtailed, unserved and interval cost."""

    diesel = grid_import = grid_export = curtailment = unserved = 0.0
    dt = INTERVAL_HOURS
    if residual_kw >= 0:
        remaining = residual_kw
        if price <= config.diesel.fuel_cost_yuan_kwh:
            grid_import = min(remaining, config.grid.import_limit_kw)
            remaining -= grid_import
            diesel = min(remaining, config.diesel.max_power_kw)
        else:
            diesel = min(remaining, config.diesel.max_power_kw)
            remaining -= diesel
            grid_import = min(remaining, config.grid.import_limit_kw)
        remaining -= grid_import if price > config.diesel.fuel_cost_yuan_kwh else diesel
        unserved = max(0.0, remaining)
    else:
        surplus = -residual_kw
        grid_export = min(surplus, config.grid.export_limit_kw)
        curtailment = max(0.0, surplus - grid_export)

    cost = dt * (
        diesel * config.diesel.fuel_cost_yuan_kwh
        + grid_import * price
        - grid_export * config.grid.sell_price_yuan_kwh
        + unserved * 20.0
        + curtailment * 0.01
    )
    return diesel, grid_import, grid_export, curtailment, unserved, cost


def _dispatch_for_transition(
    load_kw: float,
    pv_kw: float,
    price: float,
    battery_power_kw: float,
    config: MicrogridConfig,
) -> tuple[float, float, float, float, float, float]:
    residual = load_kw - pv_kw - battery_power_kw
    diesel, imported, exported, curtailed, unserved, cost = _supply_cost(
        residual, price, config
    )
    cost += (
        abs(battery_power_kw)
        * INTERVAL_HOURS
        * config.battery.cycle_cost_yuan_kwh
    )
    return diesel, imported, exported, curtailed, unserved, cost


def _optimize_day_ahead(
    data: ScenarioData,
    config: MicrogridConfig,
    pv_for_plan_kw: np.ndarray,
    reserve_margin: float,
) -> dict[str, np.ndarray | float]:
    """Find a least-cost battery path and corresponding source dispatch."""

    b = config.battery
    physical_min = b.capacity_kwh * b.min_soc
    schedule_min = b.capacity_kwh * min(b.max_soc, b.min_soc + reserve_margin)
    initial_energy = b.capacity_kwh * b.initial_soc
    schedule_min = min(schedule_min, initial_energy)
    max_energy = b.capacity_kwh * b.max_soc

    # Include the initial state exactly so the terminal SOC equality is exact.
    levels = np.unique(
        np.append(np.linspace(schedule_min, max_energy, 81), initial_energy)
    )
    states = len(levels)
    start_index = int(np.argmin(np.abs(levels - initial_energy)))
    infinity = float("inf")
    dp = np.full(states, infinity)
    dp[start_index] = 0.0
    predecessor = np.full((TIME_STEPS, states), -1, dtype=int)

    for t in range(TIME_STEPS):
        next_dp = np.full(states, infinity)
        for current in np.flatnonzero(np.isfinite(dp)):
            current_energy = levels[current]
            energy_delta = levels - current_energy
            charge_power = np.maximum(energy_delta, 0.0) / (
                b.charge_efficiency * INTERVAL_HOURS
            )
            discharge_power = np.maximum(-energy_delta, 0.0) * (
                b.discharge_efficiency / INTERVAL_HOURS
            )
            feasible = (charge_power <= b.max_charge_kw + 1e-9) & (
                discharge_power <= b.max_discharge_kw + 1e-9
            )
            for nxt in np.flatnonzero(feasible):
                battery_power = discharge_power[nxt] - charge_power[nxt]
                *_, step_cost = _dispatch_for_transition(
                    data.load_kw[t],
                    pv_for_plan_kw[t],
                    data.buy_price_yuan_kwh[t],
                    battery_power,
                    config,
                )
                candidate = dp[current] + step_cost
                if candidate < next_dp[nxt]:
                    next_dp[nxt] = candidate
                    predecessor[t, nxt] = current
        dp = next_dp

    terminal = start_index
    if not np.isfinite(dp[terminal]):
        terminal = int(np.nanargmin(dp + 3.0 * np.abs(levels - initial_energy)))

    state_path = np.empty(TIME_STEPS + 1, dtype=int)
    state_path[-1] = terminal
    for t in range(TIME_STEPS - 1, -1, -1):
        state_path[t] = predecessor[t, state_path[t + 1]]
        if state_path[t] < 0:
            raise RuntimeError("动态规划回溯失败，请检查储能参数")

    energy = levels[state_path]
    delta = np.diff(energy)
    battery_power = np.where(
        delta >= 0,
        -delta / (b.charge_efficiency * INTERVAL_HOURS),
        -delta * b.discharge_efficiency / INTERVAL_HOURS,
    )
    diesel = np.zeros(TIME_STEPS)
    imported = np.zeros(TIME_STEPS)
    exported = np.zeros(TIME_STEPS)
    curtailed = np.zeros(TIME_STEPS)
    unserved = np.zeros(TIME_STEPS)
    for t in range(TIME_STEPS):
        values = _dispatch_for_transition(
            data.load_kw[t],
            pv_for_plan_kw[t],
            data.buy_price_yuan_kwh[t],
            battery_power[t],
            config,
        )
        diesel[t], imported[t], exported[t], curtailed[t], unserved[t], _ = values

    return {
        "battery_kw": battery_power,
        "diesel_kw": diesel,
        "grid_import_kw": imported,
        "grid_export_kw": exported,
        "curtailment_kw": curtailed,
        "unserved_kw": unserved,
        "soc_pct": 100.0 * energy[1:] / b.capacity_kwh,
        "optimized_cost": float(dp[terminal]),
        "physical_min_kwh": physical_min,
    }


def _execute_in_real_time(
    data: ScenarioData,
    config: MicrogridConfig,
    plan: dict[str, np.ndarray | float],
    pv_for_plan_kw: np.ndarray,
    risk_aware: bool,
) -> dict[str, np.ndarray]:
    """Balance actual PV errors and enforce physical constraints each interval."""

    b = config.battery
    dt = INTERVAL_HOURS
    min_energy = b.capacity_kwh * b.min_soc
    max_energy = b.capacity_kwh * b.max_soc
    energy = b.capacity_kwh * b.initial_soc

    output = {
        name: np.zeros(TIME_STEPS)
        for name in (
            "battery_kw",
            "diesel_kw",
            "grid_import_kw",
            "grid_export_kw",
            "curtailment_kw",
            "unserved_kw",
            "soc_pct",
        )
    }

    for t in range(TIME_STEPS):
        target_energy_next = (
            float(plan["soc_pct"][t]) / 100.0 * b.capacity_kwh
        )
        energy_to_target = target_energy_next - energy
        if energy_to_target >= 0:
            trajectory_power = -energy_to_target / (
                b.charge_efficiency * dt
            )
        else:
            trajectory_power = -energy_to_target * b.discharge_efficiency / dt
        forecast_error = pv_for_plan_kw[t] - data.pv_actual_kw[t]
        # Fade the uncertainty correction near day-end so the storage returns
        # to the optimized terminal state instead of carrying forecast-error
        # energy into the next operating day.
        terminal_weight = min(1.0, max(0.0, (TIME_STEPS - 1 - t) / 8.0))
        correction_gain = 0.90 * terminal_weight if risk_aware else 0.0
        requested_battery = trajectory_power + correction_gain * forecast_error

        max_discharge_by_soc = max(0.0, (energy - min_energy) * b.discharge_efficiency / dt)
        max_charge_by_soc = max(0.0, (max_energy - energy) / (b.charge_efficiency * dt))
        battery_power = float(
            np.clip(
                requested_battery,
                -min(b.max_charge_kw, max_charge_by_soc),
                min(b.max_discharge_kw, max_discharge_by_soc),
            )
        )
        if battery_power >= 0:
            energy -= battery_power * dt / b.discharge_efficiency
        else:
            energy += -battery_power * dt * b.charge_efficiency
        energy = float(np.clip(energy, min_energy, max_energy))

        diesel = float(plan["diesel_kw"][t])
        residual = data.load_kw[t] - data.pv_actual_kw[t] - battery_power - diesel

        # A risk-aware controller can call unused diesel headroom during an
        # expensive-price shortfall.  The main grid remains the slack source.
        if (
            risk_aware
            and residual > 0
            and data.buy_price_yuan_kwh[t] > config.diesel.fuel_cost_yuan_kwh
        ):
            extra = min(residual, config.diesel.max_power_kw - diesel)
            diesel += extra
            residual -= extra
        elif residual < 0 and diesel > 0:
            reduction = min(diesel, -residual)
            diesel -= reduction
            residual += reduction

        imported = exported = curtailed = unserved = 0.0
        if residual >= 0:
            imported = min(residual, config.grid.import_limit_kw)
            remaining = residual - imported
            if remaining > 0 and diesel < config.diesel.max_power_kw:
                extra = min(remaining, config.diesel.max_power_kw - diesel)
                diesel += extra
                remaining -= extra
            unserved = max(0.0, remaining)
        else:
            exported = min(-residual, config.grid.export_limit_kw)
            curtailed = max(0.0, -residual - exported)

        output["battery_kw"][t] = battery_power
        output["diesel_kw"][t] = diesel
        output["grid_import_kw"][t] = imported
        output["grid_export_kw"][t] = exported
        output["curtailment_kw"][t] = curtailed
        output["unserved_kw"][t] = unserved
        output["soc_pct"][t] = 100.0 * energy / b.capacity_kwh

    return output


def _optimize_horizon(
    data: ScenarioData,
    config: MicrogridConfig,
    pv_for_plan_kw: np.ndarray,
    start_index: int,
    start_energy: float,
    terminal_energy: float | None = None,
) -> dict[str, np.ndarray | float]:
    """Optimise a finite rolling window with the same transparent DP model."""

    b = config.battery
    horizon = len(pv_for_plan_kw)
    if horizon <= 0:
        return {"battery_kw": np.zeros(0), "diesel_kw": np.zeros(0), "grid_import_kw": np.zeros(0), "grid_export_kw": np.zeros(0), "curtailment_kw": np.zeros(0), "unserved_kw": np.zeros(0), "soc_pct": np.zeros(0), "final_energy_kwh": float(start_energy), "optimized_cost": 0.0}
    min_energy = b.capacity_kwh * b.min_soc
    max_energy = b.capacity_kwh * b.max_soc
    start_energy = float(np.clip(start_energy, min_energy, max_energy))
    levels = np.unique(np.append(np.linspace(min_energy, max_energy, 81), start_energy))
    if terminal_energy is not None:
        levels = np.unique(np.append(levels, np.clip(terminal_energy, min_energy, max_energy)))
    start_state = int(np.argmin(np.abs(levels - start_energy)))
    states = len(levels)
    dp = np.full(states, np.inf)
    dp[start_state] = 0.0
    predecessor = np.full((horizon, states), -1, dtype=int)
    for tau in range(horizon):
        next_dp = np.full(states, np.inf)
        current_indices = np.flatnonzero(np.isfinite(dp))
        for current in current_indices:
            current_energy = levels[current]
            delta = levels - current_energy
            charge_power = np.maximum(delta, 0.0) / (b.charge_efficiency * INTERVAL_HOURS)
            discharge_power = np.maximum(-delta, 0.0) * b.discharge_efficiency / INTERVAL_HOURS
            feasible = (charge_power <= b.max_charge_kw + 1e-9) & (discharge_power <= b.max_discharge_kw + 1e-9)
            for nxt in np.flatnonzero(feasible):
                battery_power = discharge_power[nxt] - charge_power[nxt]
                *_, step_cost = _dispatch_for_transition(
                    float(data.load_kw[start_index + tau]),
                    float(pv_for_plan_kw[tau]),
                    float(data.buy_price_yuan_kwh[start_index + tau]),
                    float(battery_power),
                    config,
                )
                candidate = dp[current] + step_cost
                if candidate < next_dp[nxt]:
                    next_dp[nxt] = candidate
                    predecessor[tau, nxt] = current
        dp = next_dp
    if terminal_energy is None:
        terminal = int(np.nanargmin(dp))
    else:
        target = int(np.argmin(np.abs(levels - terminal_energy)))
        terminal = target if np.isfinite(dp[target]) else int(np.nanargmin(dp + 2.0 * np.abs(levels - terminal_energy)))
    path = np.empty(horizon + 1, dtype=int)
    path[-1] = terminal
    for tau in range(horizon - 1, -1, -1):
        path[tau] = predecessor[tau, path[tau + 1]]
        if path[tau] < 0:
            raise RuntimeError("滚动动态规划回溯失败，请检查储能参数")
    energy = levels[path]
    delta = np.diff(energy)
    battery_power = np.where(delta >= 0, -delta / (b.charge_efficiency * INTERVAL_HOURS), -delta * b.discharge_efficiency / INTERVAL_HOURS)
    arrays = {name: np.zeros(horizon) for name in ("diesel_kw", "grid_import_kw", "grid_export_kw", "curtailment_kw", "unserved_kw")}
    for tau in range(horizon):
        values = _dispatch_for_transition(
            float(data.load_kw[start_index + tau]),
            float(pv_for_plan_kw[tau]),
            float(data.buy_price_yuan_kwh[start_index + tau]),
            float(battery_power[tau]),
            config,
        )
        arrays["diesel_kw"][tau], arrays["grid_import_kw"][tau], arrays["grid_export_kw"][tau], arrays["curtailment_kw"][tau], arrays["unserved_kw"][tau], _ = values
    arrays["battery_kw"] = battery_power
    arrays["soc_pct"] = 100.0 * energy[1:] / b.capacity_kwh
    arrays["final_energy_kwh"] = float(energy[-1])
    arrays["optimized_cost"] = float(dp[terminal])
    return arrays


def _calculate_metrics(
    frame: pd.DataFrame,
    config: MicrogridConfig,
) -> tuple[dict[str, float], dict[str, float]]:
    dt = INTERVAL_HOURS
    grid_purchase = float((frame.grid_import_kw * frame.price_yuan_kwh).sum() * dt)
    export_revenue = float(
        frame.grid_export_kw.sum() * dt * config.grid.sell_price_yuan_kwh
    )
    diesel_cost = float(
        frame.diesel_kw.sum() * dt * config.diesel.fuel_cost_yuan_kwh
    )
    battery_cost = float(
        frame.battery_kw.abs().sum() * dt * config.battery.cycle_cost_yuan_kwh
    )
    shortage_penalty = float(frame.unserved_kw.sum() * dt * 20.0)
    curtail_penalty = float(frame.curtailment_kw.sum() * dt * 0.01)
    total_cost = (
        grid_purchase
        + diesel_cost
        + battery_cost
        + shortage_penalty
        + curtail_penalty
        - export_revenue
    )
    pv_energy = float(frame.pv_actual_kw.sum() * dt)
    curtailed_energy = float(frame.curtailment_kw.sum() * dt)
    renewable_utilization = 100.0 if pv_energy <= 1e-9 else 100.0 * (pv_energy - curtailed_energy) / pv_energy
    carbon = float(
        frame.grid_import_kw.sum() * dt * config.grid.carbon_kg_kwh
        + frame.diesel_kw.sum() * dt * config.diesel.carbon_kg_kwh
    )
    metrics = {
        "total_cost_yuan": total_cost,
        "planned_cost_yuan": float(frame.planned_interval_cost_yuan.sum()),
        "grid_import_kwh": float(frame.grid_import_kw.sum() * dt),
        "grid_export_kwh": float(frame.grid_export_kw.sum() * dt),
        "diesel_energy_kwh": float(frame.diesel_kw.sum() * dt),
        "battery_throughput_kwh": float(frame.battery_kw.abs().sum() * dt),
        "pv_energy_kwh": pv_energy,
        "curtailment_kwh": curtailed_energy,
        "unserved_kwh": float(frame.unserved_kw.sum() * dt),
        "renewable_utilization_pct": renewable_utilization,
        "peak_grid_import_kw": float(frame.grid_import_kw.max()),
        "carbon_kg": carbon,
        "final_soc_pct": float(frame.soc_pct.iloc[-1]),
        "min_soc_pct": float(frame.soc_pct.min()),
    }
    breakdown = {
        "电网购电": grid_purchase,
        "柴油发电": diesel_cost,
        "储能损耗": battery_cost,
        "失负荷惩罚": shortage_penalty,
        "弃光惩罚": curtail_penalty,
        "上网收益": -export_revenue,
    }
    return metrics, breakdown


def _rolling_strategy_frame(
    data: ScenarioData,
    config: MicrogridConfig,
    confidence_pct: float,
    settings: RollingPredictiveSettings,
) -> pd.DataFrame:
    """Run an hourly rolling forecast and re-dispatch loop on offline data."""

    envelope = build_forecast_envelope(data, config, confidence_pct)
    b = config.battery
    dt = INTERVAL_HOURS
    min_energy = b.capacity_kwh * b.min_soc
    max_energy = b.capacity_kwh * b.max_soc
    energy = b.capacity_kwh * b.initial_soc
    bias = 0.0
    planned_battery = np.zeros(TIME_STEPS)
    planned_diesel = np.zeros(TIME_STEPS)
    rolling_forecast = np.zeros(TIME_STEPS)
    rolling_lower = np.zeros(TIME_STEPS)
    bias_series = np.zeros(TIME_STEPS)
    replan_flag = np.zeros(TIME_STEPS, dtype=int)
    replan_reason = np.full(TIME_STEPS, "执行已发布计划", dtype=object)
    control_mode = np.full(TIME_STEPS, "执行已发布计划", dtype=object)

    battery = np.zeros(TIME_STEPS)
    diesel = np.zeros(TIME_STEPS)
    imported = np.zeros(TIME_STEPS)
    exported = np.zeros(TIME_STEPS)
    curtailed = np.zeros(TIME_STEPS)
    unserved = np.zeros(TIME_STEPS)
    soc = np.zeros(TIME_STEPS)

    current_plan: dict[str, np.ndarray | float] | None = None
    for t in range(TIME_STEPS):
        # Update the error estimate only with observations that have already
        # happened.  The first point has no past error and keeps bias at 0.
        if t > 0:
            error = float(data.pv_actual_kw[t - 1] - data.pv_forecast_kw[t - 1])
            bias = settings.ewma_alpha * error + (1.0 - settings.ewma_alpha) * bias
        bias_series[t] = bias
        must_replan = current_plan is None or t % settings.replan_interval_steps == 0
        if must_replan:
            horizon = min(settings.horizon_steps, TIME_STEPS - t)
            offsets = np.arange(horizon, dtype=float) / 4.0
            corrected = data.pv_forecast_kw[t : t + horizon] + bias * np.power(
                settings.forecast_decay_per_hour, offsets
            )
            corrected = np.clip(corrected, 0.0, config.pv.capacity_kw)
            current_plan = _optimize_horizon(
                data,
                config,
                corrected,
                t,
                energy,
                b.capacity_kwh * b.initial_soc if t + horizon >= TIME_STEPS else None,
            )
            replan_flag[t] = 1
            replan_reason[t] = "滚动重优化：更新未来 4 小时预测"
            control_mode[t] = "滚动重优化"
            rolling_forecast[t : t + horizon] = corrected
            lower = np.clip(corrected - 0.5 * np.abs(bias), 0.0, config.pv.capacity_kw)
            rolling_lower[t : t + horizon] = lower
        if current_plan is None:
            raise RuntimeError("滚动策略未生成有效计划")
        local_index = min(t % settings.replan_interval_steps, len(current_plan["battery_kw"]) - 1)
        planned_battery[t] = float(current_plan["battery_kw"][local_index])
        planned_diesel[t] = float(current_plan["diesel_kw"][local_index])
        if rolling_forecast[t] <= 0.0:
            remaining = min(settings.horizon_steps, TIME_STEPS - t)
            offsets = np.arange(remaining, dtype=float) / 4.0
            corrected = data.pv_forecast_kw[t : t + remaining] + bias * np.power(
                settings.forecast_decay_per_hour, offsets
            )
            rolling_forecast[t : t + remaining] = np.clip(corrected, 0.0, config.pv.capacity_kw)
            rolling_lower[t : t + remaining] = np.clip(
                corrected - 0.5 * np.abs(bias), 0.0, config.pv.capacity_kw
            )

        max_discharge_by_soc = max(0.0, (energy - min_energy) * b.discharge_efficiency / dt)
        max_charge_by_soc = max(0.0, (max_energy - energy) / (b.charge_efficiency * dt))
        battery_power = float(
            np.clip(
                planned_battery[t],
                -min(b.max_charge_kw, max_charge_by_soc),
                min(b.max_discharge_kw, max_discharge_by_soc),
            )
        )
        if battery_power >= 0:
            energy -= battery_power * dt / b.discharge_efficiency
        else:
            energy += -battery_power * dt * b.charge_efficiency
        energy = float(np.clip(energy, min_energy, max_energy))

        diesel_power = float(np.clip(planned_diesel[t], 0.0, config.diesel.max_power_kw))
        residual = float(data.load_kw[t] - data.pv_actual_kw[t] - battery_power - diesel_power)
        # Use the main grid as the first real-time slack source, then use any
        # remaining diesel headroom before declaring unserved load.
        if residual >= 0:
            imported_power = min(residual, config.grid.import_limit_kw)
            remaining = residual - imported_power
            if remaining > 0:
                extra = min(remaining, config.diesel.max_power_kw - diesel_power)
                diesel_power += extra
                remaining -= extra
            unserved_power = max(0.0, remaining)
            exported_power = curtailed_power = 0.0
        else:
            imported_power = unserved_power = 0.0
            exported_power = min(-residual, config.grid.export_limit_kw)
            curtailed_power = max(0.0, -residual - exported_power)

        battery[t] = battery_power
        diesel[t] = diesel_power
        imported[t] = imported_power
        exported[t] = exported_power
        curtailed[t] = curtailed_power
        unserved[t] = unserved_power
        soc[t] = 100.0 * energy / b.capacity_kwh
        if imported_power >= 0.82 * config.grid.import_limit_kw:
            control_mode[t] = "高价削峰执行" if data.buy_price_yuan_kwh[t] >= 0.90 else control_mode[t]
            if control_mode[t] == "执行已发布计划":
                control_mode[t] = "保供模式" if unserved_power > 0 else "滚动重优化"
        if unserved_power > 1e-9:
            replan_reason[t] = "保供告警：主网与柴油机均接近上限"
            control_mode[t] = "保供模式"
        elif imported_power >= 0.82 * config.grid.import_limit_kw:
            replan_reason[t] = "主网负载率超过 82%"

    frame = pd.DataFrame(
        {
            "time": data.time_labels,
            "load_kw": data.load_kw,
            "pv_forecast_kw": envelope.median_kw,
            "pv_lower_kw": envelope.lower_kw,
            "pv_upper_kw": envelope.upper_kw,
            "pv_actual_kw": data.pv_actual_kw,
            "pv_plan_kw": rolling_forecast,
            "rolling_forecast_kw": rolling_forecast,
            "rolling_lower_kw": rolling_lower,
            "forecast_bias_kw": bias_series,
            "price_yuan_kwh": data.buy_price_yuan_kwh,
            "battery_plan_kw": planned_battery,
            "diesel_plan_kw": planned_diesel,
            "grid_import_plan_kw": np.zeros(TIME_STEPS),
            "grid_export_plan_kw": np.zeros(TIME_STEPS),
            "battery_kw": battery,
            "diesel_kw": diesel,
            "grid_import_kw": imported,
            "grid_export_kw": exported,
            "curtailment_kw": curtailed,
            "unserved_kw": unserved,
            "soc_pct": soc,
            "replan_flag": replan_flag,
            "replan_reason": replan_reason,
            "control_mode": control_mode,
        }
    )
    frame["net_grid_kw"] = frame.grid_import_kw - frame.grid_export_kw
    frame["grid_loading_pct"] = 100.0 * frame.grid_import_kw / config.grid.import_limit_kw
    frame["grid_status"] = np.where(
        frame.unserved_kw > 1e-9,
        "保供告警",
        np.where(
            (frame.grid_import_kw >= 0.82 * config.grid.import_limit_kw)
            & (frame.price_yuan_kwh >= 0.90),
            "高价削峰",
            np.where(frame.grid_import_kw >= 0.82 * config.grid.import_limit_kw, "电网紧张", "正常"),
        ),
    )
    frame["power_balance_error_kw"] = (
        frame.pv_actual_kw
        - frame.curtailment_kw
        + frame.battery_kw
        + frame.diesel_kw
        + frame.grid_import_kw
        - frame.grid_export_kw
        + frame.unserved_kw
        - frame.load_kw
    )
    frame["planned_interval_cost_yuan"] = dt * (
        frame.grid_import_kw * frame.price_yuan_kwh
        + frame.diesel_kw * config.diesel.fuel_cost_yuan_kwh
        - frame.grid_export_kw * config.grid.sell_price_yuan_kwh
        + frame.battery_kw.abs() * config.battery.cycle_cost_yuan_kwh
    )
    return frame


def run_rolling_predictive(
    data: ScenarioData,
    config: MicrogridConfig,
    confidence_pct: float = 90.0,
    settings: RollingPredictiveSettings | None = None,
) -> DispatchResult:
    """Run the explainable 4-hour rolling forecast and re-dispatch strategy."""

    settings = settings or RollingPredictiveSettings()
    if settings.horizon_steps <= 0 or settings.replan_interval_steps <= 0:
        raise ValueError("滚动预测窗口和重规划间隔必须大于零")
    if settings.replan_interval_steps > settings.horizon_steps:
        raise ValueError("重规划间隔不能大于预测窗口")
    if not 0.0 < settings.ewma_alpha <= 1.0:
        raise ValueError("EWMA 修正系数必须在 (0, 1] 范围内")
    if not 0.0 < settings.forecast_decay_per_hour <= 1.0:
        raise ValueError("预测偏差衰减系数必须在 (0, 1] 范围内")
    data.validate()
    config.validate()
    frame = _rolling_strategy_frame(data, config, confidence_pct, settings)
    metrics, breakdown = _calculate_metrics(frame, config)
    return DispatchResult(
        strategy_key="rolling_predictive",
        strategy_name="滚动预测调度（4h MPC）",
        frame=frame,
        metrics=metrics,
        cost_breakdown=breakdown,
        confidence_pct=float(np.clip(confidence_pct, 50.0, 99.0)),
    )


def prepare_dispatch_plan(
    data: ScenarioData,
    config: MicrogridConfig,
    strategy_key: str,
    confidence_pct: float = 90.0,
) -> DispatchPlan:
    """Optimize one day-ahead plan without consuming actual PV observations."""

    data.validate()
    config.validate()
    if strategy_key not in {"deterministic", "risk_aware"}:
        raise ValueError("未知调度策略")

    envelope = build_forecast_envelope(data, config, confidence_pct)
    risk_aware = strategy_key == "risk_aware"
    pv_for_plan = envelope.lower_kw if risk_aware else envelope.median_kw
    reserve = config.reserve_soc_margin if risk_aware else 0.0
    schedule = _optimize_day_ahead(data, config, pv_for_plan, reserve)
    return DispatchPlan(
        strategy_key=strategy_key,
        strategy_name="风险感知 P下界" if risk_aware else "确定性 P50",
        confidence_pct=envelope.confidence_pct,
        envelope=envelope,
        pv_for_plan_kw=pv_for_plan.copy(),
        schedule=schedule,
        risk_aware=risk_aware,
    )


def execute_dispatch_plan(
    data: ScenarioData,
    config: MicrogridConfig,
    plan: DispatchPlan,
) -> DispatchResult:
    """Execute a fixed plan against the actual PV curve in ``data``."""

    data.validate()
    config.validate()
    actual = _execute_in_real_time(
        data,
        config,
        plan.schedule,
        plan.pv_for_plan_kw,
        plan.risk_aware,
    )

    frame = pd.DataFrame(
        {
            "time": data.time_labels,
            "load_kw": data.load_kw,
            "pv_forecast_kw": plan.envelope.median_kw,
            "pv_lower_kw": plan.envelope.lower_kw,
            "pv_upper_kw": plan.envelope.upper_kw,
            "pv_actual_kw": data.pv_actual_kw,
            "pv_plan_kw": plan.pv_for_plan_kw,
            "price_yuan_kwh": data.buy_price_yuan_kwh,
            "battery_plan_kw": plan.schedule["battery_kw"],
            "diesel_plan_kw": plan.schedule["diesel_kw"],
            "grid_import_plan_kw": plan.schedule["grid_import_kw"],
            "grid_export_plan_kw": plan.schedule["grid_export_kw"],
            "battery_kw": actual["battery_kw"],
            "diesel_kw": actual["diesel_kw"],
            "grid_import_kw": actual["grid_import_kw"],
            "grid_export_kw": actual["grid_export_kw"],
            "curtailment_kw": actual["curtailment_kw"],
            "unserved_kw": actual["unserved_kw"],
            "soc_pct": actual["soc_pct"],
        }
    )
    frame["net_grid_kw"] = frame.grid_import_kw - frame.grid_export_kw
    frame["rolling_forecast_kw"] = frame.pv_plan_kw
    frame["rolling_lower_kw"] = frame.pv_lower_kw
    frame["forecast_bias_kw"] = 0.0
    frame["grid_loading_pct"] = 100.0 * frame.grid_import_kw / config.grid.import_limit_kw
    frame["grid_status"] = np.where(
        frame.grid_import_kw >= 0.82 * config.grid.import_limit_kw,
        "电网紧张",
        "正常",
    )
    frame["replan_flag"] = 0
    frame["replan_reason"] = "执行已发布计划"
    frame["control_mode"] = "执行已发布计划"
    frame["power_balance_error_kw"] = (
        frame.pv_actual_kw
        - frame.curtailment_kw
        + frame.battery_kw
        + frame.diesel_kw
        + frame.grid_import_kw
        - frame.grid_export_kw
        + frame.unserved_kw
        - frame.load_kw
    )
    frame["planned_interval_cost_yuan"] = INTERVAL_HOURS * (
        frame.grid_import_plan_kw * frame.price_yuan_kwh
        + frame.diesel_plan_kw * config.diesel.fuel_cost_yuan_kwh
        - frame.grid_export_plan_kw * config.grid.sell_price_yuan_kwh
        + frame.battery_plan_kw.abs() * config.battery.cycle_cost_yuan_kwh
    )
    metrics, breakdown = _calculate_metrics(frame, config)
    return DispatchResult(
        strategy_key=plan.strategy_key,
        strategy_name=plan.strategy_name,
        frame=frame,
        metrics=metrics,
        cost_breakdown=breakdown,
        confidence_pct=plan.confidence_pct,
    )


def run_strategy(
    data: ScenarioData,
    config: MicrogridConfig,
    strategy_key: str,
    confidence_pct: float = 90.0,
) -> DispatchResult:
    """Compatibility wrapper: prepare and execute one strategy."""
    if strategy_key == "rolling_predictive":
        return run_rolling_predictive(data, config, confidence_pct)

    plan = prepare_dispatch_plan(data, config, strategy_key, confidence_pct)
    return execute_dispatch_plan(data, config, plan)


def run_baseline(data: ScenarioData, config: MicrogridConfig) -> DispatchResult:
    """Run a no-storage merit-order baseline for savings comparisons."""

    data.validate()
    config.validate()
    diesel = np.zeros(TIME_STEPS)
    imported = np.zeros(TIME_STEPS)
    exported = np.zeros(TIME_STEPS)
    curtailed = np.zeros(TIME_STEPS)
    unserved = np.zeros(TIME_STEPS)
    interval_cost = np.zeros(TIME_STEPS)
    for t in range(TIME_STEPS):
        values = _supply_cost(
            float(data.load_kw[t] - data.pv_actual_kw[t]),
            float(data.buy_price_yuan_kwh[t]),
            config,
        )
        (
            diesel[t],
            imported[t],
            exported[t],
            curtailed[t],
            unserved[t],
            interval_cost[t],
        ) = values

    zeros = np.zeros(TIME_STEPS)
    soc = np.full(TIME_STEPS, config.battery.initial_soc * 100.0)
    frame = pd.DataFrame(
        {
            "time": data.time_labels,
            "load_kw": data.load_kw,
            "pv_forecast_kw": data.pv_forecast_kw,
            "pv_lower_kw": data.pv_forecast_kw,
            "pv_upper_kw": data.pv_forecast_kw,
            "pv_actual_kw": data.pv_actual_kw,
            "pv_plan_kw": data.pv_forecast_kw,
            "price_yuan_kwh": data.buy_price_yuan_kwh,
            "battery_plan_kw": zeros,
            "diesel_plan_kw": diesel,
            "grid_import_plan_kw": imported,
            "grid_export_plan_kw": exported,
            "battery_kw": zeros,
            "diesel_kw": diesel,
            "grid_import_kw": imported,
            "grid_export_kw": exported,
            "curtailment_kw": curtailed,
            "unserved_kw": unserved,
            "soc_pct": soc,
            "planned_interval_cost_yuan": interval_cost,
        }
    )
    frame["net_grid_kw"] = frame.grid_import_kw - frame.grid_export_kw
    frame["power_balance_error_kw"] = (
        frame.pv_actual_kw
        - frame.curtailment_kw
        + frame.diesel_kw
        + frame.grid_import_kw
        - frame.grid_export_kw
        + frame.unserved_kw
        - frame.load_kw
    )
    metrics, breakdown = _calculate_metrics(frame, config)
    return DispatchResult(
        strategy_key="baseline",
        strategy_name="无储能基础方案",
        frame=frame,
        metrics=metrics,
        cost_breakdown=breakdown,
        confidence_pct=0.0,
    )


def run_all_strategies(
    data: ScenarioData,
    config: MicrogridConfig,
    confidence_pct: float = 90.0,
) -> dict[str, DispatchResult]:
    return {
        key: run_strategy(data, config, key, confidence_pct)
        for key in ("deterministic", "risk_aware", "rolling_predictive")
    }
