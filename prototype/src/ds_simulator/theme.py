"""Shared visual tokens for the desktop prototype."""

BLUE = "#3264e8"
INK = "#1e2b40"
MUTED = "#7b8799"

STYLESHEET = """
QMainWindow, QWidget#root { background: #f3f5f9; }
QWidget { color: #1e2b40; font-size: 13px; }
QLabel { background: transparent; }
QFrame#header { background: white; border-bottom: 1px solid #e3e8ef; }
QFrame#sidebar { background: #142136; }
QFrame#card { background: white; border: 1px solid #e1e6ef; border-radius: 12px; }
QFrame#inset { background: #f7f9fc; border: 1px solid #e7ecf3; border-radius: 8px; }
QFrame#targetBanner { background: #edf3ff; border: 1px solid #b7cdf9; border-left: 4px solid #3264e8; border-radius: 7px; }
QFrame#previewNote { background: #1c2e49; border: 1px solid #2b4161; border-radius: 9px; }
QLabel[role="muted"] { color: #7b8799; }
QLabel[role="caption"] { color: #7b8799; font-size: 11px; }
QLabel[role="title"] { color: #19273e; font-size: 25px; font-weight: 700; }
QLabel[role="heading"] { color: #1e2b40; font-size: 15px; font-weight: 700; }
QLabel[role="stat"] { color: #1e2b40; font-size: 27px; font-weight: 700; }
QLabel[role="sidebarCaption"] { color: #8393ad; font-size: 10px; font-weight: 600; }
QLabel[role="brand"] { color: #1a2941; font-size: 17px; font-weight: 800; }
QLabel#chip { background: #edf2ff; color: #3264e8; border-radius: 5px; padding: 4px 9px; font-size: 11px; font-weight: 600; }
QLabel#greenChip { background: #eaf8f1; color: #1a9264; border-radius: 5px; padding: 4px 8px; font-size: 11px; }
QLabel#neutralChip { background: #f0f3f8; color: #73829a; border-radius: 5px; padding: 4px 8px; font-size: 11px; }
QPushButton { background: white; border: 1px solid #dce3ee; border-radius: 7px; padding: 8px 13px; font-weight: 500; }
QPushButton:hover { background: #f0f4fd; border-color: #b6c9f3; }
QPushButton:pressed { background: #e6edfc; }
QPushButton#primary { background: #3264e8; color: white; border: 1px solid #3264e8; font-weight: 600; }
QPushButton#primary:hover { background: #2754ce; }
QPushButton#primary:disabled { background: #e0e6f1; color: #8492aa; border-color: #e0e6f1; }
QPushButton#quiet { border: 0; background: transparent; color: #7b8799; padding: 4px 8px; }
QPushButton#nav { background: transparent; color: #9caec8; border: 0; text-align: left; padding: 13px 12px; border-radius: 7px; font-size: 13px; }
QPushButton#nav:hover { background: #20334f; color: white; }
QPushButton#nav:checked { background: #2c4b80; color: white; font-weight: 600; }
QPushButton#connection { text-align: left; background: #f8fafc; border: 1px solid #e7ecf3; border-radius: 8px; padding: 11px; }
QPushButton#connection:checked { background: #eff4ff; border: 1px solid #9bb9f9; color: #2c59c2; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #dfe5ee; border-radius: 6px; padding: 7px 10px; min-height: 19px; selection-background-color: #dce6ff; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #7195ef; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #eaf0ff; selection-color: #3264e8; }
QPlainTextEdit { background: #f7f9fc; border: 1px solid #e3e9f1; border-radius: 7px; padding: 7px; selection-background-color: #dce6ff; }
QTableWidget { background: white; border: 0; gridline-color: #edf1f6; outline: 0; selection-background-color: #eff4ff; selection-color: #1e2b40; alternate-background-color: #fbfcfe; }
QTableWidget::item { padding: 5px 9px; border-bottom: 1px solid #edf1f6; }
QTableWidget::item:selected { background: #eff4ff; color: #1e2b40; }
QListWidget#messageCatalog { background: white; border: 0; outline: 0; }
QListWidget#messageCatalog::item { border: 1px solid #e7ecf3; border-radius: 7px; padding: 10px 9px; margin-bottom: 8px; }
QListWidget#messageCatalog::item:selected { background: #eff4ff; border: 1px solid #9bb9f9; color: #2c59c2; }
QListWidget#messageCatalog:disabled { color: #a4adbc; background: #fafbfd; }
QLineEdit:disabled { color: #a4adbc; background: #f7f9fc; }
QHeaderView::section { background: #f7f9fc; color: #7b8799; font-size: 11px; font-weight: 500; border: 0; border-bottom: 1px solid #e5eaf2; padding: 9px; text-align: left; }
QTabWidget::pane { border: 0; }
QTabBar::tab { color: #7b8799; padding: 8px 15px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #3264e8; border-bottom: 2px solid #3264e8; font-weight: 600; }
QCheckBox { spacing: 7px; color: #6d7d92; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #ccd6e4; border-radius: 3px; background: white; }
QCheckBox::indicator:checked { background: #3264e8; border-color: #3264e8; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #d6deea; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 7px; }
QScrollBar::handle:horizontal { background: #d6deea; border-radius: 3px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QStatusBar { background: white; color: #8190a5; border-top: 1px solid #e3e8ef; font-size: 11px; }
QStatusBar::item { border: 0; }
QToolTip { background: #1e2b40; color: white; border: 0; padding: 6px; }
QDialog { background: #f3f5f9; }
"""
