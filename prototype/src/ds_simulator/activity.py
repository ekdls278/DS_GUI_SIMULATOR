"""Bounded mock activity log shared by manual and scenario sends."""

import csv
import io
import json

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QFileDialog, QLineEdit, QMessageBox, QPlainTextEdit, QTableWidgetItem

from .domain import Step, save_json
from .widgets import Card, button, chip, label, row, table


class ActivityMixin:
    def make_log(self):
        self.log_events = []
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
        receive.clicked.connect(self.mock_receive)
        header.addWidget(receive)
        export = button("내보내기", icon_name="download")
        export.clicked.connect(self.export_log)
        header.addWidget(export)
        card.body.addLayout(header)
        self.log_table = table(["시간", "방향", "연결 ID", "상대 IP : Port", "SRC", "DST", "CMD", "메시지 / 출처"], [])
        self.log_table.setMinimumHeight(140)
        self.log_table.itemSelectionChanged.connect(self.show_log_detail)
        card.body.addWidget(self.log_table, 1)
        self.log_detail = QPlainTextEdit()
        self.log_detail.setReadOnly(True)
        self.log_detail.setMaximumHeight(82)
        self.log_detail.setPlaceholderText("로그 행을 선택하면 모의 데이터와 입력값을 확인할 수 있습니다. 최대 2,000건을 유지합니다.")
        card.body.addWidget(self.log_detail)
        self.transport.sent.connect(self.record_event)
        return card

    @staticmethod
    def log_row(event):
        headers = event["headers"]
        return [event["time"], event["direction"], event["connection_id"], event["peer"], headers["src"], headers["dst"], headers["cmd"], f"{event['message']} · {event['source']} · MOCK"]

    def record_event(self, event):
        self.log_events.insert(0, event)
        if len(self.log_events) > 2000:
            self.log_events.pop()
        self.log_table.blockSignals(True)
        self.log_table.insertRow(0)
        for column, value in enumerate(self.log_row(event)):
            self.log_table.setItem(0, column, QTableWidgetItem(value))
        self.log_table.item(0, 1).setForeground(QColor("#3264e8" if event["direction"] == "TX" else "#15996e"))
        if self.log_table.rowCount() > 2000:
            self.log_table.removeRow(2000)
        self.log_table.clearSelection()
        self.log_table.blockSignals(False)
        self.log_detail.clear()
        self.log_count.setText(f"MOCK · {len(self.log_events):,}건")
        self.filter_log()

    def filter_log(self, *args):
        direction = self.log_direction.currentData()
        connection_id = self.log_connection_filter.currentData()
        term = self.log_search.text().casefold()
        for index, event in enumerate(self.log_events):
            hidden = (direction is not None and direction != event["direction"]) or (connection_id is not None and connection_id != event["connection_id"]) or term not in json.dumps(event, ensure_ascii=False).casefold()
            self.log_table.setRowHidden(index, hidden)
        self.show_log_detail()

    def show_log_detail(self):
        index = self.log_table.currentRow()
        selected = self.log_table.selectionModel().hasSelection()
        if selected and 0 <= index < len(self.log_events) and not self.log_table.isRowHidden(index):
            self.log_detail.setPlainText(json.dumps(self.log_events[index], ensure_ascii=False, indent=2))
        else:
            self.log_detail.clear()

    def mock_receive(self):
        connection = self.selected_connection()
        socket = self.current_socket()
        if socket is None:
            self.statusBar().showMessage("모의 수신을 생성할 연결과 접속 대상을 먼저 선택하세요.", 5000)
            return
        step = Step.send("STATUS_RESPONSE")
        step.connection_id, step.socket_id = connection.identifier, socket.identifier
        # Explicit button only: never invent an automatic hardware acknowledgement.
        from datetime import datetime
        from .domain import validate_message
        _, peer = self.transport.resolve(step.connection_id, step.socket_id)
        self.record_event({"time": datetime.now().astimezone().isoformat(timespec="milliseconds"), "mode": "MOCK", "direction": "RX", "source": "수신 예시 버튼", "connection_id": connection.identifier, "socket_id": socket.identifier, "peer": peer, "message": step.message, "headers": step.headers, "values": validate_message(step.message, step.headers, step.values), "big_endian": False})

    def visible_events(self):
        return [event for index, event in enumerate(self.log_events) if not self.log_table.isRowHidden(index)]

    def export_log(self):
        filename, selected = QFileDialog.getSaveFileName(self, "현재 필터의 모의 로그 저장", "mock-log.json", "JSON (*.json);;CSV (*.csv)")
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
                save_json(path, {"format": "ds-mock-log", "version": 1, "events": events})
            self.statusBar().showMessage(f"모의 로그 {len(events)}건 저장: {path}", 6000)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "로그 저장 실패", str(exc))
