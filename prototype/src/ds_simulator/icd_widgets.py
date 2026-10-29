"""Shared field inputs for the manual composer and scenario inspector."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QComboBox, QLineEdit, QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from .icd import IcdMessage, FIXED_COLUMNS, DEFAULT_FIXED_HEADERS


class ChoiceCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#637b9c'))
        x, y = self.width() - 16, self.height() / 2
        painter.drawPolygon(QPolygonF([QPointF(x - 4, y - 2), QPointF(x + 4, y - 2), QPointF(x, y + 3)]))


def make_field_input(message, key, value):
    element = next((f for f in message.elements if f.key == key), None) if isinstance(message, IcdMessage) else None
    if element is not None and element.choices:
        widget = ChoiceCombo()
        widget.setMinimumContentsLength(12)
        widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.addItems(element.choices)
        widget.setEditable(False)
        for i, choice in enumerate(element.choices):
            widget.setItemData(i, choice, Qt.ItemDataRole.ToolTipRole)
        widget.setCurrentText(value)
        widget.setToolTip(value)
        widget.currentTextChanged.connect(widget.setToolTip)
        return widget
    widget = QLineEdit(value)
    if element is not None and message.current_layout:
        widget.setReadOnly(True)
        widget.setPlaceholderText('선택값 없음')
        widget.setToolTip('M열에 선택값이 없어 변경할 수 없습니다. C~K의 ICD 원본 정의는 유지됩니다.')
    return widget


class IcdFieldTable(QWidget):
    """One row per element; C/D and M stay visible while E:K scroll horizontally."""
    def __init__(self, message, values, changed, parent=None):
        super().__init__(parent)
        self.inputs = {}
        self.message = message
        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        headers = message.fixed_headers or DEFAULT_FIXED_HEADERS
        captions = [f'{column} · {title}' for column, title in zip(FIXED_COLUMNS, headers)]
        self.identity = self.make_table(captions[:2], len(message.elements))
        self.details = self.make_table(captions[2:], len(message.elements))
        self.settings = self.make_table(['M · 사용자 설정값' if message.current_layout else '이전 설정값 (E열)'], len(message.elements))
        self.identity.setFixedWidth(184)
        self.identity.setColumnWidth(0, 64)
        self.identity.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.identity.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.settings.setFixedWidth(190)
        self.settings.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.settings.setStyleSheet('QTableWidget { background: #f1f5ff; border: 1px solid #cddaff; border-radius: 0; } QHeaderView::section { background: #e6eeff; color: #285ac6; padding: 7px 4px; border: 0; }')
        for column in range(7):
            self.details.setColumnWidth(column, 145)
        self.details.setMinimumWidth(85)
        self.details.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.details.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        spacer_height = self.details.horizontalScrollBar().sizeHint().height()
        for side in (self.identity, self.settings):
            side.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            side.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        def side_container(view):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(view, 1)
            spacer = QWidget(); spacer.setFixedHeight(spacer_height)
            layout.addWidget(spacer)
            return container
        body.addWidget(side_container(self.identity))
        body.addWidget(self.details, 1)
        body.addWidget(side_container(self.settings))
        self.tables = (self.identity, self.details, self.settings)
        for source in self.tables:
            for target in self.tables:
                if source is not target:
                    source.verticalScrollBar().valueChanged.connect(target.verticalScrollBar().setValue)
        for index, field in enumerate(message.elements):
            fixed = field.fixed if message.current_layout else (field.sequence, field.name, *('' for _ in range(7)))
            for column, text in enumerate(fixed):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setToolTip(text)
                (self.identity if column < 2 else self.details).setItem(index, column if column < 2 else column - 2, item)
            widget = make_field_input(message, field.key, values[field.key])
            connect_input(widget, lambda value, key=field.key: changed(key, value))
            self.inputs[field.key] = widget
            self.settings.setCellWidget(index, 0, widget)
            height = max(44, min(76, max(text.count('\n') + 1 for text in fixed) * 18 + 12))
            for view in self.tables:
                view.setRowHeight(index, height)
        self.setMinimumHeight(220)
        self.setMinimumWidth(450)

    @staticmethod
    def make_table(headers, count):
        view = QTableWidget(count, len(headers))
        view.setHorizontalHeaderLabels(headers)
        view.horizontalHeader().setFixedHeight(40)
        for column, caption in enumerate(headers):
            view.horizontalHeaderItem(column).setToolTip(caption)
        view.verticalHeader().hide()
        view.setAlternatingRowColors(True)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setStyleSheet('QTableWidget { border: 1px solid #e0e6f0; border-radius: 0; background: #f8fafc; }')
        return view


def input_value(widget):
    return widget.currentText() if isinstance(widget, QComboBox) else widget.text()


def connect_input(widget, callback, user_only=False):
    signal = widget.currentTextChanged if isinstance(widget, QComboBox) else (widget.textEdited if user_only else widget.textChanged)
    signal.connect(callback)
