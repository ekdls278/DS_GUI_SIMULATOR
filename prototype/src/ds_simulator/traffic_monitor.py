"""Live timeline, rate bars and frozen display controls; all traffic is mock data."""
from datetime import datetime
import json
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QPlainTextEdit, QScrollArea, QSlider, QToolTip, QWidget

from .traffic import display_groups, lane_key
from .widgets import Card, button, chip, label, row

TX, RX = '#3264e8', '#15996e'


def public_record(record):
    return {key: value for key, value in record.items() if not key.startswith('_')}


class TimelineCanvas(QWidget):
    events_clicked = Signal(object)
    LEFT, TOP, LANE = 220, 38, 76

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(620)
        self.setMouseTracking(True)
        self.hits = []
        self.records = ()
        self.groups = []
        self.lanes = []
        self.start, self.end = 0, 1
        self.selected_ids = set()
        self.setMinimumHeight(170)

    def set_data(self, snapshot, start, end, connection_id):
        self.records = snapshot.records
        self.start, self.end = start, end
        self.connection_id = connection_id
        records = [r for r in self.records if start <= r['_timestamp'] <= end and (connection_id is None or r['connection_id'] == connection_id)]
        self.lane_latest = {lane_key(record): record for record in records}
        self.lanes = sorted(self.lane_latest)
        self.setMinimumHeight(max(170, self.TOP + len(self.lanes) * self.LANE + 14))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#f8faff'))
        painter.setFont(QFont(self.font().family(), 8))
        plot_width = max(100, self.width() - self.LEFT - 16)
        slots = max(1, int(plot_width / 148))
        slot_width = plot_width / slots
        self.groups = display_groups(self.records, self.start, self.end, slots, self.connection_id) if self.lanes else []
        for index in range(5):
            x = self.LEFT + plot_width * index / 4
            painter.setPen(QPen(QColor('#e1e8f3'), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, self.TOP), QPointF(x, self.height()))
            stamp = self.start + (self.end - self.start) * index / 4
            painter.setPen(QColor('#7b8799'))
            label_x = min(x - 43, self.width() - 90)
            painter.drawText(QRectF(label_x, 6, 86, 24), Qt.AlignmentFlag.AlignCenter, datetime.fromtimestamp(stamp).strftime('%H:%M:%S'))
        self.hits = []
        if not self.lanes:
            painter.setPen(QColor('#8190a5'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '선택한 시간에 기록이 없습니다. 송신하거나 모의 수신을 생성하세요.')
            return
        for index, lane in enumerate(self.lanes):
            y = self.TOP + index * self.LANE
            painter.fillRect(QRectF(0, y, self.LEFT - 8, self.LANE - 2), QColor('#edf2f8'))
            latest = self.lane_latest[lane]
            title = lane[0] + (f' / {lane[1]}' if lane[1] else '')
            painter.setPen(QColor('#263d5d'))
            painter.drawText(QRectF(12, y + 7, self.LEFT - 26, 24), Qt.AlignmentFlag.AlignVCenter, title)
            painter.setPen(QColor('#7b8799'))
            painter.drawText(QRectF(12, y + 33, self.LEFT - 26, 26), Qt.AlignmentFlag.AlignVCenter, latest['peer'])
            painter.setPen(QPen(QColor('#e1e8f3'), 1))
            painter.drawLine(QPointF(self.LEFT, y + self.LANE - 1), QPointF(self.width(), y + self.LANE - 1))
        lane_indices = {lane: index for index, lane in enumerate(self.lanes)}
        for (lane, direction, slot), records in self.groups:
            y = self.TOP + lane_indices[lane] * self.LANE + (8 if direction == 'TX' else 41)
            rect = QRectF(self.LEFT + slot * slot_width + 3, y, slot_width - 7, 27)
            color = TX if direction == 'TX' else RX
            selected = any(r['event_id'] in self.selected_ids for r in records)
            painter.setBrush(QColor('#e8efff' if direction == 'TX' else '#e6f6ee'))
            painter.setPen(QPen(QColor(color), 2 if selected else 1))
            painter.drawRoundedRect(rect, 5, 5)
            names = {record['message'] for record in records}
            group_name = '스펙트럼' if names == {'SPECTRUM_DATA'} else (records[0]['message'] if len(names) == 1 else '여러 메시지')
            text = f'{direction} {records[0]["message"]}' if len(records) == 1 else f'{direction} {len(records):,}건 · {group_name}'
            text = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width() - 12))
            painter.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, text)
            self.hits.append((rect, records))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for rect, records in self.hits:
                if rect.contains(event.position()):
                    self.selected_ids = {r['event_id'] for r in records}
                    self.events_clicked.emit(records)
                    self.update()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        for rect, records in self.hits:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), f'{records[0]["direction"]} · {len(records)}건\n{records[0]["time"]}\n{records[-1]["time"]}\n클릭하면 필드값을 확인합니다.', self)
                return
        QToolTip.hideText()


class RatePlot(QWidget):
    def __init__(self):
        super().__init__()
        self.series = []
        self.setFixedHeight(67)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#f8faff'))
        peak = max((tx + rx for _, tx, rx in self.series), default=0)
        scale = max(peak, 1)
        width = max(1, (self.width() - 156) / max(1, len(self.series)))
        painter.setPen(QColor('#7b8799'))
        painter.drawText(QRectF(8, 5, 135, 24), '최근 20초 · 초당 건수')
        painter.drawText(QRectF(8, 30, 135, 24), f'최대 {peak:,}건/초')
        for index, (_, tx, rx) in enumerate(self.series):
            x = 150 + index * width
            tx_height, rx_height = tx / scale * 48, rx / scale * 48
            painter.fillRect(QRectF(x, 57 - tx_height, max(1, width - 3), tx_height), QColor(TX))
            painter.fillRect(QRectF(x, 57 - tx_height - rx_height, max(1, width - 3), rx_height), QColor(RX))


