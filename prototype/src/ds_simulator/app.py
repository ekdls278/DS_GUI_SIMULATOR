"""TCP/UDP test workspace with explicit real and mock modes."""

import argparse
import ipaddress
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QScrollArea, QSpinBox, QStackedWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QMessageBox,
)

from .theme import BLUE, STYLESHEET
from .widgets import Card, SpectrumPlot, button, chip, icon, label, row, table
from .workspace import WorkspaceMixin
from .scenario_editor import ScenarioEditor
from .runtime import TransportRouter
from .activity import ActivityMixin
from .profiles import ProfileMixin
from .icd_ui import IcdMixin
from .icd import read_icd_sheet


from .preview_data import CONNECTIONS, MESSAGES, SOCKETS, ConnectionPreview

PAGE_NAMES = ("workspace", "sockets", "icd", "spectrum", "scenario", "logs")


def combo(values: list[str]) -> QComboBox:
    widget = QComboBox()
    widget.addItems(values)
    return widget


def divider() -> QFrame:
    widget = QFrame()
    widget.setFixedHeight(1)
    widget.setStyleSheet("background: #e8edf4; border: 0;")
    return widget


class SimulatorWindow(WorkspaceMixin, ActivityMixin, ProfileMixin, IcdMixin, QMainWindow):
    def __init__(self, mock=False):
        super().__init__()
        self.setWindowTitle("DS Simulator — TCP/UDP 통신 시험")
        self.resize(1680, 1040)
        self.setMinimumSize(1180, 760)
        self.setWindowIcon(icon("logo", BLUE, 32))
        self.connections = list(CONNECTIONS)
        self.sockets = [s for s in SOCKETS if s.connection_id != "TCP-01"] if mock else []
        self.connection_errors = {}
        self.next_socket_number = 7
        self.selected_connection_index = 0
        self.selected_message_name = None
        self.connection_buttons = {}
        self.selected_peers = {}
        self.messages = dict(MESSAGES)
        self.catalog_source = "기본 예시 ICD"
        self.transport = TransportRouter(lambda: self.connections, lambda: self.sockets, self, catalog=lambda: self.messages, live=not mock)
        self.transport.network.changed.connect(self.network_changed)
        self.transport.network.error.connect(self.network_error)
        self.initialize_activity()
        self.spectrum_window = None
        self.active_page = 0
        self.page_indices = {}
        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.make_header())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.stack = QStackedWidget()
        body.addWidget(self.make_sidebar())
        for navigation_id, page in ((0, self.make_workspace()), (1, self.make_sockets_page()), (2, self.make_icd_page()), (4, self.make_scenario_page()), (5, self.make_log_page())):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.page_indices[navigation_id] = self.stack.addWidget(scroll)
        body.addWidget(self.stack, 1)
        layout.addLayout(body, 1)
        self.setCentralWidget(root)
        self.select_connection(0)
        self.statusBar().setSizeGripEnabled(False)
        self.mode_status = label('', 'caption')
        self.statusBar().addWidget(self.mode_status)
        self.refresh_mode_labels()
        self.statusBar().addPermanentWidget(label("DS Simulator   /   Prototype 0.2    ", "caption"))

    def make_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("header")
        frame.setFixedHeight(72)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 0, 28, 0)
        layout.setSpacing(13)
        logo = QLabel()
        logo.setPixmap(icon("logo", BLUE, 32).pixmap(32, 32))
        layout.addWidget(logo)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        brand.addWidget(label("DS SIMULATOR", "brand"))
        brand.addWidget(label("DEVICE SIMULATION WORKSPACE", "caption"))
        layout.addLayout(brand)
        layout.addSpacing(37)
        project = label("수신기 시험  /  개발 프로젝트")
        project.setStyleSheet("color: #63748c; border-left: 1px solid #e1e6ef; padding-left: 24px;")
        layout.addWidget(project)
        layout.addStretch()
        save_profiles = button("연결 설정 저장")
        save_profiles.clicked.connect(self.save_profiles_dialog)
        load_profiles = button("연결 설정 불러오기")
        load_profiles.clicked.connect(self.load_profiles_dialog)
        layout.addWidget(load_profiles)
        layout.addWidget(save_profiles)
        self.mode_select = QComboBox()
        self.mode_select.addItem('실제 통신 · LIVE', True)
        self.mode_select.addItem('모의 통신 · MOCK', False)
        self.mode_select.setCurrentIndex(0 if self.transport.live else 1)
        self.mode_select.setToolTip('통신 모드를 바꾸면 모든 연결을 해제합니다. 로그는 각 기록의 LIVE/MOCK 구분을 유지합니다.')
        self.mode_select.currentIndexChanged.connect(self.change_transport_mode)
        layout.addWidget(self.mode_select)
        layout.addSpacing(5)
        layout.addWidget(label("TCP / UDP", "muted"))
        return frame

    def make_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(190)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(13, 26, 13, 18)
        layout.setSpacing(7)
        layout.addWidget(label("   WORKSPACE", "sidebarCaption"))
        layout.addSpacing(9)
        self.nav_group = QButtonGroup(self)
        for index, (text, glyph) in enumerate((
            ("ICD 송수신", "grid"), ("소켓 상세", "link"), ("ICD 정의", "file"), ("스펙트럼", "wave"),
            ("시나리오", "folder"), ("송수신 로그", "file"),
        )):
            nav = button(text, icon_name=glyph)
            nav.setObjectName("nav")
            nav.setCheckable(index != 3)
            nav.setIconSize(QSize(18, 18))
            nav.setChecked(index == 0)
            self.nav_group.addButton(nav, index)
            layout.addWidget(nav)
        self.nav_group.idClicked.connect(self.show_page)
        layout.addSpacing(28)
        layout.addWidget(label("   PROJECT", "sidebarCaption"))
        layout.addSpacing(9)
        for text in ("   수신기 시험", "      연결 프로파일       04", "      ICD 메시지            05"):
            item = label(text)
            item.setStyleSheet("color: #9caec8; padding: 6px 2px; font-size: 12px;")
            layout.addWidget(item)
            if "연결 프로파일" in text:
                self.sidebar_connections = item
            if "ICD 메시지" in text:
                self.sidebar_messages = item
        layout.addStretch()
        note = QFrame()
        note.setObjectName("previewNote")
        notes = QVBoxLayout(note)
        notes.setContentsMargins(12, 14, 12, 14)
        notes.setSpacing(9)
        notes.addWidget(label("COMMUNICATION TEST", color="#b2c9ef"))
        description = label("실제 통신: HEX·UTF-8 송수신\nICD 인코딩 규격은 별도 정의")
        description.setStyleSheet("color: #91a8c8; font-size: 11px; line-height: 1.6;")
        notes.addWidget(description)
        layout.addWidget(note)
        return frame

    def page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("root")
        page.setMinimumWidth(1050)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        titles.addWidget(label(title, "title"))
        titles.addWidget(label(subtitle, "muted"))
        heading.addLayout(titles)
        heading.addStretch()
        heading.addWidget(chip("프로젝트  /  수신기 시험", "neutralChip"))
        layout.addLayout(heading)
        return page, layout

    def preview_notice(self, action: str):
        self.statusBar().showMessage(f"  {action} · 모의 동작이며 실제 네트워크 통신은 하지 않습니다.", 5500)

    def network_changed(self):
        if not self.transport.live:
            return
        self.sockets = self.transport.network.snapshots()
        self.refresh_socket_monitor()

    def network_error(self, cid, message):
        self.connection_errors[cid] = message
        self.statusBar().showMessage(f'{cid} · {message}', 15000)

    def refresh_mode_labels(self):
        live = self.transport.live
        self.mode_status.setText('   ● LIVE · 실제 TCP/UDP · ICD 자동 인코딩 미정 · 스펙트럼은 정적 예시' if live else '   ● MOCK · 실제 패킷을 전송하지 않습니다.')
        self.connection_mode_note.setText('실제 소켓을 연결합니다. 수신 데이터는 로그에 자동 기록됩니다.' if live else '연결·해제는 모의 동작입니다.')
        self.connection_detail_note.setText('연결 후 실제 Local / Remote 주소를 표시합니다.' if live else 'Local / Remote 값은 예시입니다.')
        self.connect_button.setToolTip('입력한 주소로 실제 소켓을 연결/해제합니다.' if live else '모의 연결 상태를 전환합니다.')
        self.log_receive_button.setVisible(not live)
        self.traffic_monitor.mock_button.setVisible(not live)
        self.traffic_monitor.mode_chip.setText(f'{self.transport.label} · 최근 2,000건')
        self.scenario_editor.refresh_mode()
        self.update_send_button()

    def change_transport_mode(self, index):
        live = bool(self.mode_select.itemData(index))
        if live == self.transport.live:
            return
        if self.scenario_editor.runner.running:
            self.mode_select.blockSignals(True)
            self.mode_select.setCurrentIndex(0 if self.transport.live else 1)
            self.mode_select.blockSignals(False)
            self.statusBar().showMessage('시험을 중지한 뒤 통신 모드를 변경하세요.', 5000)
            return
        # Both modes start disconnected after switching; never reuse mock socket IDs.
        self.transport.live = False
        self.transport.network.close_all()
        self.sockets = []
        self.selected_peers.clear()
        self.clear_message_selection()
        self.connection_errors.clear()
        self.transport.live = live
        self.send_format.setCurrentIndex(1 if live else 0)
        self.refresh_socket_monitor()
        self.refresh_mode_labels()

    def make_scenario_page(self):
        page, layout = self.page("시나리오 편집기", "송신·대기·반복 블록으로 시험을 구성합니다. 실제 통신은 직접 송신 블록을 사용하세요.")
        self.scenario_editor = ScenarioEditor(self)
        layout.addWidget(self.scenario_editor, 1)
        return page

    def closeEvent(self, event):
        self.scenario_editor.runner.stop()
        if self.scenario_editor.confirm_discard():
            if self.spectrum_window is not None:
                self.spectrum_window.close()
            self.traffic_monitor.timer.stop()
            self.log_refresh_timer.stop()
            self.transport.network.close_all()
            event.accept()
        else:
            event.ignore()

    def show_page(self, index: int):
        if index == 3:
            self.open_spectrum()
            return
        self.stack.setCurrentIndex(self.page_indices[index])
        self.active_page = index
        self.nav_group.button(index).setChecked(True)
        if index == 4:
            self.scenario_editor.show_properties()
        elif index == 5:
            self.flush_log_view()

    def open_spectrum(self):
        if self.spectrum_window is None:
            self.spectrum_window = QDialog(self, Qt.WindowType.Window)
            self.spectrum_window.setWindowTitle('스펙트럼 · 정적 예시')
            self.spectrum_window.setModal(False)
            self.spectrum_window.resize(1150, 850)
            self.spectrum_window.setMinimumSize(850, 620)
            layout = QVBoxLayout(self.spectrum_window)
            layout.setContentsMargins(0, 0, 0, 0)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            spectrum = self.make_spectrum_page()
            spectrum.setMinimumWidth(810)
            scroll.setWidget(spectrum)
            layout.addWidget(scroll)
        if self.spectrum_window.isMinimized():
            self.spectrum_window.showNormal()
        else:
            self.spectrum_window.show()
        self.spectrum_window.raise_()
        self.spectrum_window.activateWindow()

    def make_sockets_page(self) -> QWidget:
        page, layout = self.page("소켓 현황", "앱에서 관리하는 소켓의 상태와 Local / Remote 주소를 확인합니다.")
        summary = QHBoxLayout()
        self.socket_stat_values = {}
        for title, state, description in (
            ("연결된 TCP 소켓", "ESTABLISHED", "Client 및 서버 접속 소켓"),
            ("TCP 대기 소켓", "LISTENING", "서버의 접속 요청 대기"),
            ("UDP 소켓", "BOUND", "로컬 주소에 바인딩됨"),
        ):
            card = Card()
            card.body.setSpacing(4)
            card.body.addWidget(label(title, "muted"))
            value = label(f"{sum(s.state == state for s in self.sockets):02}", "stat")
            self.socket_stat_values[state] = value
            card.body.addWidget(value)
            card.body.addWidget(label(description, "caption"))
            summary.addWidget(card, 1)
        layout.addLayout(summary)

        catalog = Card("앱 소켓 목록")
        filters = QHBoxLayout()
        self.socket_count_label = label(f"소켓 {len(self.sockets)}개 · 서버 대기 소켓과 접속 소켓을 구분합니다.", "caption")
        filters.addWidget(self.socket_count_label)
        filters.addStretch()
        self.socket_connection_filter = QComboBox()
        self.socket_connection_filter.addItem("전체 연결", None)
        for connection in self.connections:
            self.socket_connection_filter.addItem(connection.title, connection.identifier)
        self.socket_state_filter = QComboBox()
        for title, value in (("전체 상태", None), ("연결됨 · TCP", "ESTABLISHED"), ("대기 중 · TCP", "LISTENING"), ("바인딩 · UDP", "BOUND")):
            self.socket_state_filter.addItem(title, value)
        filters.addWidget(self.socket_connection_filter)
        filters.addWidget(self.socket_state_filter)
        catalog.body.addLayout(filters)
        names = {c.identifier: c.title for c in self.connections}
        rows = [[s.identifier, names[s.connection_id], s.role, s.state, s.local_ip, str(s.local_port), s.remote_ip or "—", str(s.remote_port) if s.remote_port is not None else "—"] for s in self.sockets]
        self.socket_table = table(["소켓 ID", "연결", "역할", "상태", "Local IP (내 PC)", "Local Port", "Remote IP (상대)", "Remote Port"], rows, stretch_column=1)
        self.socket_table.setObjectName("socketTable")
        self.socket_table.setMinimumHeight(300)
        self.socket_table.verticalHeader().setDefaultSectionSize(42)
        for index, item in enumerate(self.sockets):
            self.socket_table.item(index, 3).setForeground(QColor("#15996e" if item.state == "ESTABLISHED" else BLUE))
        catalog.body.addWidget(self.socket_table, 1)
        self.socket_empty = label("선택한 조건에 해당하는 소켓이 없습니다. ICD 송수신 화면에서 연결할 수 있습니다.", "muted")
        self.socket_empty.hide()
        catalog.body.addWidget(self.socket_empty)
        layout.addWidget(catalog, 3)

        detail = Card()
        self.socket_detail_title = label("선택한 소켓", "heading")
        title = row(self.socket_detail_title)
        title.addStretch()
        self.socket_use_button = button("이 소켓을 송신 대상으로 선택", primary=True, icon_name="arrow")
        self.socket_use_button.clicked.connect(self.use_inspected_socket)
        title.addWidget(self.socket_use_button)
        detail.body.addLayout(title)
        endpoints = QHBoxLayout()
        endpoints.setSpacing(18)
        self.socket_detail_labels = {}
        for side, title_text in (("local", "Local · 내 PC"), ("remote", "Remote · 상대 장치")):
            panel = QFrame()
            panel.setObjectName("inset")
            form = QFormLayout(panel)
            form.setContentsMargins(16, 14, 16, 14)
            form.setVerticalSpacing(10)
            form.addRow(label(title_text, "heading"))
            for field in ("ip", "port"):
                value = label("—")
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                form.addRow(label("IP" if field == "ip" else "Port", "muted"), value)
                self.socket_detail_labels[f"{side}_{field}"] = value
            endpoints.addWidget(panel, 1)
        detail.body.addLayout(endpoints)
        self.socket_config_note = label("", "caption")
        self.socket_role_note = label("", "muted")
        self.socket_role_note.setWordWrap(True)
        detail.body.addWidget(self.socket_config_note)
        detail.body.addWidget(self.socket_role_note)
        layout.addWidget(detail, 2)
        self.socket_table.itemSelectionChanged.connect(self.update_socket_inspector)
        self.socket_connection_filter.currentIndexChanged.connect(self.filter_sockets)
        self.socket_state_filter.currentIndexChanged.connect(self.filter_sockets)
        self.socket_table.selectRow(0)
        return page

    def refresh_socket_monitor(self):
        # Preserve the inspected socket by ID as rows change on connect/disconnect.
        item = self.socket_table.item(self.socket_table.currentRow(), 0)
        selected_id = item.text() if item else None
        self.socket_table.blockSignals(True)
        self.socket_table.clearSelection()
        self.socket_table.setCurrentCell(-1, -1)
        self.socket_table.setRowCount(len(self.sockets))
        names = {c.identifier: c.title for c in self.connections}
        for index, socket in enumerate(self.sockets):
            values = [socket.identifier, names[socket.connection_id], socket.role, socket.state, socket.local_ip, str(socket.local_port), socket.remote_ip or "—", str(socket.remote_port) if socket.remote_port is not None else "—"]
            for column, value in enumerate(values):
                self.socket_table.setItem(index, column, QTableWidgetItem(value))
            self.socket_table.item(index, 3).setForeground(QColor("#15996e" if socket.state == "ESTABLISHED" else BLUE))
            if socket.identifier == selected_id:
                self.socket_table.selectRow(index)
        self.socket_table.blockSignals(False)
        for state, value in self.socket_stat_values.items():
            value.setText(f"{sum(s.state == state for s in self.sockets):02}")
        self.socket_count_label.setText(f"소켓 {len(self.sockets)}개 · 서버 대기 소켓과 접속 소켓을 구분합니다.")
        self.filter_sockets()
        for connection in self.connections:
            peer_id = self.selected_peers.get(connection.identifier)
            if peer_id and not any(p.identifier == peer_id for p in self.server_peers(connection)):
                self.selected_peers.pop(connection.identifier, None)
                if self.selected_connection().identifier == connection.identifier:
                    self.clear_message_selection()
            self.refresh_connection_button(connection)
        self.update_send_button()

    def filter_sockets(self):
        connection_id = self.socket_connection_filter.currentData()
        state = self.socket_state_filter.currentData()
        visible = []
        for index, item in enumerate(self.sockets):
            hidden = (connection_id is not None and item.connection_id != connection_id) or (state is not None and item.state != state)
            self.socket_table.setRowHidden(index, hidden)
            if not hidden:
                visible.append(index)
        self.socket_empty.setVisible(not visible)
        current = self.socket_table.currentRow()
        if visible:
            self.socket_table.selectRow(current if current in visible else visible[0])
        else:
            self.socket_table.clearSelection()
        self.update_socket_inspector()

    def inspected_socket(self):
        row_index = self.socket_table.currentRow()
        if row_index < 0 or not self.socket_table.selectionModel().hasSelection() or self.socket_table.isRowHidden(row_index):
            return None
        return self.sockets[row_index]

    def update_socket_inspector(self):
        item = self.inspected_socket()
        if item is None:
            self.socket_detail_title.setText("선택한 소켓 없음")
            for value in self.socket_detail_labels.values():
                value.setText("—")
            self.socket_config_note.clear()
            self.socket_role_note.setText("소켓 목록에서 확인할 행을 선택하세요.")
            self.socket_use_button.setEnabled(False)
            return
        connection = next(c for c in self.connections if c.identifier == item.connection_id)
        self.socket_detail_title.setText(f"{item.identifier}  ·  {connection.title}  ·  {item.state}")
        values = (item.local_ip, str(item.local_port), item.remote_ip or "—", str(item.remote_port) if item.remote_port is not None else "—")
        for key, value in zip(("local_ip", "local_port", "remote_ip", "remote_port"), values):
            self.socket_detail_labels[key].setText(value)
        self.socket_config_note.setText(f"연결 설정  |  Local Bind: {connection.local_endpoint}  |  Remote 대상: {connection.remote_endpoint or '접속한 클라이언트에 따라 결정'}")
        note = {
            "Client": "Local Port 0(자동)을 설정하면 연결 후 운영체제가 배정한 포트를 표시합니다.",
            "Listen": "LISTENING은 접속을 기다리는 소켓입니다. Remote는 없으며, 송신하려면 Accepted 소켓을 선택합니다.",
            "Accepted": "서버가 수락한 개별 연결입니다. 같은 Local Port를 사용해도 Remote IP·Port로 각 클라이언트를 구분합니다.",
            "UDP": f"UDP는 고정된 연결 상대가 없습니다. 각 수신의 발신 주소는 로그에서 확인합니다. 송신 대상 설정은 {connection.remote_endpoint}입니다.",
        }
        self.socket_role_note.setText(note[item.role])
        self.socket_use_button.setEnabled(item.state == "ESTABLISHED" or (item.state == "BOUND" and bool(connection.remote_endpoint)))

    def use_inspected_socket(self):
        item = self.inspected_socket()
        if item is None or not self.socket_use_button.isEnabled():
            return
        current = self.current_socket()
        if current is None or current.identifier != item.identifier:
            self.clear_message_selection()
        index = next(i for i, c in enumerate(self.connections) if c.identifier == item.connection_id)
        if item.role == "Accepted":
            self.selected_peers[item.connection_id] = item.identifier
        self.select_connection(index)
        self.show_page(0)

    def make_spectrum_card(self, expanded: bool = False) -> Card:
        card = Card("수신 스펙트럼", "예시 데이터")
        card.setMinimumWidth(330)
        info = row(label("CH 1", color=BLUE), label("중심 1,000 MHz  /  Span 20 MHz", "caption"))
        info.addStretch()
        card.body.addLayout(info)
        plot = SpectrumPlot()
        if expanded:
            plot.setMinimumHeight(340)
        card.body.addWidget(plot, 1)
        legend = row(label("━  Spectrum", color=BLUE), label("┄  Max hold", "muted"))
        legend.addStretch()
        hold = QCheckBox("최대값 유지")
        hold.setChecked(True)
        hold.toggled.connect(lambda checked: (setattr(plot, "show_peak_hold", checked), plot.update()))
        legend.addWidget(hold)
        card.body.addLayout(legend)
        card.body.addWidget(divider())
        metrics = QHBoxLayout()
        for name, value in (("PEAK FREQUENCY", "1,000.0 MHz"), ("PEAK LEVEL", "−24.2 dBm"), ("BINS", "1,024")):
            metric = QVBoxLayout()
            metric.setSpacing(4)
            metric.addWidget(label(name, "caption"))
            metric.addWidget(label(value, "heading"))
            metrics.addLayout(metric, 1)
        card.body.addLayout(metrics)
        return card

    def make_spectrum_page(self) -> QWidget:
        page, layout = self.page("스펙트럼", "수신 신호의 주파수 분포와 피크 정보를 확인합니다.")
        controls = Card()
        toolbar = row(label("수신 연결", "muted"), combo(["스펙트럼 수신  ·  UDP"]), label("채널", "muted"), combo(["CH 1"]))
        toolbar.addStretch()
        toolbar.addWidget(chip("정적 예시 그래프"))
        controls.body.addLayout(toolbar)
        layout.addWidget(controls)
        layout.addWidget(self.make_spectrum_card(expanded=True), 3)
        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        marker = Card("마커", "M1")
        marker.body.addWidget(table(["마커", "주파수", "레벨"], [["M1 · Peak", "1,000.0 MHz", "−24.2 dBm"]]), 1)
        bottom.addWidget(marker, 1)
        settings = Card("표시 설정")
        form = QFormLayout()
        form.addRow("주파수 단위", combo(["MHz"]))
        form.addRow("레벨 단위", combo(["dBm"]))
        form.addRow("표시 범위", label("990 ~ 1,010 MHz", "muted"))
        settings.body.addLayout(form)
        settings.body.addStretch()
        settings.body.addWidget(label("수신 데이터 형식 확정 후 표시 옵션을 연결합니다.", "caption"))
        bottom.addWidget(settings, 1)
        layout.addLayout(bottom, 1)
        return page

    def show_connection_dialog(self, checked=False, *, edit=False):
        original = self.selected_connection() if edit else None
        if edit and self.connection_sockets(original):
            QMessageBox.information(self, '연결 설정', '연결을 해제한 뒤 설정을 편집하세요.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('연결 설정 편집' if edit else '연결 추가')
        dialog.setMinimumWidth(470)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(label("통신 연결 추가", "title"))
        layout.addWidget(label("여러 연결을 등록하고 각각 송신 대상으로 선택할 수 있습니다.", "muted"))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        name = QLineEdit("새 연결")
        name.setObjectName("connectionName")
        name.setMaxLength(24)
        mode = combo(["TCP Client", "TCP Server", "UDP"])
        mode.setObjectName("connectionMode")
        remote_host = QLineEdit("127.0.0.1")
        remote_host.setObjectName("remoteHost")
        local_host = QLineEdit("0.0.0.0")
        local_host.setObjectName("localHost")
        remote_port = QSpinBox()
        remote_port.setObjectName("remotePort")
        remote_port.setRange(1, 65535)
        remote_port.setValue(5000)
        local_port = QSpinBox()
        local_port.setObjectName("localPort")
        local_port.setRange(0, 65535)
        local_port.setSpecialValueText("자동 할당 (0)")
        local_host.setToolTip("0.0.0.0은 모든 로컬 인터페이스입니다. 특정 내 PC 주소를 입력할 수도 있습니다.")
        local_port.setToolTip("0은 운영체제에 포트 배정을 맡기는 설정입니다. 소켓 현황에서는 배정 결과를 표시합니다.")
        form.addRow("연결 이름", name)
        form.addRow("통신 방식", mode)
        form.addRow("Local IP · 내 PC", local_host)
        form.addRow("Local Port", local_port)
        form.addRow("Remote IP · 상대 장치", remote_host)
        form.addRow("Remote Port", remote_port)
        layout.addLayout(form)
        address_note = label("Local IP 0.0.0.0: 모든 인터페이스 · Local Port 0: 자동 배정\n연결 후 Local / Remote 주소는 소켓 현황에서 확인합니다.", "caption")
        address_note.setWordWrap(True)
        layout.addWidget(address_note)
        layout.addWidget(label('설정 저장 후 연결 버튼을 누르면 연결합니다.', 'caption'))
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        confirm = actions.button(QDialogButtonBox.StandardButton.Ok)
        confirm.setText('설정 적용' if edit else '연결 추가')
        confirm.setObjectName("primary")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        def validate():
            try:
                ipaddress.IPv4Address(local_host.text().strip())
                if mode.currentText() != "TCP Server":
                    ipaddress.IPv4Address(remote_host.text().strip())
                confirm.setEnabled(bool(name.text().strip()))
            except ValueError:
                confirm.setEnabled(False)
        def change_mode():
            is_server = mode.currentText() == "TCP Server"
            form.setRowVisible(remote_host, not is_server)
            form.setRowVisible(remote_port, not is_server)
            local_port.setValue({"TCP Client": 0, "TCP Server": 7000, "UDP": 6000}[mode.currentText()])
            address_note.setText(
                "서버는 Local IP / Port에서 접속을 기다립니다.\nRemote IP / Port는 접속한 각 클라이언트 소켓에서 확인합니다."
                if is_server else
                "Local IP 0.0.0.0: 모든 인터페이스 · Local Port 0: 자동 배정\n연결 후 Local / Remote 주소는 소켓 현황에서 확인합니다."
            )
            validate()
        for edit in (name, remote_host, local_host):
            edit.textChanged.connect(validate)
        mode.currentIndexChanged.connect(change_mode)
        if original:
            name.setText(original.name)
            mode.setCurrentText(original.mode)
            host, port = original.local_endpoint.rsplit(':', 1)
            local_host.setText(host); local_port.setValue(int(port))
            if original.remote_endpoint:
                host, port = original.remote_endpoint.rsplit(':', 1)
                remote_host.setText(host); remote_port.setValue(int(port))
            form.setRowVisible(remote_host, original.mode != 'TCP Server')
            form.setRowVisible(remote_port, original.mode != 'TCP Server')
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addWidget(actions)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prefix = {"TCP Client": "TCP", "TCP Server": "SRV", "UDP": "UDP"}[mode.currentText()]
            number = 1
            identifiers = {connection.identifier for connection in self.connections}
            while f"{prefix}-{number:02}" in identifiers:
                number += 1
            connection = ConnectionPreview(
                original.identifier if original else f"{prefix}-{number:02}", name.text().strip(), mode.currentText(),
                f"{local_host.text().strip()}:{local_port.value()}",
                "" if mode.currentText() == "TCP Server" else f"{remote_host.text().strip()}:{remote_port.value()}",
            )
            if original:
                self.connections[self.selected_connection_index] = connection
                self.clear_connection_cards()
                for index, item in enumerate(self.connections):
                    self.append_connection_button(index, item)
                    self.log_connection_filter.setItemText(index + 1, item.title)
                    self.socket_connection_filter.setItemText(index + 1, item.title)
                self.connection_errors.pop(connection.identifier, None)
                self.select_connection(self.selected_connection_index)
                self.traffic_monitor.set_connections(self.connections)
            else:
                self.add_connection_preview(connection)

    def add_connection_preview(self, connection: ConnectionPreview):
        if any(item.identifier == connection.identifier for item in self.connections):
            raise ValueError("Connection IDs must be unique")
        self.connections.append(connection)
        index = len(self.connections) - 1
        self.append_connection_button(index, connection)
        self.log_connection_filter.addItem(connection.title, connection.identifier)
        self.socket_connection_filter.addItem(connection.title, connection.identifier)
        tcp_count = sum(item.mode.startswith("TCP") for item in self.connections)
        self.connection_summary.setText(f"프로파일 {len(self.connections):02}개  ·  TCP {tcp_count} / UDP {len(self.connections) - tcp_count}")
        self.sidebar_connections.setText(f"      연결 프로파일       {len(self.connections):02}")
        self.select_connection(index)
        self.traffic_monitor.set_connections(self.connections)


def main() -> int:
    parser = argparse.ArgumentParser(description="DS Simulator 화면 프로토타입")
    parser.add_argument("--screenshot", type=Path, help="선택 화면을 PNG로 저장하고 종료")
    parser.add_argument("--page", choices=PAGE_NAMES, default="workspace")
    parser.add_argument("--preview-stage", choices=("initial", "connected", "ready"), default="initial", help="워크스페이스의 모의 연결/ICD 선택 단계")
    parser.add_argument("--icd-excel", type=Path, help="로컬 Excel에서 지정한 데이터 시트를 가져옵니다")
    parser.add_argument("--icd-sheet", help="가져올 (데이터) 시트 이름")
    parser.add_argument('--mock', action='store_true', help='실제 통신 없이 모의 화면을 실행합니다.')
    parser.add_argument('--network-self-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if bool(args.icd_excel) != bool(args.icd_sheet):
        parser.error("--icd-excel과 --icd-sheet를 함께 지정하세요.")
    app = QApplication(sys.argv[:1])
    if args.network_self_test:
        from .network_check import run_check
        return run_check(args.network_self_test)
    app.setStyle("Fusion")
    families = QFontDatabase.families()
    font_family = next((f for f in ("Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR", "Segoe UI") if f in families), "Sans Serif")
    app.setFont(QFont(font_family, 10))
    app.setStyleSheet(STYLESHEET)
    window = SimulatorWindow(mock=args.mock)
    if args.icd_excel:
        try:
            window.apply_catalog(read_icd_sheet(args.icd_excel, args.icd_sheet), f"{args.icd_excel.name} · {args.icd_sheet}")
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    if args.preview_stage != "initial" and args.mock:
        window.toggle_preview_connection()
        if args.preview_stage == "ready":
            window.message_catalog.setCurrentRow(0)
        window.statusBar().clearMessage()
    index = PAGE_NAMES.index(args.page)
    window.show_page(index)
    window.show()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            target = window.spectrum_window if args.page == "spectrum" else window
            ok = target.grab().save(str(args.screenshot))
            window.close()
            app.exit(0 if ok else 1)
        QTimer.singleShot(350, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
