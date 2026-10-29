"""Connection configuration persistence; live socket state is never restored."""

from dataclasses import asdict
import ipaddress
import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from .domain import save_json
from .preview_data import ConnectionPreview


def read_profiles(path):
    path = Path(path)
    if path.stat().st_size > 1_000_000:
        raise ValueError("연결 설정 파일은 1MB 이하여야 합니다.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or data.get("format") != "ds-connections" or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("지원하는 연결 설정 파일이 아닙니다.")
        rows = data["connections"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError("연결 설정은 1~100개여야 합니다.")
        result = []
        seen = set()
        for entry in rows:
            connection = ConnectionPreview(**entry)
            for text in (connection.identifier, connection.name, connection.mode, connection.local_endpoint, connection.remote_endpoint):
                if not isinstance(text, str) or len(text) > 200:
                    raise ValueError("연결 설정 문자열이 올바르지 않습니다.")
            if not connection.identifier.strip() or connection.identifier in seen or not connection.name.strip():
                raise ValueError("연결 ID는 고유해야 하며 이름이 필요합니다.")
            if connection.mode not in ("TCP Client", "TCP Server", "UDP"):
                raise ValueError("지원하지 않는 연결 모드입니다.")
            endpoints = [connection.local_endpoint]
            if connection.mode != "TCP Server":
                endpoints.append(connection.remote_endpoint)
            elif connection.remote_endpoint:
                raise ValueError("TCP 서버의 Remote는 접속 후 결정됩니다.")
            for index, endpoint in enumerate(endpoints):
                host, port = endpoint.rsplit(":", 1)
                if ipaddress.ip_address(host).version != 4:
                    raise ValueError("프로토타입은 IPv4 주소를 사용합니다.")
                if not port.isdecimal() or not (0 if index == 0 else 1) <= int(port) <= 65535:
                    raise ValueError("포트 범위를 확인하세요.")
            seen.add(connection.identifier)
            result.append(connection)
        return result
    except (KeyError, TypeError, AttributeError, UnicodeError, RecursionError):
        raise ValueError("연결 설정 JSON 구조가 올바르지 않습니다.") from None


class ProfileMixin:
    def save_profiles_to(self, path):
        save_json(path, {"format": "ds-connections", "version": 1, "connections": [asdict(c) for c in self.connections]})

    def load_profiles_from(self, path):
        # Parse fully before touching current state.
        connections = read_profiles(path)
        if self.scenario_editor.runner.running:
            raise ValueError("시험을 중지한 뒤 연결 설정을 불러오세요.")
        self.clear_message_selection()
        self.connections = connections
        self.sockets = []
        self.selected_peers.clear()
        self.selected_connection_index = 0
        self.clear_connection_cards()
        self.log_connection_filter.blockSignals(True)
        self.socket_connection_filter.blockSignals(True)
        self.log_connection_filter.clear()
        self.log_connection_filter.addItem("전체 연결", None)
        self.socket_connection_filter.clear()
        self.socket_connection_filter.addItem("전체 연결", None)
        for index, connection in enumerate(connections):
            self.append_connection_button(index, connection)
            self.log_connection_filter.addItem(connection.title, connection.identifier)
            self.socket_connection_filter.addItem(connection.title, connection.identifier)
        self.log_connection_filter.blockSignals(False)
        self.socket_connection_filter.blockSignals(False)
        self.connection_summary.setText(f"프로파일 {len(connections):02}개 · 모두 미연결")
        self.sidebar_connections.setText(f"      연결 프로파일       {len(connections):02}")
        self.refresh_socket_monitor()
        self.select_connection(0)
        self.filter_log()
        self.scenario_editor.show_properties()
        self.traffic_monitor.set_connections(self.connections)

    def save_profiles_dialog(self):
        filename, _ = QFileDialog.getSaveFileName(self, "연결 설정 저장", "connections.json", "연결 설정 JSON (*.json)")
        if filename:
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".json")
            try:
                self.save_profiles_to(path)
                self.statusBar().showMessage(f"연결 설정 저장 완료: {path}", 5000)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "저장 실패", str(exc))

    def load_profiles_dialog(self):
        if self.scenario_editor.runner.running:
            QMessageBox.information(self, "시험 실행 중", "시험을 중지한 뒤 연결 설정을 불러오세요.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "연결 설정 불러오기", "", "연결 설정 JSON (*.json)")
        if not filename:
            return
        if self.sockets and QMessageBox.question(self, "연결 설정 변경", "현재 모의 연결을 해제하고 연결 설정을 바꿀까요?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.load_profiles_from(filename)
            self.statusBar().showMessage("연결 설정 불러오기 완료 · 연결 상태는 복원하지 않습니다. 모의 연결을 다시 진행하세요.", 6000)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "불러오기 실패", str(exc))
