"""Presentation-only widgets. Plot points are generated for visual review."""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .theme import BLUE, INK, MUTED


def label(text: str, role: str = "", *, color: str = "") -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if color:
        widget.setStyleSheet(f"color: {color};")
    return widget


def chip(text: str, kind: str = "chip") -> QLabel:
    widget = label(text)
    widget.setObjectName(kind)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return widget


def row(*widgets: QWidget, spacing: int = 10) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


def button(text: str, *, primary: bool = False, icon_name: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    if icon_name:
        widget.setIcon(icon(icon_name, "#ffffff" if primary else "#71829d"))
        widget.setIconSize(QSize(16, 16))
    return widget


def icon(name: str, color: str = "#8fa4c3", size: int = 20) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == "grid":
        for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
            painter.drawRoundedRect(QRectF(x, y, 7, 7), 1.5, 1.5)
    elif name == "file":
        painter.drawRoundedRect(QRectF(5, 2, 14, 20), 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(9, y, 15, y)
    elif name == "wave":
        path = QPainterPath(QPointF(2, 14))
        for point in ((6, 14), (9, 5), (12, 20), (16, 9), (19, 14), (22, 14)):
            path.lineTo(*point)
        painter.drawPath(path)
    elif name == "plus":
        painter.drawLine(12, 4, 12, 20)
        painter.drawLine(4, 12, 20, 12)
    elif name == "arrow":
        painter.drawLine(4, 12, 20, 12)
        painter.drawLine(14, 6, 20, 12)
        painter.drawLine(14, 18, 20, 12)
    elif name == "download":
        painter.drawLine(12, 3, 12, 15)
        painter.drawLine(7, 10, 12, 15)
        painter.drawLine(17, 10, 12, 15)
        painter.drawPolyline([QPointF(4, 16), QPointF(4, 21), QPointF(20, 21), QPointF(20, 16)])
    elif name == "link":
        painter.drawRoundedRect(QRectF(2, 8, 9, 8), 3, 3)
        painter.drawRoundedRect(QRectF(13, 8, 9, 8), 3, 3)
        painter.drawLine(8, 12, 16, 12)
    elif name == "folder":
        path = QPainterPath(QPointF(3, 6))
        for point in ((10, 6), (12, 9), (21, 9), (21, 20), (3, 20), (3, 6)):
            path.lineTo(*point)
        painter.drawPath(path)
    elif name == "logo":
        for x, height in ((4, 7), (10, 15), (16, 11)):
            painter.fillRect(QRectF(x, 20 - height, 4, height), QColor(color))
    painter.end()
    return QIcon(pixmap)


class Card(QFrame):
    def __init__(self, title: str = "", badge: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(12)
        if title:
            header = row(label(title, "heading"))
            header.addStretch()
            if badge:
                header.addWidget(chip(badge, "neutralChip"))
            self.body.addLayout(header)


def table(headers: list[str], rows: list[list[str]], *, stretch_column: int = -1) -> QTableWidget:
    widget = QTableWidget(len(rows), len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(36)
    widget.setShowGrid(False)
    widget.setAlternatingRowColors(True)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for i, values in enumerate(rows):
        for j, value in enumerate(values):
            item = QTableWidgetItem(value)
            if value in ("TX", "RX"):
                item.setForeground(QColor(BLUE if value == "TX" else "#15996e"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            widget.setItem(i, j, item)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_column < 0:
        stretch_column = len(headers) - 1
    widget.horizontalHeader().setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
    return widget


class SpectrumPlot(QWidget):
    """A deterministic illustrative trace; never represents received data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 190)
        self.show_peak_hold = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(42, 22, self.width() - 55, self.height() - 60)
        painter.fillRect(plot, QColor("#fafcff"))
        font = QFont(self.font())
        font.setPointSizeF(8)
        painter.setFont(font)
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            painter.setPen(QPen(QColor("#e5ecf5"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(MUTED))
            painter.drawText(QRectF(0, y - 9, 34, 18), Qt.AlignmentFlag.AlignRight, str(-20 - 20 * i))
        for i in range(5):
            x = plot.left() + plot.width() * i / 4
            painter.setPen(QPen(QColor("#eaf0f7"), 1))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(MUTED))
            painter.drawText(QRectF(x - 24, plot.bottom() + 9, 48, 18), Qt.AlignmentFlag.AlignCenter, f"{990 + i * 5}")
        painter.setPen(QColor(MUTED))
        painter.drawText(2, 12, "dBm")
        painter.drawText(QRectF(plot.left(), self.height() - 17, plot.width(), 16), Qt.AlignmentFlag.AlignCenter, "Frequency (MHz)")

        trace = QPainterPath()
        hold = QPainterPath()
        for i in range(601):
            t = i / 600
            noise = 2.1 * math.sin(i * 1.7) + 1.7 * math.cos(i * 2.9) + 1.6 * math.sin(i * .37)
            signal = 59 * math.exp(-((t - .5) / .026) ** 2)
            shoulder = 11 * math.exp(-((t - .5) / .095) ** 2)
            secondary = 17 * math.exp(-((t - .77) / .025) ** 2)
            dbm = min(-22, -94 + noise + signal + shoulder + secondary)
            x = plot.left() + t * plot.width()
            y = plot.top() + (-20 - dbm) / 80 * plot.height()
            hy = plot.top() + (-20 - (dbm + 5 + math.sin(i * .18))) / 80 * plot.height()
            if i == 0:
                trace.moveTo(x, y)
                hold.moveTo(x, hy)
            else:
                trace.lineTo(x, y)
                hold.lineTo(x, hy)

        painter.save()
        painter.setClipRect(plot)
        fill = QPainterPath(trace)
        fill.lineTo(plot.right(), plot.bottom())
        fill.lineTo(plot.left(), plot.bottom())
        fill.closeSubpath()
        gradient = QLinearGradient(plot.topLeft(), plot.bottomLeft())
        gradient.setColorAt(0, QColor(50, 100, 232, 65))
        gradient.setColorAt(1, QColor(50, 100, 232, 5))
        painter.fillPath(fill, gradient)
        if self.show_peak_hold:
            painter.setPen(QPen(QColor("#a9bae3"), 1, Qt.PenStyle.DashLine))
            painter.drawPath(hold)
        painter.setPen(QPen(QColor(BLUE), 1.5))
        painter.drawPath(trace)
        painter.restore()

        x = plot.center().x()
        painter.setPen(QPen(QColor("#94a9db"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BLUE))
        painter.drawEllipse(QPointF(x, plot.top() + 12), 3.5, 3.5)
        painter.setPen(QColor(BLUE))
        painter.drawText(QRectF(x + 9, plot.top() + 3, 125, 20), "M1  1,000.0 MHz")
        painter.end()
