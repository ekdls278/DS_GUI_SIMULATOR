"""Connection cards with an explicit listener → accepted-client hierarchy."""
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QFrame, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout

ROLE = Qt.ItemDataRole.UserRole
SERVER_COLORS = ('#3264e8', '#8058bf', '#198b81', '#bd7430')


class PeerTree(QTreeWidget):
    def drawBranches(self, painter, rect, index):
        super().drawBranches(painter, rect, index)
        if index.parent().isValid():
            painter.save()
            painter.setPen(QPen(QColor('#b9c9e3'), 1))
            x, y = rect.right() - self.indentation() // 2, rect.center().y()
            painter.drawLine(x, rect.top(), x, y)
            painter.drawLine(x, y, rect.right(), y)
            if index.row() < self.model().rowCount(index.parent()) - 1:
                painter.drawLine(x, y, x, rect.bottom())
            painter.restore()


class ConnectionCard(QFrame):
    peer_selected = Signal(str, str)

    def __init__(self, connection, accent='#3264e8', parent=None):
        super().__init__(parent)
        self.connection_id = connection.identifier
        self.is_server = connection.mode == 'TCP Server'
        self.accent = accent
        self.signature = None
        self.setObjectName('serverConnectionCard' if self.is_server else 'connectionCard')
        body = QVBoxLayout(self)
        body.setContentsMargins(5, 5, 5, 5)
        body.setSpacing(0)
        self.header = QPushButton()
        self.header.setObjectName('connectionHeader')
        self.header.setCheckable(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setMinimumHeight(88)
        self.header.setStyleSheet('''
            QPushButton#connectionHeader { text-align: left; border: 0; background: transparent; padding: 8px; font-size: 11px; }
            QPushButton#connectionHeader:hover { background: #edf3ff; }
            QPushButton#connectionHeader:checked { color: #285ac6; }
        ''')
        body.addWidget(self.header)
        if self.is_server:
            self.tree = PeerTree()
            self.tree.setObjectName('serverClients')
            self.tree.setHeaderHidden(True)
            self.tree.setIndentation(17)
            self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            palette = self.tree.palette()
            palette.setColor(QPalette.ColorRole.Highlight, QColor('#e5eeff'))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor('#2455bf'))
            self.tree.setPalette(palette)
            self.tree.setStyleSheet('''
                QTreeWidget#serverClients { border: 0; background: transparent; outline: 0; font-size: 11px; }
                QTreeWidget#serverClients::item { border-radius: 5px; padding: 3px; }
                QTreeWidget#serverClients::item:selected { background: #e5eeff; color: #2455bf; }
                QTreeWidget#serverClients::branch:selected { background: transparent; }
            ''')
            self.tree.itemSelectionChanged.connect(self.choose_peer)
            self.tree.itemCollapsed.connect(self.resize_tree)
            self.tree.itemExpanded.connect(self.resize_tree)
            body.addWidget(self.tree)

    def update_snapshot(self, connection, sockets, peers, selected_id, active):
        color = self.accent if self.is_server else ('#9bb9f9' if active else '#e1e6ef')
        background = '#f4f7ff' if active else '#ffffff'
        self.setStyleSheet(f'QFrame#{self.objectName()} {{ border: {3 if self.is_server else 1}px solid {color}; border-radius: 9px; background: {background}; }}')
        local = sockets[0].local_endpoint if sockets else connection.local_endpoint
        if self.is_server:
            listener = next((s for s in sockets if s.role == 'Listen'), None)
            local = listener.local_endpoint if listener else connection.local_endpoint
            state = 'LISTENING · 접속 대기 중' if listener else '서버 중지 · 대기 시작 필요'
            self.header.setText(f'TCP SERVER  ·  {connection.identifier}\n{connection.name}\nLocal  {local}\n{state}')
            self.header.setToolTip(f'{connection.title}\n서버 수신 주소: {local}\n0.0.0.0은 내 PC의 모든 인터페이스를 뜻합니다.\n송신하려면 아래 접속 클라이언트를 선택하세요. (모의 상태)')
            self.update_peers(peers, selected_id if active else None)
        else:
            mode = 'TCP CLIENT' if connection.mode == 'TCP Client' else 'UDP'
            state = ('연결됨' if connection.mode == 'TCP Client' else '바인딩됨') if sockets else '미연결'
            self.header.setText(f'{mode}  ·  {connection.title}\nLocal  {local}\n{"송신 대상" if connection.mode == "UDP" else "Remote"}  {connection.remote_endpoint}\n{state} · 모의')
            self.header.setToolTip(f'{connection.mode} · {state}\nLocal {local}\nRemote {connection.remote_endpoint}\n주소와 상태는 예시입니다.')

    def update_peers(self, peers, selected_id):
        signature = tuple((p.identifier, p.remote_endpoint, p.local_endpoint) for p in peers)
        self.tree.blockSignals(True)
        try:
            if signature != self.signature:
                expanded = self.root.isExpanded() if self.signature is not None else True
                self.tree.clear()
                self.root = QTreeWidgetItem(self.tree)
                self.root.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.root.setText(0, f'접속 클라이언트 · {len(peers)}개' if peers else '접속 클라이언트 없음')
                self.root.setSizeHint(0, QSize(0, 29))
                for peer in peers:
                    item = QTreeWidgetItem(self.root)
                    item.setData(0, ROLE, peer.identifier)
                    item.setText(0, f'{peer.remote_endpoint}\n{peer.identifier} · 연결됨')
                    item.setToolTip(0, f'Accepted · {peer.identifier}\nRemote {peer.remote_endpoint}\nLocal {peer.local_endpoint}\n클릭하면 이 클라이언트를 송신 대상으로 선택합니다.')
                    item.setSizeHint(0, QSize(0, 53))
                    font = QFont(self.tree.font())
                    font.setPointSize(9)
                    item.setFont(0, font)
                    item.setForeground(0, QColor('#254267'))
                self.root.setExpanded(expanded)
                self.signature = signature
            selected = next((self.root.child(i) for i in range(self.root.childCount()) if self.root.child(i).data(0, ROLE) == selected_id), None)
            self.tree.clearSelection()
            self.tree.setCurrentItem(selected)
            if selected is not None:
                selected.setSelected(True)
        finally:
            self.tree.blockSignals(False)
        self.resize_tree()

    def resize_tree(self, *args):
        rows = self.root.childCount() if self.root.isExpanded() else 0
        self.tree.setFixedHeight(35 + min(rows, 5) * 53)

    def choose_peer(self):
        item = self.tree.currentItem()
        if item is not None and item.isSelected() and item.data(0, ROLE):
            self.peer_selected.emit(self.connection_id, item.data(0, ROLE))
