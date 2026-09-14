from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LauncherScriptTests(unittest.TestCase):
    def test_run_bat_prefers_portable_exe_and_keeps_diagnostics(self):
        text = (ROOT / "run.bat").read_text(encoding="utf-8")
        self.assertIn("dist\\DongMicrogridEMS\\DongMicrogridEMS.exe", text)
        self.assertIn('set "LOG_FILE=%LOG_DIR%\\startup.log"', text)
        self.assertIn("pause", text.lower())
        self.assertIn(".venv\\Scripts\\python.exe", text)

    def test_version_is_1_7(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        window_text = (ROOT / "microgrid" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn('setApplicationVersion("1.7.0")', main_text)
        self.assertIn("v1.7", window_text)


if __name__ == "__main__":
    unittest.main()
