"""Small, non-layout-shifting Qt animations used by the v1.4 workbench."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QAbstractButton, QGraphicsOpacityEffect, QTabWidget, QWidget


def clear_effect(widget: QWidget) -> None:
    """Stop and remove transient effects so hidden pages cannot bleed through."""

    if widget is None:
        return
    animation = getattr(widget, "_dong_animation", None)
    if animation is not None:
        animation.stop()
        animation.deleteLater()
        widget._dong_animation = None
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        widget.setGraphicsEffect(None)


def clear_tree_effects(root: QWidget) -> None:
    """Remove transient effects from a page and every animated child."""

    clear_effect(root)
    for child in root.findChildren(QWidget):
        clear_effect(child)


def _finish_transient(widget: QWidget, animation: QPropertyAnimation) -> None:
    if getattr(widget, "_dong_animation", None) is animation:
        clear_effect(widget)


def fade_in(widget: QWidget, duration: int = 180) -> None:
    if widget is None:
        return
    clear_effect(widget)
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.72)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._dong_animation = animation
    animation.finished.connect(lambda: _finish_transient(widget, animation))
    animation.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)


def pulse(widget: QWidget, duration: int = 150) -> None:
    """Give a KPI or button a short opacity pulse without changing geometry."""

    if widget is None:
        return
    clear_effect(widget)
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setKeyValueAt(0.0, 0.68)
    animation.setKeyValueAt(0.45, 1.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._dong_animation = animation
    animation.finished.connect(lambda: _finish_transient(widget, animation))
    animation.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)


def install_tab_fade(tabs: QTabWidget) -> None:
    def on_changed(index: int) -> None:
        # QTabWidget keeps neighboring pages alive. Never fade the page root:
        # a translucent root composites the previous page underneath it.
        # Animate only opaque child panels and clear all old effects first.
        for page_index in range(tabs.count()):
            page = tabs.widget(page_index)
            if page is not None:
                clear_tree_effects(page)
        current = tabs.widget(index)
        if current is not None:
            animate_sections(current)

    tabs.currentChanged.connect(on_changed)
    if tabs.count():
        animate_sections(tabs.currentWidget(), delay_ms=45)


def animate_sections(root: QWidget, delay_ms: int = 35) -> None:
    """Reveal visible direct child panels in sequence after a page appears."""

    if root is None:
        return
    panels = [
        child for child in root.findChildren(QWidget)
        if child.parentWidget() is root and child.isVisible()
    ]
    for index, panel in enumerate(panels[:8]):
        QTimer.singleShot(index * delay_ms, lambda target=panel: fade_in(target, 160))


def install_button_feedback(root: QWidget) -> None:
    for button in root.findChildren(QAbstractButton):
        if getattr(button, "_dong_feedback_installed", False):
            continue
        button._dong_feedback_installed = True
        button.clicked.connect(lambda _checked=False, target=button: pulse(target))
