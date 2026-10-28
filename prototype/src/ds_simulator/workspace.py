"""Same-screen socket → connect → ICD → send flow. All connections are simulated."""

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFormLayout, QFrame, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from .preview_data import MESSAGES, SocketPreview
from .domain import Step, validate_message
from .connection_cards import ConnectionCard, SERVER_COLORS
from .theme import BLUE
from .widgets import Card, button, chip, label, row


class WorkspaceMixin:
    def make_workspace(self):
        page, layout = self.page("ICD 송수신", "같은 화면에서 소켓을 연결하고, ICD 메시지를 선택해 송신합니다.")
        layout.setSpacing(12)
        steps = Card()
        steps.body.setContentsMargins(16, 9, 16, 9)
        flow = QHBoxLayout()
        self.flow_steps = []
        for index, title in enumerate(("소켓 선택", "연결", "ICD 선택", "송신")):
            item = chip(f"{index + 1:02}  {title}", "neutralChip")
            self.flow_steps.append(item)
            flow.addWidget(item)
            if index < 3:
                flow.addWidget(label("→", "muted"))
        flow.addStretch()
        self.flow_hint = label("소켓을 연결하세요.", "muted")
        flow.addWidget(self.flow_hint)
        steps.body.addLayout(flow)
        layout.addWidget(steps)
        panels = QHBoxLayout()
        panels.setSpacing(14)
        panels.addWidget(self.make_connections(), 29)
        panels.addWidget(self.make_message_catalog(), 26)
        panels.addWidget(self.make_composer(), 45)
        layout.addLayout(panels, 3)
        layout.addWidget(self.make_log(), 2)
        return page

    def make_connections(self):
        card = Card()
        card.setMinimumWidth(295)
        card.body.setContentsMargins(12, 8, 12, 12)
        self.socket_tabs = QTabWidget()
        self.socket_tabs.setObjectName("socketTabs")
        overview = QWidget()
        body = QVBoxLayout(overview)
        body.setContentsMargins(4, 12, 4, 0)
        body.setSpacing(9)
        self.connection_summary = label("프로파일 04개  ·  상태 예시", "caption")
        body.addWidget(self.connection_summary)
        self.connection_group = QButtonGroup(card)
        self.connection_cards = {}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: white; }")
        scroll.setMinimumHeight(300)
        self.connection_scroll = scroll
        items = QWidget()
        self.connection_list = QVBoxLayout(items)
        self.connection_list.setContentsMargins(0, 0, 3, 0)
        self.connection_list.setSpacing(8)
        self.connection_list.addStretch()
        for index, connection in enumerate(self.connections):
            self.append_connection_button(index, connection)
        scroll.setWidget(items)
        body.addWidget(scroll, 1)
        self.connect_button = button("연결", primary=True, icon_name="link")
        self.connect_button.setToolTip("화면에서 연결 상태만 변경합니다. 실제 소켓은 생성하지 않습니다.")
        self.connect_button.clicked.connect(self.toggle_preview_connection)
        body.addWidget(self.connect_button)
        self.accept_demo_button = button("클라이언트 접속 예시 추가")
        self.accept_demo_button.clicked.connect(self.accept_preview_peer)
        body.addWidget(self.accept_demo_button)
        body.addWidget(label("연결·해제는 화면 검토용 모의 동작입니다.", "caption"))
        self.socket_tabs.addTab(overview, "소켓 현황")

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(8, 16, 8, 8)
        details_layout.setSpacing(12)
        self.left_connection_title = label("", "heading")
        self.left_connection_info = label("", "muted")
        self.left_connection_info.setWordWrap(True)
        self.left_connection_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.left_connection_title)
        details_layout.addWidget(self.left_connection_info)
        details_layout.addStretch()
        details_layout.addWidget(label("Local / Remote 값은 모두 예시입니다.", "caption"))
        self.socket_tabs.addTab(details, "연결 정보")
        card.body.addWidget(self.socket_tabs, 1)
        add = button("소켓 프로파일 추가", icon_name="plus")
        add.clicked.connect(self.show_connection_dialog)
        card.body.addWidget(add)
        self.connection_group.idClicked.connect(self.select_connection_header)
        return card

    def append_connection_button(self, index, connection):
        server_number = sum(c.mode == "TCP Server" for c in self.connections[:index])
        card = ConnectionCard(connection, SERVER_COLORS[server_number % len(SERVER_COLORS)])
        card.peer_selected.connect(self.select_server_peer)
        self.connection_cards[connection.identifier] = card
        self.connection_buttons[connection.identifier] = card.header
        self.connection_group.addButton(card.header, index)
        self.connection_list.insertWidget(self.connection_list.count() - 1, card)
        self.refresh_connection_button(connection)

    def clear_connection_cards(self):
        for card in self.connection_cards.values():
            self.connection_group.removeButton(card.header)
            self.connection_list.removeWidget(card)
            card.deleteLater()
        self.connection_cards.clear()
        self.connection_buttons.clear()

    def refresh_connection_button(self, connection):
        self.connection_cards[connection.identifier].update_snapshot(
            connection, self.connection_sockets(connection), self.server_peers(connection),
            self.selected_peers.get(connection.identifier),
            self.selected_connection().identifier == connection.identifier,
        )

    def select_connection_header(self, index):
        connection = self.connections[index]
        if connection.mode == "TCP Server":
            self.selected_peers.pop(connection.identifier, None)
            self.clear_message_selection()
        self.select_connection(index)

    def select_server_peer(self, connection_id, socket_id):
        index = next((i for i, c in enumerate(self.connections) if c.identifier == connection_id and c.mode == "TCP Server"), None)
        if index is None or not any(p.identifier == socket_id for p in self.server_peers(self.connections[index])):
            return
        if self.selected_connection_index != index or self.selected_peers.get(connection_id) != socket_id:
            self.clear_message_selection()
        self.selected_peers[connection_id] = socket_id
        self.select_connection(index)

    def make_message_catalog(self):
        card = Card("ICD 선택", "05")
        card.setMinimumWidth(265)
        card.body.addWidget(label("Receiver_ICD_v0.1.xlsx", "caption"))
        self.message_search = QLineEdit()
        self.message_search.setPlaceholderText("메시지 이름 또는 CMD 검색")
        card.body.addWidget(self.message_search)
        self.message_catalog = QListWidget()
        self.message_catalog.setObjectName("messageCatalog")
        for name, message in MESSAGES.items():
            item = QListWidgetItem(f"{name}\n{message.cmd}  ·  {message.description}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(f"{name}\n{message.description}\nSRC {message.src} · DST {message.dst} · CMD {message.cmd}")
            self.message_catalog.addItem(item)
        self.message_catalog.setMinimumHeight(260)
        self.message_catalog.currentItemChanged.connect(self.select_send_message)
        self.message_search.textChanged.connect(self.filter_messages)
        card.body.addWidget(self.message_catalog, 1)
        self.catalog_hint = label("소켓 연결 후 ICD를 선택하세요.", "muted")
        self.catalog_hint.setWordWrap(True)
        card.body.addWidget(self.catalog_hint)
        card.body.addWidget(label("메시지 정의와 필드 값은 예시입니다.", "caption"))
        return card

    def filter_messages(self, text):
        term = text.casefold()
        for index in range(self.message_catalog.count()):
            item = self.message_catalog.item(index)
            item.setHidden(term not in item.text().casefold())
        item = self.message_catalog.currentItem()
        if item and item.isHidden():
            self.clear_message_selection()
            self.update_send_button()

    def make_composer(self):
        card = Card("메시지 편집 · 송신", "ICD")
        card.setMinimumWidth(410)
        card.body.setSpacing(10)
        target = QFrame()
        target.setObjectName("targetBanner")
        target_layout = QVBoxLayout(target)
        target_layout.setContentsMargins(12, 10, 12, 10)
        target_layout.setSpacing(4)
        self.target_title = label("", "heading", color=BLUE)
        self.target_address = label("", "caption")
        target_layout.addWidget(self.target_title)
        target_layout.addWidget(self.target_address)
        card.body.addWidget(target)
        self.message_title = label("ICD 메시지를 선택하세요", "heading")
        self.message_description = label("선택한 메시지의 필드가 여기에 표시됩니다.", "muted")
        card.body.addWidget(self.message_title)
        card.body.addWidget(self.message_description)
        self.editor = QWidget()
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(12)
        headers = QHBoxLayout()
        self.header_inputs = {}
        for name in ("src", "dst", "cmd"):
            field = QVBoxLayout()
            field.setSpacing(4)
            field.addWidget(label(name.upper(), "caption"))
            edit = QLineEdit()
            edit.setObjectName(f"header_{name}")
            edit.setPlaceholderText("ICD 선택 후 표시")
            edit.setValidator(QRegularExpressionValidator(QRegularExpression("0[xX][0-9a-fA-F]+"), edit))
            edit.textChanged.connect(self.update_send_button)
            self.header_inputs[name] = edit
            field.addWidget(edit)
            headers.addLayout(field, 1)
        editor_layout.addLayout(headers)
        editor_layout.addWidget(label("DST는 ICD 식별자입니다. 송신 소켓은 왼쪽에서 선택합니다.", "caption"))
        self.payload_form = QFormLayout()
        self.payload_form.setVerticalSpacing(9)
        editor_layout.addLayout(self.payload_form)
        self.payload_inputs = {}
        card.body.addWidget(self.editor)
        card.body.addStretch()
        self.send_feedback = label("", "caption")
        self.send_feedback.setWordWrap(True)
        card.body.addWidget(self.send_feedback)
        self.big_endian = QCheckBox("빅엔디안 (모의 로그에 설정만 기록)")
        card.body.addWidget(self.big_endian)
        self.send_button = button("소켓을 먼저 연결하세요", primary=True, icon_name="arrow")
        self.send_button.clicked.connect(self.preview_send)
        card.body.addWidget(self.send_button)
        return card

    def selected_connection(self):
        return self.connections[self.selected_connection_index]

    def connection_sockets(self, connection):
        return [s for s in self.sockets if s.connection_id == connection.identifier]

    def server_peers(self, connection):
        return [s for s in self.connection_sockets(connection) if s.role == "Accepted" and s.state == "ESTABLISHED"]

    def current_socket(self):
        connection = self.selected_connection()
        if connection.mode == "TCP Server":
            return next((s for s in self.server_peers(connection) if s.identifier == self.selected_peers.get(connection.identifier)), None)
        return next((s for s in self.connection_sockets(connection) if s.state in ("ESTABLISHED", "BOUND")), None)

    def select_connection(self, index):
        if not 0 <= index < len(self.connections):
            return
        if index != self.selected_connection_index:
            self.clear_message_selection()
        self.selected_connection_index = index
        connection = self.selected_connection()
        self.connection_group.button(index).setChecked(True)
        peer_id = self.selected_peers.get(connection.identifier)
        if peer_id and not any(p.identifier == peer_id for p in self.server_peers(connection)):
            self.selected_peers.pop(connection.identifier, None)
            self.clear_message_selection()
        for item in self.connections:
            self.refresh_connection_button(item)
        self.update_send_button()
        self.connection_scroll.ensureWidgetVisible(self.connection_cards[connection.identifier])

    def clear_message_selection(self):
        self.selected_message_name = None
        self.message_catalog.blockSignals(True)
        self.message_catalog.setCurrentRow(-1)
        self.message_catalog.clearSelection()
        self.message_catalog.blockSignals(False)
        for edit in self.header_inputs.values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        while self.payload_form.rowCount():
            self.payload_form.removeRow(0)
        self.payload_inputs.clear()
        self.message_title.setText("ICD 메시지를 선택하세요")
        self.message_description.setText("선택한 메시지의 필드가 여기에 표시됩니다.")
        self.send_feedback.clear()

    def select_send_message(self, item, previous=None):
        if item is None or self.current_socket() is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        message = MESSAGES[name]
        self.selected_message_name = name
        self.message_title.setText(name)
        self.message_description.setText(f"{message.description}  ·  필드 {len(message.fields)}개")
        for key, edit in self.header_inputs.items():
            edit.setText(getattr(message, key))
        while self.payload_form.rowCount():
            self.payload_form.removeRow(0)
        self.payload_inputs.clear()
        for key, data_type, value, unit, description in message.fields:
            edit = QLineEdit(value)
            edit.textChanged.connect(self.update_send_button)
            edit.setToolTip(f"{key} · {data_type} · 화면 예시")
            self.payload_inputs[key] = edit
            self.payload_form.addRow(label(description, "muted"), row(edit, label(unit, "caption")) if unit != "—" else edit)
        self.send_feedback.clear()
        self.update_send_button()

    def update_send_button(self):
        connection = self.selected_connection()
        sockets = self.connection_sockets(connection)
        current = self.current_socket()
        remote = current.remote_endpoint if current and connection.mode == "TCP Server" else connection.remote_endpoint
        self.target_title.setText(f"송신 대상  →  {connection.title}")
        if current:
            remote_text = remote + (" (전송 대상)" if current.role == "UDP" else "")
            detail = f"{current.identifier} · {current.state}\nLocal    {current.local_endpoint}\nRemote  {remote_text}"
        elif sockets:
            detail = f"LISTENING · 클라이언트 접속 / 선택 대기\nLocal    {sockets[0].local_endpoint}\nRemote  선택 대기"
        else:
            detail = f"미연결 · 왼쪽에서 연결하세요\nLocal 설정    {connection.local_endpoint}\nRemote 설정  {remote or '접속 후 결정'}"
        self.target_address.setText(detail)
        self.left_connection_title.setText(connection.title)
        self.left_connection_info.setText(f"{connection.mode}\n\n{detail}\n\n설정 Local Bind\n{connection.local_endpoint}\n\n설정 Remote\n{connection.remote_endpoint or '접속 후 결정'}")
        self.connect_button.setText("연결 해제" if sockets else ("서버 대기 시작" if connection.mode == "TCP Server" else "연결"))
        self.accept_demo_button.setVisible(connection.mode == "TCP Server" and bool(sockets))
        ready = current is not None and bool(remote)
        self.message_catalog.setEnabled(ready)
        self.message_search.setEnabled(ready)
        self.editor.setEnabled(ready and self.selected_message_name is not None)
        self.catalog_hint.setText("송신할 ICD 메시지를 선택하세요." if ready else ("접속 클라이언트를 선택하세요." if sockets else "소켓 연결 후 ICD를 선택하세요."))
        valid = ready and self.selected_message_name is not None
        error = ""
        if valid:
            try:
                validate_message(self.selected_message_name, {k: e.text() for k, e in self.header_inputs.items()}, {k: e.text() for k, e in self.payload_inputs.items()})
            except ValueError as exc:
                error = str(exc)
                valid = False
        self.send_button.setToolTip(error or "모의 송신 로그를 기록합니다. 실제 패킷은 전송하지 않습니다.")
        self.send_feedback.setText(error)
        self.send_button.setEnabled(valid)
        if not ready:
            self.send_button.setText("접속 클라이언트를 선택하세요" if sockets else "소켓을 먼저 연결하세요")
        elif self.selected_message_name is None:
            self.send_button.setText("ICD 메시지를 선택하세요")
        else:
            self.send_button.setText(f"{connection.title}로 송신")
        stage = 1 if not ready else (2 if self.selected_message_name is None else 3)
        for index, item in enumerate(self.flow_steps):
            color, background = ("#1a9264", "#eaf8f1") if index < stage else ((BLUE, "#e8efff") if index == stage else ("#7b8799", "#f0f3f8"))
            item.setStyleSheet(f"color: {color}; background: {background}; border-radius: 5px; padding: 6px 14px;")
        self.flow_hint.setText(("연결 후 ICD 선택", "연결됨 · ICD를 선택하세요", "대상과 필드 확인 후 송신")[stage - 1])
        if not ready and sockets:
            self.flow_hint.setText("서버 대기 중 · 접속 클라이언트를 선택하세요")

    def new_socket_id(self):
        identifier = f"SOCK-{self.next_socket_number:03}"
        self.next_socket_number += 1
        return identifier

    def toggle_preview_connection(self):
        connection = self.selected_connection()
        self.clear_message_selection()
        if self.connection_sockets(connection):
            self.sockets = [s for s in self.sockets if s.connection_id != connection.identifier]
            self.selected_peers.pop(connection.identifier, None)
        else:
            local_ip, port_text = connection.local_endpoint.rsplit(":", 1)
            local_port = int(port_text) or 52000 + self.next_socket_number
            role = {"TCP Client": "Client", "TCP Server": "Listen", "UDP": "UDP"}[connection.mode]
            state = {"Client": "ESTABLISHED", "Listen": "LISTENING", "UDP": "BOUND"}[role]
            remote_ip, remote_port = "", None
            if role == "Client":
                local_ip = "192.168.0.100" if local_ip == "0.0.0.0" else local_ip
                remote_ip, remote_port_text = connection.remote_endpoint.rsplit(":", 1)
                remote_port = int(remote_port_text)
            self.sockets.append(SocketPreview(self.new_socket_id(), connection.identifier, role, state, local_ip, local_port, remote_ip, remote_port))
        self.refresh_connection_button(connection)
        self.refresh_socket_monitor()
        self.select_connection(self.selected_connection_index)
        self.preview_notice("연결 상태 전환 (모의)")

    def accept_preview_peer(self):
        connection = self.selected_connection()
        listener = next((s for s in self.connection_sockets(connection) if s.role == "Listen"), None)
        if listener is None:
            return
        self.clear_message_selection()
        local_ip = "192.168.0.100" if listener.local_ip == "0.0.0.0" else listener.local_ip
        # Deterministic UI sample; this does not accept a real network connection.
        peer = SocketPreview(self.new_socket_id(), connection.identifier, "Accepted", "ESTABLISHED", local_ip, listener.local_port, "192.168.0.21", 51000 + self.next_socket_number)
        self.sockets.append(peer)
        self.selected_peers[connection.identifier] = peer.identifier
        self.refresh_connection_button(connection)
        self.refresh_socket_monitor()
        self.select_connection(self.selected_connection_index)

    def preview_send(self):
        if not self.send_button.isEnabled():
            return
        current = self.current_socket()
        connection = self.selected_connection()
        step = Step.send(self.selected_message_name)
        step.connection_id, step.socket_id = connection.identifier, current.identifier
        step.headers = {k: e.text() for k, e in self.header_inputs.items()}
        step.values = {k: e.text() for k, e in self.payload_inputs.items()}
        step.big_endian = self.big_endian.isChecked()
        try:
            event = self.transport.send(step)
        except ValueError as exc:
            self.send_feedback.setText(str(exc))
            return
        self.send_feedback.setText(f"MOCK · 송신 기록 완료 · {self.selected_message_name}\n{current.local_endpoint} → {event['peer']}")
