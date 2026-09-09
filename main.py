"""Dong Microgrid EMS application entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dong 微电网能源管理系统")
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="在离屏模式启动并保存界面截图，用于自动化界面检查",
    )
    parser.add_argument(
        "--screenshot-tab",
        choices=("overview", "replay", "rolling", "topology", "comparison", "lab", "details", "report"),
        default="overview",
        help="截图时自动切换到指定页面",
    )
    parser.add_argument(
        "--window-size",
        default="1500x920",
        help="截图窗口尺寸，例如 1180x760",
    )
    return parser.parse_args()


def parse_window_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("窗口尺寸必须使用 WIDTHxHEIGHT 格式") from exc
    if width < 1180 or height < 760:
        raise ValueError("窗口尺寸不能小于 1180x760")
    return width, height


def main() -> int:
    arguments = parse_arguments()
    # Matplotlib's Windows font discovery expects WINDIR even in restricted
    # or packaged processes where only SystemRoot may be inherited.
    os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", r"C:\Windows"))
    if arguments.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print(f"缺少 PySide6 或其运行库：{exc}。请先双击 setup.bat 安装运行环境。", file=sys.stderr)
        return 2

    from microgrid.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Dong 微电网能源管理系统")
    app.setApplicationVersion("1.4.0")
    app.setOrganizationName("SEU Course Design")
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for font_file in ("msyh.ttc", "msyhbd.ttc"):
        font_path = windows_fonts / font_file
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Microsoft YaHei UI", 9))
    project_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    window = MainWindow(project_root)
    try:
        width, height = parse_window_size(arguments.window_size)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    window.resize(width, height)
    window.show()

    if arguments.screenshot:
        target = arguments.screenshot.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            window.grab().save(str(target), "PNG")
            app.quit()

        def prepare_capture() -> None:
            delay = window.prepare_screenshot_tab(arguments.screenshot_tab)
            QTimer.singleShot(delay, capture)

        QTimer.singleShot(5200, prepare_capture)
    elif arguments.screenshot_tab != "overview":
        QTimer.singleShot(5200, lambda: window.prepare_screenshot_tab(arguments.screenshot_tab))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
