from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from microgrid.data import SCENARIO_NAMES, generate_typical_day
from microgrid.models import default_config
from microgrid.scheduler import run_strategy
from microgrid.ui.main_window import MainWindow
from microgrid.ui.replay_page import ReplayPage


class UiBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.config = default_config()
        cls.data = generate_typical_day(SCENARIO_NAMES[0], cls.config)
        cls.result = run_strategy(cls.data, cls.config, "deterministic", 90.0)

    def test_replay_controls_and_end_state(self) -> None:
        page = ReplayPage()
        page.set_result(self.result, self.config)
        self.assertEqual(page.current_index, 0)
        page.step_forward()
        self.assertEqual(page.current_index, 1)
        page.play()
        self.assertTrue(page.timer.isActive())
        page.pause()
        self.assertFalse(page.timer.isActive())
        page.set_index(95)
        page.step_forward()
        self.assertEqual(page.current_index, 95)
        page.set_index(37)
        self.assertEqual(page.position_slider.value(), 37)
        page.reset()
        self.assertEqual(page.current_index, 0)
        page.select_midday()
        self.assertEqual(page.current_index, 52)
        page.close()

    def test_main_window_contains_seven_pages(self) -> None:
        root = Path(__file__).resolve().parents[1]
        window = MainWindow(root)
        self.assertEqual(window.tabs.count(), 7)
        self.assertEqual(
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
            ["运行总览", "实时仿真", "微电网拓扑", "策略对比", "场景实验室", "96 时段明细", "运行报告"],
        )
        window.close()


if __name__ == "__main__":
    unittest.main()