class TrafficMonitor(Card):
    def __init__(self, history, connections, open_logs, receive, parent=None):
        super().__init__(parent=parent)
        self.history = history
        self.paused_snapshot = None
        self.manual_anchor = time.time()
        heading = row(label('실시간 통신 모니터', 'heading'), chip('MOCK · 최근 2,000건'))
        heading.addStretch()
        self.connection_filter = QComboBox()
        heading.addWidget(self.connection_filter)
        self.span = QComboBox()
        for seconds in (5, 10, 30, 60):
            self.span.addItem(f'{seconds}초 보기', seconds)
        self.span.setCurrentIndex(1)
        heading.addWidget(self.span)
        self.pause_button = button('화면 일시정지')
        self.pause_button.setCheckable(True)
        heading.addWidget(self.pause_button)
        logs = button('전체 로그 보기', icon_name='arrow')
        logs.clicked.connect(open_logs)
        heading.addWidget(logs)
        self.body.addLayout(heading)
        self.stats = label('', 'muted')
        self.stats.setWordWrap(True)
        self.body.addWidget(self.stats)
        controls = row(label('■ TX 송신', color=TX), label('■ RX 수신', color=RX))
        controls.addStretch()
        mock = button('모의 수신 생성')
        mock.clicked.connect(receive)
        controls.addWidget(mock)
        self.follow = QCheckBox('실시간 따라가기')
        self.follow.setChecked(True)
        controls.addWidget(self.follow)
        self.offset = QSlider(Qt.Orientation.Horizontal)
        self.offset.setRange(0, 120)
        self.offset.setEnabled(False)
        self.offset.setMaximumWidth(190)
        self.offset.setToolTip('실시간 따라가기를 해제하고 최대 120초 전으로 이동합니다.')
        controls.addWidget(self.offset)
        self.body.addLayout(controls)
        self.canvas = TimelineCanvas()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.canvas)
        scroll.setMinimumHeight(180)
        scroll.setMaximumHeight(430)
        self.body.addWidget(scroll, 1)
        self.rate_plot = RatePlot()
        self.body.addWidget(self.rate_plot)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(100)
        self.detail.hide()
        self.detail.setPlaceholderText('메시지 구간을 클릭하면 상세값을 표시합니다. 응답 관계는 추정하지 않습니다.')
        self.body.addWidget(self.detail)
        self.notice = label('가까운 메시지는 구간으로 묶고, 스펙트럼 메시지는 1초 단위로 집계합니다.', 'caption')
        self.notice.setWordWrap(True)
        self.body.addWidget(self.notice)
        self.canvas.events_clicked.connect(self.show_events)
        self.connection_filter.currentIndexChanged.connect(self.render_now)
        self.span.currentIndexChanged.connect(self.render_now)
        self.offset.valueChanged.connect(self.render_now)
        self.follow.toggled.connect(self.change_follow)
        self.pause_button.toggled.connect(self.change_pause)
        self.set_connections(connections)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.render_now()

    def set_connections(self, connections):
        selected = self.connection_filter.currentData()
        self.connection_filter.blockSignals(True)
        self.connection_filter.clear()
        self.connection_filter.addItem('전체 연결', None)
        for connection in connections:
            self.connection_filter.addItem(connection.title, connection.identifier)
        self.connection_filter.setCurrentIndex(max(0, self.connection_filter.findData(selected)))
        self.connection_filter.blockSignals(False)

    def change_follow(self, checked):
        self.manual_anchor = self.paused_snapshot.captured_at if self.paused_snapshot else time.time()
        self.offset.setEnabled(not checked)
        if checked:
            self.offset.setValue(0)
        self.render_now()

    def change_pause(self, paused):
        self.paused_snapshot = self.history.snapshot() if paused else None
        self.pause_button.setText('표시 재개' if paused else '화면 일시정지')
        self.render_now()

    def tick(self):
        if self.isVisible():
            self.render_now()

    def render_now(self, *args):
        snapshot = self.paused_snapshot or self.history.snapshot()
        connection_id = self.connection_filter.currentData()
        end = snapshot.captured_at if self.follow.isChecked() else self.manual_anchor - self.offset.value()
        self.canvas.set_data(snapshot, end - self.span.currentData(), end, connection_id)
        stats = snapshot.stats(connection_id)
        age = '없음' if stats['last_rx'] is None else f'{max(0, snapshot.captured_at - stats["last_rx"]):.1f}초 전'
        self.stats.setText(f'누적 TX {stats["TX"]:,}건  ·  누적 RX {stats["RX"]:,}건  ·  최근 수신 {age}  ·  버퍼 {len(snapshot.records):,}/2,000건')
        self.rate_plot.series = snapshot.rate_series(end, connection_id=connection_id)
        self.rate_plot.update()
        if self.paused_snapshot:
            self.notice.setText(f'화면 일시정지 · 수집 계속 · 일시정지 후 {self.history.received - snapshot.received:,}건 추가 수집. 필터·시간 조절은 고정된 화면에 적용됩니다.')
        else:
            self.notice.setText('스펙트럼은 1초 단위, 겹치는 메시지는 시간 구간으로 묶습니다. 가까운 RX를 응답으로 자동 판단하지 않습니다.')

    def show_events(self, records):
        self.detail.show()
        self.detail.setPlainText(json.dumps({'count': len(records), 'shown': min(100, len(records)), 'events': [public_record(r) for r in records[-100:]]}, ensure_ascii=False, indent=2))
