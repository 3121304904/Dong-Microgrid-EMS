from __future__ import annotations

import unittest

import numpy as np

from microgrid.data import SCENARIO_NAMES, generate_typical_day
from microgrid.models import TIME_STEPS, default_config
from microgrid.scheduler import run_rolling_predictive


class RollingPredictiveTests(unittest.TestCase):
    def test_rolling_output_and_replan_points(self) -> None:
        config = default_config()
        data = generate_typical_day(SCENARIO_NAMES[0], config)
        result = run_rolling_predictive(data, config)
        frame = result.frame
        self.assertEqual(len(frame), TIME_STEPS)
        self.assertTrue(np.isfinite(frame.rolling_forecast_kw).all())
        self.assertTrue((frame.rolling_forecast_kw >= -1e-9).all())
        self.assertTrue((frame.rolling_forecast_kw <= config.pv.capacity_kw + 1e-9).all())
        self.assertEqual(frame.index[frame.replan_flag.astype(bool)].tolist(), list(range(0, 96, 4)))
        self.assertLess(float(frame.power_balance_error_kw.abs().max()), 1e-7)
        self.assertGreaterEqual(float(frame.soc_pct.min()), config.battery.min_soc * 100 - 1e-6)
        self.assertLessEqual(float(frame.soc_pct.max()), config.battery.max_soc * 100 + 1e-6)
        self.assertTrue(set(frame.grid_status.unique()).issubset({"正常", "电网紧张", "高价削峰", "保供告警"}))

    def test_rolling_is_reproducible_and_does_not_mutate_input(self) -> None:
        config = default_config()
        data = generate_typical_day(SCENARIO_NAMES[1], config)
        pv = data.pv_actual_kw.copy()
        first = run_rolling_predictive(data, config)
        second = run_rolling_predictive(data, config)
        self.assertTrue(first.frame.equals(second.frame))
        self.assertTrue(np.array_equal(data.pv_actual_kw, pv))


if __name__ == "__main__":
    unittest.main()
