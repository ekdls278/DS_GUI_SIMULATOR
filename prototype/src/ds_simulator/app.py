"""Interactive mock simulator: no real sockets or instrument control."""

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
    QVBoxLayout, QWidget,
)

from .theme import BLUE, STYLESHEET
from .widgets import Card, SpectrumPlot, button, chip, icon, label, row, table
from .workspace import WorkspaceMixin
from .scenario_editor import ScenarioEditor
from .runtime import MockTransport
from .activity import ActivityMixin
from .profiles import ProfileMixin


from .preview_data import CONNECTIONS, MESSAGES, SOCKETS, ConnectionPreview

PAGE_NAMES = ("workspace", "sockets", "icd", "spectrum", "scenario")


def combo(values: list[str]) -> QComboBox:
    widget = QComboBox()
    widget.addItems(values)
    return widget


def divider() -> QFrame:
    widget = QFrame()
    widget.setFixedHeight(1)
    widget.setStyleSheet("background: #e8edf4; border: 0;")
    return widget


class SimulatorWindow(WorkspaceMixin, ActivityMixin, ProfileMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DS Simulator — 화면 프로토타입")
        self.resize(1680, 1040)
        self.setMinimumSize(1180, 760)
        self.setWindowIcon(icon("logo", BLUE, 32))
        self.connections = list(CONNECTIONS)
        self.sockets = [s for s in SOCKETS if s.connection_id != "TCP-01"]
        self.next_socket_number = 7
        self.selected_connection_index = 0
        self.selected_message_name = None
        self.connection_buttons = {}
        self.selected_peers = {}
        self.transport = MockTransport(lambda: self.connections, lambda: self.sockets, self)
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
        for page in (self.make_workspace(), self.make_sockets_page(), self.make_icd_page(), self.make_spectrum_page(), self.make_scenario_page()):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        body.addWidget(self.stack, 1)
        layout.addLayout(body, 1)
        self.setCentralWidget(root)
        self.select_connection(0)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addWidget(label("   ●  MOCK 모드 · 실제 장비에 연결하지 않습니다. 스펙트럼은 정적 예시입니다.", "caption"))
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
        layout.addWidget(chip("●  MOCK MODE"))
        layout.addSpacing(5)
        layout.addWidget(label("예시 데이터", "muted"))
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
            ("시나리오", "folder"),
        )):
            nav = button(text, icon_name=glyph)
            nav.setObjectName("nav")
            nav.setCheckable(True)
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
        layout.addStretch()
        note = QFrame()
        note.setObjectName("previewNote")
        notes = QVBoxLayout(note)
        notes.setContentsMargins(12, 14, 12, 14)
        notes.setSpacing(9)
        notes.addWidget(label("DESIGN PREVIEW", color="#b2c9ef"))
        description = label("화면 구성과 조작 흐름을\n확인하는 프로토타입입니다.")
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

    def make_scenario_page(self):
        page, layout = self.page("시나리오 편집기", "ICD 송신·대기·반복 블록으로 시험을 구성하고 모의 실행합니다.")
        self.scenario_editor = ScenarioEditor(self)
        layout.addWidget(self.scenario_editor, 1)
        return page

    def closeEvent(self, event):
        self.scenario_editor.runner.stop()
        if self.scenario_editor.confirm_discard():
            event.accept()
        else:
            event.ignore()

    def show_page(self, index: int):
        self.stack.setCurrentIndex(index)
        self.nav_group.button(index).setChecked(True)
        if index == 4:
            self.scenario_editor.show_properties()

    def make_sockets_page(self) -> QWidget:
        page, layout = self.page("소켓 현황", "앱에서 관리하는 소켓의 상태와 Local / Remote 주소를 확인합니다. 현재 값은 모두 예시입니다.")
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

        catalog = Card("앱 소켓 목록", "모의 상태")
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
            "Client": "Local Port 0(자동)을 설정하면 연결 후 운영체제가 배정한 포트를 표시합니다. 위 주소와 포트는 예시입니다.",
            "Listen": "LISTENING은 접속을 기다리는 소켓입니다. Remote는 없으며, 송신하려면 Accepted 소켓을 선택합니다.",
            "Accepted": "서버가 수락한 개별 연결입니다. 같은 Local Port를 사용해도 Remote IP·Port로 각 클라이언트를 구분합니다.",
            "UDP": f"이 UDP 소켓은 바인딩만 한 예시입니다. 고정된 연결 상대는 없고, 송신 대상 설정은 {connection.remote_endpoint}입니다.",
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

    def make_icd_page(self) -> QWidget:
        page, layout = self.page("ICD 메시지", "엑셀에서 정의한 메시지와 필드 구조를 확인합니다.")
        profile = Card()
        profile_row = row(label("Receiver_ICD_v0.1.xlsx", "heading"), chip("예시 프로파일"))
        profile_row.addStretch()
        load = button("엑셀 가져오기 · 준비 중", icon_name="plus")
        load.setEnabled(False)
        load.setToolTip("실제 Excel ICD 열 구조를 확인한 뒤 구현합니다.")
        profile_row.addWidget(load)
        profile.body.addLayout(profile_row)
        profile.body.addWidget(label("아래 메시지와 필드 정의는 화면 구성을 위한 예시입니다. 실제 ICD는 추후 적용합니다.", "muted"))
        layout.addWidget(profile)
        columns = QHBoxLayout()
        columns.setSpacing(16)
        catalog = Card("메시지 목록", "05")
        catalog.setMinimumWidth(300)
        message_table = table(["CMD (예시)", "메시지"], [[value.cmd, name] for name, value in MESSAGES.items()])
        message_table.setMinimumHeight(295)
        message_table.verticalHeader().setDefaultSectionSize(48)
        catalog.body.addWidget(message_table, 1)
        catalog.body.addWidget(label("메시지를 선택하면 필드 구성이 표시됩니다.", "caption"))
        columns.addWidget(catalog, 3)
        detail = Card()
        detail_title = label("SET_FREQUENCY", "heading")
        detail_subtitle = label("SRC 0xAAAA  →  DST 0xBBBB  ·  CMD 0xCCCC", "muted")
        detail.body.addWidget(detail_title)
        detail.body.addWidget(detail_subtitle)
        field_stack = QStackedWidget()
        for message in MESSAGES.values():
            fields_table = table(["필드", "자료형", "예시 값", "단위", "설명"], message.field_rows())
            fields_table.verticalHeader().setDefaultSectionSize(40)
            field_stack.addWidget(fields_table)
        detail.body.addWidget(field_stack, 1)
        detail.body.addWidget(label("SRC / DST / CMD의 필드 폭·순서·바이트 순서는 ICD 확인 후 정합니다.", "caption"))
        columns.addWidget(detail, 7)
        layout.addLayout(columns, 3)
        message_table.selectRow(0)
        def select_message():
            index = message_table.currentRow()
            if index < 0:
                return
            name = list(MESSAGES)[index]
            message = MESSAGES[name]
            field_stack.setCurrentIndex(index)
            detail_title.setText(name)
            detail_subtitle.setText(f"SRC {message.src}  →  DST {message.dst}  ·  CMD {message.cmd}")
            property_name.setText(name)
            property_id.setText(message.cmd)
            raw.setPlainText(header_preview(message))
        message_table.itemSelectionChanged.connect(select_message)
        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        properties = Card("메시지 속성")
        properties_form = QFormLayout()
        properties_form.setVerticalSpacing(15)
        properties_form.setHorizontalSpacing(20)
        property_name = label("SET_FREQUENCY")
        property_id = label("0xCCCC")
        properties_form.addRow(label("메시지 이름", "muted"), property_name)
        properties_form.addRow(label("CMD", "muted"), property_id)
        properties_form.addRow(label("ICD 프로파일", "muted"), label("Receiver_ICD_v0.1.xlsx"))
        properties.body.addLayout(properties_form)
        properties.body.addStretch()
        properties.body.addWidget(label("값 입력과 송신은 ICD 송수신 화면에서 진행합니다.", "caption"))
        bottom.addWidget(properties, 4)
        preview = Card("ICD 헤더 미리보기", "필드 값")
        preview.body.addWidget(label("SRC · DST · CMD", "caption"))
        def header_preview(message):
            return f"SRC    {message.src}\nDST    {message.dst}\nCMD    {message.cmd}"
        raw = QPlainTextEdit(header_preview(MESSAGES["SET_FREQUENCY"]))
        raw.setReadOnly(True)
        raw.setStyleSheet("font-family: 'Consolas', 'DejaVu Sans Mono'; font-size: 14px; padding: 14px;")
        preview.body.addWidget(raw, 1)
        preview.body.addWidget(label("헤더 값 표시 예시입니다. 실제 전송 바이트는 아직 정의하지 않았습니다.", "caption"))
        bottom.addWidget(preview, 6)
        layout.addLayout(bottom, 2)
        return page

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

    def show_connection_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("연결 추가 · 화면 미리보기")
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
        remote_host = QLineEdit("192.168.0.12")
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
        layout.addWidget(chip("UI PREVIEW · 프로파일만 추가하며 소켓은 생성하지 않습니다."))
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        confirm = actions.button(QDialogButtonBox.StandardButton.Ok)
        confirm.setText("예시 연결 추가")
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
                f"{prefix}-{number:02}", name.text().strip(), mode.currentText(),
                f"{local_host.text().strip()}:{local_port.value()}",
                "" if mode.currentText() == "TCP Server" else f"{remote_host.text().strip()}:{remote_port.value()}",
            )
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


def main() -> int:
    parser = argparse.ArgumentParser(description="DS Simulator 화면 프로토타입")
    parser.add_argument("--screenshot", type=Path, help="선택 화면을 PNG로 저장하고 종료")
    parser.add_argument("--page", choices=PAGE_NAMES, default="workspace")
    parser.add_argument("--preview-stage", choices=("initial", "connected", "ready"), default="initial", help="워크스페이스의 모의 연결/ICD 선택 단계")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    families = QFontDatabase.families()
    font_family = next((f for f in ("Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR", "Segoe UI") if f in families), "Sans Serif")
    app.setFont(QFont(font_family, 10))
    app.setStyleSheet(STYLESHEET)
    window = SimulatorWindow()
    if args.preview_stage != "initial":
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
            ok = window.grab().save(str(args.screenshot))
            window.close()
            app.exit(0 if ok else 1)
        QTimer.singleShot(350, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
