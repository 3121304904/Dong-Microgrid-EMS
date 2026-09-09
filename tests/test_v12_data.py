from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from microgrid.data import (
    HERTZ_FILENAME,
    list_50hertz_dates,
    load_50hertz_day,
    read_50hertz_year,
)
from microgrid.models import TIME_STEPS, default_config


class HertzDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = Path(__file__).resolve().parents[1] / "sample_data" / HERTZ_FILENAME
        cls.config = default_config()

    def test_year_profile_and_dst_day_lengths(self) -> None:
        frame = read_50hertz_year(self.path)
        dates = list_50hertz_dates(self.path)
        self.assertEqual(len(dates), 365)
        self.assertEqual(len(frame[frame.date_key == "2025-03-30"]), 92)
        self.assertEqual(len(frame[frame.date_key == "2025-10-26"]), 97)

    def test_day_is_resampled_and_scaled(self) -> None:
        for date_key in ("2025-01-15", "2025-03-30", "2025-10-26"):
            data = load_50hertz_day(self.path, date_key, self.config)
            self.assertEqual(len(data.time_labels), TIME_STEPS)
            self.assertGreaterEqual(float(data.pv_actual_kw.min()), 0.0)
            self.assertLessEqual(float(data.pv_actual_kw.max()), self.config.pv.capacity_kw + 1e-9)
            self.assertEqual(data.metadata["selected_date"], date_key)
            self.assertEqual(data.metadata["kind"], "50hertz")

    def test_forecast_uses_history_without_mutating_actual(self) -> None:
        data = load_50hertz_day(self.path, "2025-06-20", self.config)
        actual = data.pv_actual_kw.copy()
        self.assertTrue(np.isfinite(data.pv_forecast_kw).all())
        self.assertFalse(np.array_equal(actual, data.pv_forecast_kw))
        self.assertTrue(np.array_equal(actual, data.pv_actual_kw))


if __name__ == "__main__":
    unittest.main()
