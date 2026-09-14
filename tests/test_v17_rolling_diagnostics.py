from __future__ import annotations

import unittest

import numpy as np

from microgrid.data import SCENARIO_NAMES, generate_typical_day
from microgrid.models import default_config
from microgrid.scheduler import run_rolling_predictive


class V17RollingDiagnosticsTests(unittest.TestCase):
    def test_rolling_diagnostics_expose_trace_and_uncertainty(self):
        config = default_config()
        data = generate_typical_day(SCENARIO_NAMES[0], config)
        result = run_rolling_predictive(data, config)
        frame = result.frame
        self.assertIn("forecast_error_kw", frame)
        self.assertIn("forecast_sigma_kw", frame)
        self.assertGreaterEqual(len(result.diagnostics["rolling_trace"]), 20)
        self.assertTrue(np.isfinite(frame.forecast_sigma_kw).all())
        self.assertTrue((frame.horizon_end_index >= 0).all())


if __name__ == "__main__":
    unittest.main()
