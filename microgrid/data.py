"""Built-in typical-day profiles and CSV data exchange."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .models import TIME_STEPS, MicrogridConfig, ScenarioData


SCENARIO_NAMES = ("典型多云日", "夏季晴天", "高负荷工作日")
HERTZ_FILENAME = "Solarenergie_Hochrechnung_2025.csv"
HERTZ_SOURCE_NAME = "50Hertz 德国区域光伏 2025"


def _smooth_noise(rng: np.random.Generator, size: int) -> np.ndarray:
    raw = rng.normal(0.0, 1.0, size + 8)
    kernel = np.array([1, 2, 3, 4, 3, 2, 1], dtype=float)
    kernel /= kernel.sum()
    return np.convolve(raw, kernel, mode="valid")[:size]


def generate_typical_day(
    scenario_name: str,
    config: MicrogridConfig,
    seed: int = 2026,
) -> ScenarioData:
    """Generate a reproducible 96-point scenario for a 15-minute dispatch day."""

    config.validate()
    if scenario_name not in SCENARIO_NAMES:
        scenario_name = SCENARIO_NAMES[0]

    rng = np.random.default_rng(seed)
    hours = np.arange(TIME_STEPS) / 4.0
    time_labels = np.array([f"{int(h):02d}:{int(round((h % 1) * 60)):02d}" for h in hours])

    morning = 31.0 * np.exp(-0.5 * ((hours - 8.2) / 1.45) ** 2)
    daytime = 24.0 * np.exp(-0.5 * ((hours - 13.2) / 3.6) ** 2)
    evening = 48.0 * np.exp(-0.5 * ((hours - 19.3) / 1.8) ** 2)
    load = (58.0 + morning + daytime + evening) * config.load.scale
    load += 2.2 * _smooth_noise(rng, TIME_STEPS)

    daylight = np.sin(np.pi * np.clip((hours - 5.8) / 12.5, 0, 1)) ** 1.55
    pv_forecast = config.pv.capacity_kw * daylight

    if scenario_name == "典型多云日":
        cloud = 1.0 - 0.38 * np.exp(-0.5 * ((hours - 10.6) / 0.8) ** 2)
        cloud -= 0.50 * np.exp(-0.5 * ((hours - 14.8) / 0.65) ** 2)
        actual_factor = cloud + 0.10 * _smooth_noise(rng, TIME_STEPS)
    elif scenario_name == "夏季晴天":
        pv_forecast *= 1.03
        actual_factor = 0.99 + 0.045 * _smooth_noise(rng, TIME_STEPS)
        load *= 1.06 + 0.04 * np.exp(-0.5 * ((hours - 15.0) / 3.0) ** 2)
    else:
        actual_factor = 0.94 + 0.12 * _smooth_noise(rng, TIME_STEPS)
        load *= 1.22

    pv_forecast = np.clip(pv_forecast, 0.0, config.pv.capacity_kw)
    pv_actual = np.clip(pv_forecast * actual_factor, 0.0, config.pv.capacity_kw)
    pv_actual[daylight < 1e-6] = 0.0

    price = np.full(TIME_STEPS, 0.68)
    price[(hours < 7.0)] = 0.36
    price[(hours >= 7.0) & (hours < 10.0)] = 0.72
    price[(hours >= 10.0) & (hours < 12.0)] = 1.16
    price[(hours >= 12.0) & (hours < 17.0)] = 0.76
    price[(hours >= 17.0) & (hours < 22.0)] = 1.22
    price[(hours >= 22.0)] = 0.42

    result = ScenarioData(
        time_labels=time_labels,
        load_kw=np.maximum(load, 0.0),
        pv_forecast_kw=pv_forecast,
        pv_actual_kw=pv_actual,
        buy_price_yuan_kwh=price,
        source_name=f"内置场景 / {scenario_name}",
        metadata={"kind": "synthetic", "scenario_name": scenario_name},
    )
    result.validate()
    return result


def load_scenario_csv(
    path: str | Path,
    config: MicrogridConfig | None = None,
) -> ScenarioData:
    """Load a scenario CSV using the documented column names.

    Required columns: time, load_kw, pv_forecast_kw, price_yuan_kwh.
    pv_actual_kw is optional and defaults to the forecast when omitted.
    """

    csv_path = Path(path)
    # The supplied 50Hertz file has a different, German regional-data schema.
    # Detect it here so the normal Import CSV action remains useful for both formats.
    if _is_50hertz_file(csv_path):
        dates = list_50hertz_dates(csv_path)
        if not dates:
            raise ValueError("50Hertz 文件中没有可用日期")
        return load_50hertz_day(csv_path, dates[0], config)

    frame = pd.read_csv(csv_path, encoding="utf-8-sig")
    aliases = {
        "time": ("time", "时间"),
        "load_kw": ("load_kw", "负荷_kw", "负荷"),
        "pv_forecast_kw": ("pv_forecast_kw", "光伏预测_kw", "光伏预测"),
        "pv_actual_kw": ("pv_actual_kw", "光伏实测_kw", "光伏实测"),
        "price_yuan_kwh": ("price_yuan_kwh", "购电价_元_kwh", "购电价"),
    }

    def find(name: str, required: bool = True) -> pd.Series | None:
        for candidate in aliases[name]:
            if candidate in frame.columns:
                return frame[candidate]
        if required:
            raise ValueError(f"CSV 缺少列 {aliases[name][0]}")
        return None

    actual = find("pv_actual_kw", required=False)
    forecast = find("pv_forecast_kw")
    result = ScenarioData(
        time_labels=find("time").astype(str).to_numpy(),
        load_kw=pd.to_numeric(find("load_kw"), errors="coerce").to_numpy(dtype=float),
        pv_forecast_kw=pd.to_numeric(forecast, errors="coerce").to_numpy(dtype=float),
        pv_actual_kw=(
            pd.to_numeric(actual, errors="coerce").to_numpy(dtype=float)
            if actual is not None
            else pd.to_numeric(forecast, errors="coerce").to_numpy(dtype=float)
        ),
        buy_price_yuan_kwh=pd.to_numeric(find("price_yuan_kwh"), errors="coerce").to_numpy(dtype=float),
        source_name=f"CSV / {csv_path.name}",
        metadata={"kind": "csv", "path": str(csv_path)},
    )
    result.validate()
    return result


def locate_50hertz_csv(project_root: str | Path | None = None) -> Path | None:
    """Locate the bundled or source-tree 50Hertz annual CSV."""

    candidates: list[Path] = []
    if project_root is not None:
        root = Path(project_root)
        candidates.extend(
            [
                root / "sample_data" / HERTZ_FILENAME,
                root.parent.parent / "data" / HERTZ_FILENAME,
            ]
        )
    candidates.append(Path(__file__).resolve().parents[1] / "sample_data" / HERTZ_FILENAME)
    candidates.append(Path.cwd() / HERTZ_FILENAME)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_50hertz_frame(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    raw = source.read_bytes()
    text = None
    for encoding in ("utf-16", "utf-16-le", "utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            if "Datum" in text and "MW" in text:
                break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("无法识别 50Hertz 文件编码，预期为 UTF-16 或 UTF-8")
    lines = text.splitlines()
    # The export starts with a one-column summary header, then the actual
    # four-column table header after Maximum/Minimum rows.
    header_index = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("Datum;") and "MW" in line),
        None,
    )
    if header_index is None:
        raise ValueError("50Hertz 文件缺少 Datum/MW 表头")
    from io import StringIO

    frame = pd.read_csv(
        StringIO("\n".join(lines[header_index:])),
        sep=";",
        decimal=",",
        usecols=["Datum", "von", "bis", "MW"],
    )
    frame["Datum"] = pd.to_datetime(frame["Datum"], format="%d.%m.%Y", errors="coerce")
    frame["MW"] = pd.to_numeric(frame["MW"], errors="coerce")
    frame = frame.dropna(subset=["Datum", "MW"]).copy()
    frame["time"] = frame["von"].astype(str).str.strip()
    frame["date_key"] = frame["Datum"].dt.strftime("%Y-%m-%d")
    if frame.empty:
        raise ValueError("50Hertz 文件没有有效的日期和 MW 数据")
    return frame


def _is_50hertz_file(path: str | Path) -> bool:
    try:
        sample = Path(path).read_bytes()[:4096]
    except OSError:
        return False
    for encoding in ("utf-16", "utf-16-le", "utf-8-sig", "cp1252"):
        try:
            text = sample.decode(encoding, errors="ignore")
        except Exception:
            continue
        if "Datum" in text and "MW" in text and "von" in text:
            return True
    return False


def _resample_day(values: np.ndarray) -> np.ndarray:
    """Convert 92/96/97 DST-aware points to the fixed 96-point UI grid."""

    values = np.asarray(values, dtype=float)
    if len(values) == TIME_STEPS:
        return values.copy()
    if len(values) < 2:
        return np.repeat(values[0] if len(values) else 0.0, TIME_STEPS)
    source_axis = np.linspace(0.0, 1.0, len(values))
    target_axis = np.linspace(0.0, 1.0, TIME_STEPS)
    return np.interp(target_axis, source_axis, values)


def list_50hertz_dates(path: str | Path) -> list[str]:
    """Return sorted ISO dates present in the annual 50Hertz file."""

    frame = _read_50hertz_frame(path)
    return sorted(frame["date_key"].drop_duplicates().tolist())


def read_50hertz_year(path: str | Path) -> pd.DataFrame:
    """Read the complete 50Hertz annual table after removing summary rows."""

    return _read_50hertz_frame(path)


def load_50hertz_day(
    path: str | Path,
    selected_date: str | date | datetime,
    config: MicrogridConfig | None = None,
) -> ScenarioData:
    """Load one calendar day from the 50Hertz regional PV estimate.

    The annual series is normalized by its annual maximum and scaled to the
    configured microgrid PV capacity. A transparent historical same-time
    median over the prior 14 available days is used as the day-ahead forecast.
    """

    config = config or MicrogridConfig()
    config.validate()
    source = Path(path)
    frame = _read_50hertz_frame(source)
    if isinstance(selected_date, (date, datetime)):
        date_key = selected_date.strftime("%Y-%m-%d")
    else:
        date_key = str(selected_date)
    dates = sorted(frame["date_key"].unique().tolist())
    if date_key not in dates:
        raise ValueError(f"50Hertz 文件中不存在日期：{date_key}")

    annual_max = float(frame["MW"].max())
    if annual_max <= 0:
        raise ValueError("50Hertz 年度最大 MW 必须大于零")
    daily: dict[str, np.ndarray] = {}
    for key, group in frame.groupby("date_key", sort=True):
        daily[key] = _resample_day(group.sort_values(["Datum", "von"])["MW"].to_numpy())
    actual = np.clip(daily[date_key] / annual_max * config.pv.capacity_kw, 0.0, config.pv.capacity_kw)

    selected_index = dates.index(date_key)
    history = [daily[key] for key in dates[max(0, selected_index - 14):selected_index]]
    if history:
        forecast = np.median(np.vstack(history), axis=0) / annual_max * config.pv.capacity_kw
    else:
        # First day of the year has no historical window; keep the forecast
        # conservative while remaining deterministic and explainable.
        forecast = actual * 0.92
    forecast = np.clip(forecast, 0.0, config.pv.capacity_kw)
    hours = np.arange(TIME_STEPS) / 4.0
    time_labels = np.array([f"{int(h):02d}:{int(round((h % 1) * 60)):02d}" for h in hours])

    # Reuse the standard representative load and tariff profile; the external
    # data source replaces the PV curve while leaving the course-scale load
    # model explicit and reproducible.
    typical = generate_typical_day(SCENARIO_NAMES[0], config)
    metadata = {
        "kind": "50hertz",
        "provider": "50Hertz",
        "path": str(source),
        "selected_date": date_key,
        "year": 2025,
        "annual_max_mw": annual_max,
        "raw_points": int(len(frame[frame["date_key"] == date_key])),
        "forecast_method": "过去14天同一时刻中位数；首日为实际曲线的92%保守估计",
        "dst_resampled": int(len(frame[frame["date_key"] == date_key])) != TIME_STEPS,
        "is_forecast_official": False,
    }
    result = ScenarioData(
        time_labels=time_labels,
        load_kw=typical.load_kw,
        pv_forecast_kw=forecast,
        pv_actual_kw=actual,
        buy_price_yuan_kwh=typical.buy_price_yuan_kwh,
        source_name=f"{HERTZ_SOURCE_NAME} / {date_key}",
        metadata=metadata,
    )
    result.validate()
    return result


def scenario_to_frame(data: ScenarioData) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": data.time_labels,
            "load_kw": data.load_kw,
            "pv_forecast_kw": data.pv_forecast_kw,
            "pv_actual_kw": data.pv_actual_kw,
            "price_yuan_kwh": data.buy_price_yuan_kwh,
        }
    )
