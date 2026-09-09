"""Core scheduling regression tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from microgrid.data import SCENARIO_NAMES, generate_typical_day, load_scenario_csv, scenario_to_frame
from microgrid.io_utils import export_dispatch_csv, export_summary_json
from microgrid.models import TIME_STEPS, default_config
from microgrid.scheduler import build_forecast_envelope, run_all_strategies


class SchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = default_config()
        cls.data = generate_typical_day(SCENARIO_NAMES[0], cls.config)
        cls.results = run_all_strategies(cls.data, cls.config, 90)

    def test_typical_day_has_96_quarter_hour_points(self) -> None:
        self.assertEqual(len(self.data.time_labels), TIME_STEPS)
        self.assertEqual(self.data.time_labels[0], "00:00")
        self.assertEqual(self.data.time_labels[-1], "23:45")

    def test_forecast_envelope_contains_median(self) -> None:
        envelope = build_forecast_envelope(self.data, self.config, 90)
        self.assertTrue(np.all(envelope.lower_kw <= envelope.median_kw + 1e-9))
        self.assertTrue(np.all(envelope.median_kw <= envelope.upper_kw + 1e-9))
        self.assertTrue(np.all(envelope.lower_kw >= 0))

    def test_dispatch_respects_power_balance_and_limits(self) -> None:
        for result in self.results.values():
            frame = result.frame
            self.assertLess(float(frame.power_balance_error_kw.abs().max()), 1e-7)
            self.assertGreaterEqual(float(frame.soc_pct.min()), 100 * self.config.battery.min_soc - 1e-6)
            self.assertLessEqual(float(frame.soc_pct.max()), 100 * self.config.battery.max_soc + 1e-6)
            self.assertLessEqual(float(frame.battery_kw.max()), self.config.battery.max_discharge_kw + 1e-6)
            self.assertGreaterEqual(float(frame.battery_kw.min()), -self.config.battery.max_charge_kw - 1e-6)
            self.assertLessEqual(float(frame.grid_import_kw.max()), self.config.grid.import_limit_kw + 1e-6)
            self.assertLessEqual(float(frame.diesel_kw.max()), self.config.diesel.max_power_kw + 1e-6)

    def test_dispatch_metrics_are_finite(self) -> None:
        for result in self.results.values():
            self.assertTrue(all(np.isfinite(value) for value in result.metrics.values()))
            self.assertGreater(result.metrics["total_cost_yuan"], 0)
            self.assertLess(result.metrics["unserved_kwh"], 1e-7)

    def test_day_end_soc_is_close_to_initial(self) -> None:
        initial_pct = self.config.battery.initial_soc * 100
        for result in self.results.values():
            self.assertLess(abs(result.metrics["final_soc_pct"] - initial_pct), 1.5)

    def test_csv_import_and_result_export_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.csv"
            scenario_to_frame(self.data).to_csv(
                scenario_path, index=False, encoding="utf-8-sig"
            )
            loaded = load_scenario_csv(scenario_path)
            self.assertEqual(len(loaded.time_labels), TIME_STEPS)
            self.assertTrue(np.allclose(loaded.load_kw, self.data.load_kw))

            result = self.results["risk_aware"]
            csv_path = export_dispatch_csv(result, root / "dispatch.csv")
            json_path = export_summary_json(result, root / "summary.json")
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            self.assertIn("total_cost_yuan", json_path.read_text(encoding="utf-8"))

    def test_all_builtin_scenarios_complete_without_shortage(self) -> None:
        for scenario_name in SCENARIO_NAMES:
            with self.subTest(scenario=scenario_name):
                data = generate_typical_day(scenario_name, self.config)
                results = run_all_strategies(data, self.config, 90)
                for result in results.values():
                    self.assertLess(result.metrics["unserved_kwh"], 1e-7)
                    self.assertLess(
                        float(result.frame.power_balance_error_kw.abs().max()),
                        1e-7,
                    )


if __name__ == "__main__":
    unittest.main()
