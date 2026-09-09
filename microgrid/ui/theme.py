"""Application palette and Qt style sheet."""

COLORS = {
    "ink": "#17212B",
    "muted": "#637083",
    "subtle": "#8B97A8",
    "surface": "#FFFFFF",
    "canvas": "#F4F7F8",
    "border": "#DDE4E8",
    "primary": "#18785C",
    "primary_hover": "#12654D",
    "pv": "#D69B21",
    "grid": "#2B6CB0",
    "battery": "#18785C",
    "diesel": "#C46731",
    "danger": "#C43D3D",
}


APP_STYLE = r"""
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
    letter-spacing: 0px;
}
QMainWindow, QWidget#root {
    background: #F4F7F8;
    color: #17212B;
}
QWidget#appHeader {
    background: #173B36;
    border: none;
}
QLabel#brandTitle {
    color: #FFFFFF;
    font-size: 18px;
    font-weight: 700;
}
QLabel#brandSubtitle, QLabel#headerMeta {
    color: #BFD3CE;
    font-size: 12px;
}
QFrame#sidePanel {
    background: #FFFFFF;
    border-right: 1px solid #DDE4E8;
}
QFrame#section, QFrame#chartPanel, QFrame#tablePanel {
    background: #FFFFFF;
    border: 1px solid #DDE4E8;
    border-radius: 6px;
}
QFrame#kpiCard {
    background: #FFFFFF;
    border: 1px solid #DDE4E8;
    border-left: 4px solid #18785C;
    border-radius: 5px;
}
QLabel#sectionTitle {
    color: #17212B;
    font-size: 14px;
    font-weight: 700;
}
QLabel#fieldLabel, QLabel#muted, QLabel#kpiLabel {
    color: #637083;
    font-size: 12px;
}
QLabel#kpiValue {
    color: #17212B;
    font-size: 21px;
    font-weight: 700;
}
QLabel#kpiHint {
    color: #637083;
    font-size: 11px;
}
QPushButton {
    min-height: 32px;
    padding: 0 12px;
    border: 1px solid #CCD6DC;
    border-radius: 5px;
    background: #FFFFFF;
    color: #273442;
}
QPushButton:hover {
    background: #F0F5F4;
    border-color: #9FB4AE;
}
QPushButton:focus {
    border: 2px solid #2B6CB0;
}
QPushButton#primaryButton {
    background: #18785C;
    color: #FFFFFF;
    border-color: #18785C;
    font-weight: 700;
    min-height: 38px;
}
QPushButton#primaryButton:hover {
    background: #12654D;
}
QPushButton#iconButton {
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    padding: 0;
}
QToolButton#headerAction {
    color: #EAF3F1;
    background: transparent;
    border: 1px solid #496A64;
    border-radius: 4px;
    padding: 0 8px;
    font-weight: 600;
}
QToolButton#headerAction:hover {
    background: #244D46;
    border-color: #76938E;
}
QToolButton#headerAction:focus {
    border: 2px solid #8DBEB0;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    min-height: 30px;
    padding: 0 8px;
    background: #FFFFFF;
    border: 1px solid #CCD6DC;
    border-radius: 4px;
    selection-background-color: #18785C;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 2px solid #2B6CB0;
}
QComboBox::drop-down {
    width: 24px;
    border: none;
}
QTabWidget::pane {
    border: none;
    background: transparent;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #637083;
    padding: 10px 17px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}
QTabBar::tab:selected {
    color: #18785C;
    border-bottom: 2px solid #18785C;
}
QTabBar::tab:hover:!selected {
    color: #273442;
    background: #EAF0F0;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7F9FA;
    border: 1px solid #DDE4E8;
    gridline-color: #E7ECEF;
    selection-background-color: #DDEFE9;
    selection-color: #17212B;
}
QHeaderView::section {
    background: #EDF2F3;
    color: #384755;
    border: none;
    border-right: 1px solid #DDE4E8;
    border-bottom: 1px solid #DDE4E8;
    padding: 7px;
    font-weight: 700;
}
QScrollBar:vertical {
    width: 10px;
    background: #F0F3F4;
}
QScrollBar::handle:vertical {
    background: #BAC6CC;
    min-height: 28px;
    border-radius: 4px;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #D7E0E3;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 16px;
    margin: -6px 0;
    background: #18785C;
    border: 2px solid #FFFFFF;
    border-radius: 8px;
}
QProgressBar {
    background: #E7ECEF;
    border: 1px solid #D3DCE0;
    border-radius: 4px;
    color: #273442;
    text-align: center;
}
QProgressBar::chunk {
    background: #18785C;
    border-radius: 3px;
}
QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #DDE4E8;
    color: #637083;
}
QToolTip {
    background: #17212B;
    color: #FFFFFF;
    border: none;
    padding: 5px;
}
"""
