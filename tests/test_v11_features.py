from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from microgrid.analysis import (
    MonteCarloSettings,
    SensitivitySettings,
    run_monte_carlo,
    run_sensitivity_analysis,
)
from microgrid.data import SCENARIO_NAMES, generate_typical_day
from microgrid.models import default_config
from microgrid.project import ProjectDocument, load_project, save_project
from microgrid.reporting import export_report_bundle
from microgrid.scheduler import run_all_strategies, run_baseline


class V11FeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = default_config()
        cls.data = generate_typical_day(SCENARIO_NAMES[0], cls.config)

    def test_baseline_balances_power_without_battery(self) -> None:
        result = run_baseline(self.data, self.config)
        self.assertTrue(np.allclose(result.frame.battery_kw, 0.0))
        self.assertLess(result.frame.power_balance_error_kw.abs().max(), 1e-8)
        self.assertTrue(np.isfinite(list(result.metrics.values())).all())

    def test_monte_carlo_is_reproducible_and_ordered(self) -> None:
        settings = MonteCarloSettings(sample_count=20, seed=2026)
        first = run_monte_carlo(self.data, self.config, settings=settings)
        second = run_monte_carlo(self.data, self.config, settings=settings)
        self.assertEqual(len(first.samples), settings.sample_count * 2)
        self.assertTrue(first.samples.equals(second.samples))
        self.assertTrue(first.summary.equals(second.summary))
        self.assertTrue((first.summary.p05 <= first.summary.p50).all())
        self.assertTrue((first.summary.p50 <= first.summary.p95).all())

    def test_sensitivity_has_requested_points_and_preserves_inputs(self) -> None:
        original_capacity = self.config.battery.capacity_kwh
        original_actual = self.data.pv_actual_kw.copy()
        settings = SensitivitySettings(
            variable="battery_capacity_kwh",
            minimum=60.0,
            maximum=180.0,
            points=3,
        )
        result = run_sensitivity_analysis(self.data, self.config, settings=settings)
        self.assertEqual(result.points.parameter_value.tolist(), [60.0, 120.0, 180.0])
        self.assertTrue(np.isfinite(result.points.select_dtypes(include="number")).all().all())
        self.assertEqual(self.config.battery.capacity_kwh, original_capacity)
        self.assertTrue(np.array_equal(self.data.pv_actual_kw, original_actual))

    def test_project_round_trip_and_invalid_documents(self) -> None:
        document = ProjectDocument("v1.1 测试项目", self.config, self.data, "risk_aware", 92.0)
        with tempfile.TemporaryDirectory() as temporary:
            path = save_project(document, Path(temporary) / "example")
            loaded = load_project(path)
            self.assertEqual(loaded.project_name, document.project_name)
            self.assertEqual(loaded.strategy_key, "risk_aware")
            self.assertTrue(np.array_equal(loaded.scenario.load_kw, self.data.load_kw))

            invalid_path = Path(temporary) / "invalid.dong"
            invalid_path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不是有效 JSON"):
                load_project(invalid_path)

            unknown_path = Path(temporary) / "unknown.dong"
            payload = document.to_dict()
            payload["schema_version"] = 99
            unknown_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不支持的项目版本"):
                load_project(unknown_path)

    def test_report_bundle_contains_expected_artifacts(self) -> None:
        baseline = run_baseline(self.data, self.config)
        results = run_all_strategies(self.data, self.config, 90.0)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = export_report_bundle(
                temporary,
                "v1.1 测试项目",
                self.data,
                self.config,
                baseline,
                results,
            )
            expected = {
                "RUN_REPORT.md",
                "summary.json",
                "dispatch_baseline.csv",
                "dispatch_deterministic.csv",
                "dispatch_risk_aware.csv",
            }
            self.assertTrue(expected.issubset({path.name for path in Path(temporary).iterdir()}))
            self.assertTrue(bundle.markdown_path.exists())
            self.assertGreaterEqual(len(bundle.chart_paths), 2)


if __name__ == "__main__":
    unittest.main()
