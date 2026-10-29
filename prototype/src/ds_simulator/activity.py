"""Bounded mock activity log shared by manual and scenario sends."""

import csv
import io
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QFileDialog, QLineEdit, QMessageBox, QPlainTextEdit, QTableWidgetItem

from .domain import Step, save_json
from .icd import IcdMessage
from .traffic import TrafficHistory
from .traffic_monitor import TrafficMonitor, public_record
from .widgets import Card, button, chip, label, row, table


class ActivityMixin:
    def initialize_activity(self):
        self.log_events = []
        self.traffic_history = TrafficHistory()
        self.log_dirty = False
        self.last_log_rendered = 0
        self.transport.sent.connect(self.record_event)
        self.transport.received.connect(self.record_event)

    def make_traffic_monitor(self):
        self.traffic_monitor = TrafficMonitor(self.traffic_history, self.connections, lambda: self.show_page(5), self.mock_receive)
        return self.traffic_monitor

    def make_log_page(self):
        page, layout = self.page("송수신 로그", "최근 2,000건을 검색·필터링하고, 상세값을 확인하거나 파일로 저장합니다.")
        layout.addWidget(self.make_log(), 1)
        return page

    def make_log(self):
        card = Card()
        self.log_count = chip("MOCK · 0건", "neutralChip")
        header = row(label("송수신 로그", "heading"), self.log_count)
        header.addStretch()
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("메시지·값 검색")
        self.log_search.setMaximumWidth(150)
        self.log_search.textChanged.connect(self.filter_log)
        header.addWidget(self.log_search)
        self.log_connection_filter = QComboBox()
        self.log_connection_filter.addItem("전체 연결", None)
        for connection in self.connections:
            self.log_connection_filter.addItem(connection.title, connection.identifier)
        self.log_connection_filter.currentIndexChanged.connect(self.filter_log)
        header.addWidget(self.log_connection_filter)
        self.log_direction = QComboBox()
        for title, value in (("전체 방향", None), ("TX 송신", "TX"), ("RX 수신", "RX")):
            self.log_direction.addItem(title, value)
        self.log_direction.currentIndexChanged.connect(self.filter_log)
        header.addWidget(self.log_direction)
        receive = button("모의 수신 생성")
        self.log_receive_button = receive
        receive.clicked.connect(self.mock_receive)
        header.addWidget(receive)
        export = button("내보내기", icon_name="download")
        export.clicked.connect(self.export_log)
        header.addWidget(export)
        card.body.addLayout(header)
        self.log_table = table(["시간", "방향", "연결 ID", "상대 IP : Port", "SRC", "DST", "CMD", "메시지 / 출처"], [])
        self.log_table.setMinimumHeight(420)
        self.log_table.itemSelectionChanged.connect(self.show_log_detail)
        card.body.addWidget(self.log_table, 1)
        self.log_detail = QPlainTextEdit()
        self.log_detail.setReadOnly(True)
        self.log_detail.setMinimumHeight(170)
        self.log_detail.setMaximumHeight(280)
        self.log_detail.setPlaceholderText("로그 행을 선택하면 HEX·UTF-8 원문과 입력값을 확인할 수 있습니다. 최대 2,000건을 유지합니다.")
        card.body.addWidget(self.log_detail)
        self.log_refresh_timer = QTimer(self)
        self.log_refresh_timer.setInterval(100)
        self.log_refresh_timer.timeout.connect(lambda: self.flush_log_view() if self.log_table.isVisible() else None)
        self.log_refresh_timer.start()
        return card

    @staticmethod
    def log_row(event):
        headers = event["headers"]
        return [event["time"], event["direction"], event["connection_id"], event["peer"], headers["src"], headers["dst"], headers["cmd"], f"{event['message']} · {event['source']} · {event['mode']}"]

    def record_event(self, event):
        enriched = dict(event)
        connection = next((c for c in self.connections if c.identifier == event['connection_id']), None)
        enriched['connection_mode'] = connection.mode if connection else event.get('connection_mode', 'unknown')
        record = self.traffic_history.append(enriched)
        self.log_events.insert(0, record)
        if len(self.log_events) > 2000:
            self.log_events.pop()
        self.log_dirty = True

    def flush_log_view(self):
        if not self.log_dirty:
            return
        selected = None
        if self.log_table.selectionModel().hasSelection():
            item = self.log_table.item(self.log_table.currentRow(), 0)
            selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.log_table.blockSignals(True)
        self.log_table.setUpdatesEnabled(False)
        try:
            fresh = [r for r in self.log_events if r['event_id'] > self.last_log_rendered]
            for event in reversed(fresh):
                self.log_table.insertRow(0)
                for column, value in enumerate(self.log_row(event)):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, event['event_id'])
                    self.log_table.setItem(0, column, item)
                self.log_table.item(0, 1).setForeground(QColor('#3264e8' if event['direction'] == 'TX' else '#15996e'))
            self.log_table.setRowCount(len(self.log_events))
            self.log_table.clearSelection()
            self.log_table.setCurrentCell(-1, -1)
            if selected is not None:
                index = next((i for i, r in enumerate(self.log_events) if r['event_id'] == selected), None)
                if index is not None:
                    self.log_table.selectRow(index)
            self.last_log_rendered = self.traffic_history.received
            self.log_dirty = False
        finally:
            self.log_table.setUpdatesEnabled(True)
            self.log_table.blockSignals(False)
        self.log_count.setText(f'최근 {len(self.log_events):,}건')
        self._apply_log_filter()

    def filter_log(self, *args):
        self.flush_log_view()
        self._apply_log_filter()

    def _apply_log_filter(self):
        direction = self.log_direction.currentData()
        connection_id = self.log_connection_filter.currentData()
        term = self.log_search.text().casefold()
        visible = 0
        for index, event in enumerate(self.log_events):
            hidden = (direction is not None and direction != event["direction"]) or (connection_id is not None and connection_id != event["connection_id"]) or term not in json.dumps(event, ensure_ascii=False).casefold()
            self.log_table.setRowHidden(index, hidden)
            visible += not hidden
        self.log_count.setText(f'표시 {visible:,} / 보관 {len(self.log_events):,}건')
        self.show_log_detail()

    def show_log_detail(self):
        index = self.log_table.currentRow()
        selected = self.log_table.selectionModel().hasSelection()
        item = self.log_table.item(index, 0) if index >= 0 else None
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        record = next((r for r in self.log_events if r['event_id'] == identifier), None)
        if selected and record is not None and not self.log_table.isRowHidden(index):
            detail = public_record(record)
            if record['mode'] == 'LIVE':
                detail = {'values': detail.pop('values'), **detail}
            self.log_detail.setPlainText(json.dumps(detail, ensure_ascii=False, indent=2))
        else:
            self.log_detail.clear()

    def mock_receive(self):
        if self.transport.live:
            self.statusBar().showMessage('실제 통신에서는 소켓에서 받은 데이터만 수신 로그에 기록합니다.', 5000)
            return
        connection = self.selected_connection()
        socket = self.current_socket()
        if socket is None:
            self.statusBar().showMessage("모의 수신을 생성할 연결과 접속 대상을 먼저 선택하세요.", 5000)
            return
        name = "STATUS_RESPONSE" if "STATUS_RESPONSE" in self.messages else self.selected_message_name
        if name is None:
            self.statusBar().showMessage("모의 수신에 사용할 ICD 메시지를 먼저 선택하세요.", 5000)
            return
        step = Step.send(name, self.messages)
        step.connection_id, step.socket_id = connection.identifier, socket.identifier
        # Explicit button only: never invent an automatic hardware acknowledgement.
        from datetime import datetime
        from .domain import validate_message
        _, peer = self.transport.resolve(step.connection_id, step.socket_id)
        message = self.messages[name]
        values = validate_message(step.message, step.headers, step.values, self.messages)
        event = {"time": datetime.now().astimezone().isoformat(timespec="milliseconds"), "mode": "MOCK", "direction": "RX", "source": "수신 예시 버튼", "connection_id": connection.identifier, "socket_id": socket.identifier, "peer": peer, "message": message.description if isinstance(message, IcdMessage) else name, "message_id": name, "headers": step.headers, "values": values, "big_endian": False}
        if isinstance(message, IcdMessage):
            event['data_elements'] = [{'sequence': field.sequence, 'name': field.name, 'value': values[field.key]} for field in message.elements]
        self.record_event(event)


    def visible_events(self):
        self.flush_log_view()
        return [public_record(event) for index, event in enumerate(self.log_events) if not self.log_table.isRowHidden(index)]

    def export_log(self):
        filename, selected = QFileDialog.getSaveFileName(self, "현재 필터의 송수신 로그 저장", "communication-log.json", "JSON (*.json);;CSV (*.csv)")
        if not filename:
            return
        from pathlib import Path
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".csv" if "CSV" in selected else ".json")
        try:
            events = self.visible_events()
            if path.suffix.lower() == ".csv":
                content = io.StringIO(newline="")
                writer = csv.writer(content)
                writer.writerow(["time", "direction", "connection_id", "peer", "src", "dst", "cmd", "message/source/mode", "socket_id", "values", "big_endian"])
                for event in events:
                    values = self.log_row(event) + [event["socket_id"], json.dumps(event["values"], ensure_ascii=False), str(event["big_endian"])]
                    writer.writerow(["'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])
                with path.open("w", encoding="utf-8-sig", newline="") as stream:
                    stream.write(content.getvalue())
            else:
                save_json(path, {"format": "ds-communication-log" if any(e['mode'] == 'LIVE' for e in events) else 'ds-mock-log', "version": 1, "events": events})
            self.statusBar().showMessage(f"송수신 로그 {len(events)}건 저장: {path}", 6000)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "로그 저장 실패", str(exc))
