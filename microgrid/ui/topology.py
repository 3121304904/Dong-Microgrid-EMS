"""Interactive topology scene for the microgrid components."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsObject, QGraphicsScene, QGraphicsView, QMenu

from ..models import MicrogridConfig


class ComponentNode(QGraphicsObject):
    edit_requested = Signal(str)

    def __init__(self, component: str, title: str, detail: str, color: str) -> None:
        super().__init__()
        self.component = component
        self.title = title
        self.detail = detail
        self.color = QColor(color)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{title}\n右键修改组件参数")
        self._hovered = False

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 156, 76)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor("#F7FAFA") if self._hovered else QColor("#FFFFFF")
        painter.setBrush(QBrush(background))
        painter.setPen(QPen(self.color if self._hovered else QColor("#CCD6DC"), 1.6))
        painter.drawRoundedRect(self.boundingRect(), 6, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.color))
        painter.drawRoundedRect(QRectF(12, 16, 8, 44), 3, 3)
        painter.setPen(QPen(QColor("#17212B")))
        font = QFont("Microsoft YaHei UI", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(30, 13, 114, 25), Qt.AlignmentFlag.AlignLeft, self.title)
        painter.setPen(QPen(QColor("#637083")))
        detail_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(detail_font)
        painter.drawText(QRectF(30, 38, 116, 23), Qt.AlignmentFlag.AlignLeft, self.detail)

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu()
        action = menu.addAction("修改组件参数")
        selected = menu.exec(event.screenPos())
        if selected == action:
            self.edit_requested.emit(self.component)


class TopologyView(QGraphicsView):
    edit_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(350)
        self.setStyleSheet("QGraphicsView { background: #FFFFFF; border: none; }")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def update_config(self, config: MicrogridConfig) -> None:
        scene = self.scene()
        scene.clear()
        scene.setSceneRect(0, 0, 760, 330)
        nodes = [
            ("pv", "光伏阵列", f"{config.pv.capacity_kw:.0f} kW", "#D69B21", 40, 35),
            ("battery", "储能系统", f"{config.battery.capacity_kwh:.0f} kWh", "#18785C", 40, 220),
            ("grid", "公共电网", f"购电上限 {config.grid.import_limit_kw:.0f} kW", "#2B6CB0", 560, 35),
            ("diesel", "柴油发电机", f"{config.diesel.max_power_kw:.0f} kW", "#C46731", 560, 220),
            ("load", "园区综合负荷", f"负荷倍率 {config.load.scale:.2f}", "#273442", 302, 130),
        ]
        center = (380, 168)
        pen = QPen(QColor("#9CAAB2"), 2.0)
        bus_pen = QPen(QColor("#50616D"), 3.0)
        scene.addLine(225, center[1], 535, center[1], bus_pen)
        scene.addLine(225, 73, 225, 258, pen)
        scene.addLine(535, 73, 535, 258, pen)
        scene.addLine(225, 73, 196, 73, pen)
        scene.addLine(225, 258, 196, 258, pen)
        scene.addLine(535, 73, 560, 73, pen)
        scene.addLine(535, 258, 560, 258, pen)
        scene.addEllipse(center[0] - 5, center[1] - 5, 10, 10, QPen(QColor("#173B36")), QBrush(QColor("#173B36")))
        for component, title, detail, color, x, y in nodes:
            node = ComponentNode(component, title, detail, color)
            node.setPos(x, y)
            node.edit_requested.connect(self.edit_requested)
            scene.addItem(node)
        hint = scene.addText("右键组件可修改参数")
        hint.setDefaultTextColor(QColor("#637083"))
        hint.setFont(QFont("Microsoft YaHei UI", 8))
        hint.setPos(305, 300)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
