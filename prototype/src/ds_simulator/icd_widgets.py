"""Shared field inputs for the manual composer and scenario inspector."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QComboBox, QLineEdit
from .icd import IcdMessage


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
        widget.setCurrentText(value)
        return widget
    return QLineEdit(value)


def input_value(widget):
    return widget.currentText() if isinstance(widget, QComboBox) else widget.text()


def connect_input(widget, callback, user_only=False):
    signal = widget.currentTextChanged if isinstance(widget, QComboBox) else (widget.textEdited if user_only else widget.textChanged)
    signal.connect(callback)
