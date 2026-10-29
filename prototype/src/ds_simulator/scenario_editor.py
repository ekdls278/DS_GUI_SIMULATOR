"""Native Qt block editor, backed by UI-independent scenario models."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QScrollArea, QSpinBox, QStyledItemDelegate, QStyle, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit,
)

from .domain import Scenario, Step, load_scenario, save_json
from .preview_data import MESSAGES
from .icd import IcdMessage
from .icd_widgets import make_field_input, connect_input
from .runtime import ScenarioRunner
from .widgets import Card, button, chip, label, row

ROLE = Qt.ItemDataRole.UserRole
COLORS = {"send": "#4a71dd", "raw": '#347c93', "wait": "#5c9fba", "repeat": "#d99c30"}


class BlockTree(QTreeWidget):
    moved = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        if event.isAccepted():
            self.moved.emit()


class BlockDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(250, 83)

    def paint(self, painter, option, index):
        step = index.data(ROLE)
        if not step:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 5, -8, -5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS[step.kind]))
        painter.drawRoundedRect(rect, 8, 8)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QColor("#b8cdff"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        painter.setPen(QColor("white"))
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        title, _, subtitle = index.data().partition("\n")
        painter.drawText(rect.adjusted(16, 9, -10, -30), Qt.AlignmentFlag.AlignVCenter, title)
        font.setBold(False)
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        painter.drawText(rect.adjusted(16, 35, -10, -5), Qt.AlignmentFlag.AlignVCenter, subtitle)
        painter.restore()


class ScenarioEditor(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.document = Scenario('새 통신 시험') if window.transport.live else Scenario.example()
        self.path = None
        self.dirty = False
        self.loading = False
        self.runner = ScenarioRunner(window.transport, self)
        self.runner.changed.connect(self.on_status)
        self.runner.progress.connect(self.on_progress)
        self.runner.finished.connect(self.on_finished)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        toolbar = Card()
        self.mode_chip = chip(window.transport.label)
        actions = row(self.mode_chip)
        self.name_input = QLineEdit(self.document.name)
        self.name_input.setMaxLength(200)
        self.name_input.textEdited.connect(self.mark_dirty)
        actions.addWidget(self.name_input, 1)
        self.new_button = button("새 시험")
        self.load_button = button("불러오기")
        self.save_button = button("저장")
        self.run_button = button("모의 실행", primary=True, icon_name="arrow")
        self.stop_button = button("중지")
        self.stop_button.setEnabled(False)
        for control in (self.new_button, self.load_button, self.save_button, self.run_button, self.stop_button):
            actions.addWidget(control)
        self.new_button.clicked.connect(self.new_document)
        self.load_button.clicked.connect(self.open_document)
        self.save_button.clicked.connect(self.save_document)
        self.run_button.clicked.connect(self.run)
        self.stop_button.clicked.connect(self.runner.stop)
        toolbar.body.addLayout(actions)
        self.file_label = label("저장하지 않은 시험", "caption")
        toolbar.body.addWidget(self.file_label)
        outer.addWidget(toolbar)
        self.edit_area = QWidget()
        panels = QHBoxLayout(self.edit_area)
        panels.setContentsMargins(0, 0, 0, 0)
        palette = Card("블록 목록", "추가")
        palette.setMinimumWidth(205)
        search = QLineEdit()
        search.setPlaceholderText("블록 검색")
        self.palette_search = search
        palette.body.addWidget(search)
        self.palette = QListWidget()
        self.palette.setObjectName("messageCatalog")
        self.rebuild_palette()
        search.textChanged.connect(self.filter_palette)
        self.palette.itemDoubleClicked.connect(self.add_selected)
        palette.body.addWidget(self.palette, 1)
        add = button("선택 블록 추가", primary=True, icon_name="plus")
        add.clicked.connect(self.add_selected)
        palette.body.addWidget(add)
        note = label("더블클릭 또는 추가 버튼\n반복을 선택하면 내부에 추가됩니다.", "caption")
        note.setWordWrap(True)
        palette.body.addWidget(note)
        panels.addWidget(palette, 22)
        canvas = Card("블록 조립 영역", "드래그로 이동")
        controls = QHBoxLayout()
        for title, method in (("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1)), ("반복 안으로", self.indent), ("반복 밖으로", self.outdent), ("삭제", self.delete_selected)):
            control = button(title)
            control.clicked.connect(method)
            controls.addWidget(control)
        canvas.body.addLayout(controls)
        canvas.body.addWidget(label("▶  시험 시작", "heading", color="#239d77"))
        self.tree = BlockTree()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumHeight(380)
        self.tree.setIndentation(25)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setItemDelegate(BlockDelegate(self.tree))
        self.tree.setStyleSheet("QTreeWidget { background: #f8faff; border: 0; outline: 0; } QTreeWidget::item { border: 0; } QTreeWidget::branch:selected { background: #e8efff; }")
        self.tree.itemSelectionChanged.connect(self.show_properties)
        self.tree.moved.connect(self.mark_dirty)
        canvas.body.addWidget(self.tree, 1)
        canvas.body.addWidget(label("■  시험 종료", "heading", color="#77869c"))
        self.selection_note = label("블록을 선택해 오른쪽에서 설정하세요.", "caption")
        self.selection_note.setWordWrap(True)
        canvas.body.addWidget(self.selection_note)
        panels.addWidget(canvas, 46)
        inspector = Card("블록 설정")
        inspector.setMinimumWidth(285)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.properties = QWidget()
        self.properties.setStyleSheet("background: white;")
        scroll.setStyleSheet("QScrollArea { background: white; }")
        self.form = QFormLayout(self.properties)
        self.form.setContentsMargins(0, 0, 6, 0)
        self.form.setVerticalSpacing(12)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(self.properties)
        inspector.body.addWidget(scroll, 1)
        hint = label("실제 통신은 HEX·UTF-8 직접 송신 블록을 사용합니다.\n서버는 접속 클라이언트를 선택하세요.\n완료는 장치의 수신·정상 동작 판정이 아닙니다.", "caption")
        hint.setWordWrap(True)
        inspector.body.addWidget(hint)
        panels.addWidget(inspector, 32)
        outer.addWidget(self.edit_area, 1)
        self.status = label("준비 · 송신 대상의 모의 연결 후 실행하세요.", "muted")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.delete_shortcut = QShortcut(QKeySequence("Delete"), self.tree)
        self.delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.delete_shortcut.activated.connect(self.delete_selected)
        self.populate()

    def rebuild_palette(self):
        self.palette.clear()
        items = [("↻  횟수 반복", "repeat", ""), ("◷  시간 대기", "wait", "")]
        items.extend((f"{message.cmd}\n{message.description}", "send", key) for key, message in self.window.messages.items())
        items.append(('직접 송신\nHEX / UTF-8 바이트', 'raw', ''))
        for title, kind, key in items:
            item = QListWidgetItem(title)
            item.setData(ROLE, (kind, key))
            self.palette.addItem(item)
        self.palette.setCurrentRow(len(items) - 1 if self.window.transport.live else 2)
        self.filter_palette(self.palette_search.text())

    def reset_for_catalog(self):
        self.document = Scenario("새 시험", catalog=self.window.scenario_catalog())
        self.path = None
        self.palette_search.clear()
        self.rebuild_palette()
        self.populate()
        self.dirty = False
        self.file_label.setText("저장하지 않은 시험")
        self.status.setText("새 시험을 구성하세요. 실제 통신은 직접 송신 블록을 사용합니다.")

    def refresh_mode(self):
        self.mode_chip.setText(self.window.transport.label)
        self.run_button.setText('실제 실행' if self.window.transport.live else '모의 실행')
        self.status.setText(f'{self.window.transport.label} · 연결과 송신 데이터를 확인하세요.')

    def mark_dirty(self, *args):
        if self.loading:
            return
        self.dirty = True
        self.file_label.setText(f"● 변경됨 · {self.path or '저장하지 않은 시험'}")

    def filter_palette(self, term):
        for index in range(self.palette.count()):
            item = self.palette.item(index)
            item.setHidden(term.casefold() not in item.text().casefold())

    def describe(self, step):
        if step.kind == "repeat":
            return f"↻  {step.count}회 반복\n내부 활동을 순서대로 반복"
        if step.kind == "wait":
            return f"◷  시간 대기\n{step.milliseconds:,} ms"
        if step.kind == 'raw':
            return f'직접 송신 · {step.wire_format.upper()}\n{step.connection_id} | {step.wire_data[:24]!r}'
        message = self.window.messages[step.message]
        return f"ICD 메시지 송신 · {message.description}\nopcode {message.cmd}  |  {step.connection_id}"

    def make_item(self, step, parent):
        item = QTreeWidgetItem(parent, [self.describe(step)])
        item.setData(0, ROLE, step)
        flags = item.flags()
        if step.kind != "repeat":
            flags &= ~Qt.ItemFlag.ItemIsDropEnabled
        item.setFlags(flags)
        for child in step.children:
            self.make_item(child, item)
        item.setExpanded(True)
        return item

    def populate(self):
        self.loading = True
        blocked = self.tree.blockSignals(True)
        try:
            self.tree.clear()
            for step in self.document.steps:
                self.make_item(step, self.tree)
            self.name_input.setText(self.document.name)
            if self.tree.topLevelItemCount():
                self.tree.setCurrentItem(self.tree.topLevelItem(0))
        finally:
            self.tree.blockSignals(blocked)
            self.loading = False
        self.show_properties()

    def collect(self):
        def children(parent):
            result = []
            for index in range(parent.childCount()):
                item = parent.child(index)
                step = item.data(0, ROLE)
                step.children = children(item)
                result.append(step)
            return result
        self.document.name = self.name_input.text().strip()
        self.document.steps = children(self.tree.invisibleRootItem())
        self.document.catalog = self.window.scenario_catalog()
        return self.document

    def add_selected(self, *args):
        if self.runner.running:
            return
        item = self.palette.currentItem()
        if not item or item.isHidden():
            return
        kind, name = item.data(ROLE)
        step = Step.send(name, self.window.messages) if kind == "send" else Step(kind)
        if kind in ("send", 'raw'):
            connection = self.window.selected_connection()
            step.connection_id = connection.identifier
            current = self.window.current_socket()
            step.socket_id = current.identifier if current and connection.mode == "TCP Server" else ""
        selected = self.tree.currentItem()
        if selected and selected.data(0, ROLE).kind == "repeat":
            new_item = self.make_item(step, selected)
            selected.setExpanded(True)
        else:
            parent = selected.parent() if selected else None
            container = parent or self.tree.invisibleRootItem()
            position = container.indexOfChild(selected) + 1 if selected else container.childCount()
            new_item = self.make_item(step, container)
            container.takeChild(container.indexOfChild(new_item))
            container.insertChild(position, new_item)
        self.tree.setCurrentItem(new_item)
        self.mark_dirty()

    def delete_selected(self):
        item = self.tree.currentItem()
        if not item or self.runner.running:
            return
        if item.childCount() and QMessageBox.question(self, "반복 삭제", "반복 안의 활동도 함께 삭제할까요?") != QMessageBox.StandardButton.Yes:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        parent.takeChild(parent.indexOfChild(item))
        self.show_properties()
        self.mark_dirty()

    def move(self, delta):
        item = self.tree.currentItem()
        if not item or self.runner.running:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(item)
        if not 0 <= index + delta < parent.childCount():
            return
        parent.takeChild(index)
        parent.insertChild(index + delta, item)
        self.tree.setCurrentItem(item)
        self.mark_dirty()

    def indent(self):
        item = self.tree.currentItem()
        if not item or self.runner.running:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(item)
        previous = parent.child(index - 1) if index > 0 else None
        if previous and previous.data(0, ROLE).kind == "repeat":
            parent.takeChild(index)
            previous.addChild(item)
            previous.setExpanded(True)
            self.tree.setCurrentItem(item)
            self.mark_dirty()

    def outdent(self):
        item = self.tree.currentItem()
        if not item or not item.parent() or self.runner.running:
            return
        parent = item.parent()
        grandparent = parent.parent() or self.tree.invisibleRootItem()
        parent.takeChild(parent.indexOfChild(item))
        grandparent.insertChild(grandparent.indexOfChild(parent) + 1, item)
        self.tree.setCurrentItem(item)
        self.mark_dirty()

    def set_property(self, step, key, value):
        setattr(step, key, value)
        item = self.tree.currentItem()
        if item:
            item.setText(0, self.describe(step))
        self.mark_dirty()

    def show_properties(self):
        if self.loading:
            return
        while self.form.rowCount():
            self.form.removeRow(0)
        item = self.tree.currentItem()
        if item is None:
            self.form.addRow(label("블록을 선택하세요.", "muted"))
            return
        step = item.data(0, ROLE)
        self.selection_note.setText(f"선택: {self.describe(step).replace(chr(10), ' · ')}")
        if step.kind in ("repeat", "wait"):
            spin = QSpinBox()
            spin.setRange(1 if step.kind == "repeat" else 0, 1000 if step.kind == "repeat" else 600000)
            spin.setValue(step.count if step.kind == "repeat" else step.milliseconds)
            spin.setSuffix(" 회" if step.kind == "repeat" else " ms")
            key = "count" if step.kind == "repeat" else "milliseconds"
            spin.valueChanged.connect(lambda value: self.set_property(step, key, value))
            self.form.addRow("반복 횟수" if step.kind == "repeat" else "대기 시간", spin)
            return
        message = None if step.kind == 'raw' else self.window.messages[step.message]
        self.form.addRow(label('바이트 직접 송신' if message is None else message.description, "heading"))
        if message is not None:
            self.form.addRow(label(f"opcode {message.cmd}", "muted"))
        target = QComboBox()
        target.setMinimumContentsLength(12)
        target.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for connection in self.window.connections:
            if connection.mode == "TCP Server":
                peers = self.window.server_peers(connection)
                target.addItem(f"{connection.title} · 클라이언트 미선택", (connection.identifier, ""))
                for peer in peers:
                    target.addItem(f"{connection.identifier} · {peer.identifier} · {peer.remote_endpoint}", (connection.identifier, peer.identifier))
            else:
                target.addItem(connection.title, (connection.identifier, ""))
        selected = next((index for index in range(target.count()) if tuple(target.itemData(index)) == (step.connection_id, step.socket_id)), -1)
        if selected < 0:
            target.addItem(f"{step.connection_id} · {step.socket_id} (재선택 필요)", (step.connection_id, step.socket_id))
            selected = target.count() - 1
        target.setCurrentIndex(selected)
        def change_target(index):
            step.connection_id, step.socket_id = target.itemData(index)
            self.set_property(step, "connection_id", step.connection_id)
            QTimer.singleShot(0, self.show_properties)
        target.currentIndexChanged.connect(change_target)
        self.form.addRow("송신 대상", target)
        try:
            socket, peer = self.window.transport.resolve(step.connection_id, step.socket_id)
            endpoint = label(f"{self.window.transport.label} · {socket.identifier}\nLocal {socket.local_endpoint}\n대상 {peer}", "caption")
        except ValueError:
            endpoint = label("미연결 / 대상 미선택\nICD 송수신 화면에서 연결하세요.", "caption")
        endpoint.setWordWrap(True)
        self.form.addRow(endpoint)
        if step.kind == 'raw':
            kind = QComboBox()
            kind.addItem('HEX', 'hex'); kind.addItem('UTF-8', 'utf8')
            kind.setCurrentIndex(0 if step.wire_format == 'hex' else 1)
            kind.currentIndexChanged.connect(lambda _: self.set_property(step, 'wire_format', kind.currentData()))
            data = QPlainTextEdit(step.wire_data)
            data.setMaximumHeight(180)
            data.textChanged.connect(lambda: self.set_property(step, 'wire_data', data.toPlainText()))
            self.form.addRow('송신 형식', kind)
            self.form.addRow('송신 내용', data)
            note = label('입력한 바이트 그대로 송신합니다.\nHEX 예: AA BB 0D 0A\nUTF-8은 줄바꿈도 그대로 포함합니다.', 'caption')
            note.setWordWrap(True)
            self.form.addRow(note)
            return
        if not isinstance(message, IcdMessage):
            for key in ("src", "dst", "cmd"):
                edit = QLineEdit(step.headers[key])
                edit.textEdited.connect(lambda value, k=key: (step.headers.__setitem__(k, value), self.mark_dirty()))
                self.form.addRow(key.upper(), edit)
        for key, data_type, _, unit, description in message.fields:
            edit = make_field_input(message, key, step.values[key])
            edit.setToolTip(f"{data_type} · {unit}")
            connect_input(edit, lambda value, k=key: (step.values.__setitem__(k, value), self.mark_dirty()), user_only=True)
            self.form.addRow(f"{description}\n{unit}" if unit != "—" else description, edit)
        endian = QCheckBox("빅엔디안 (설정 기록용)")
        endian.setChecked(step.big_endian)
        endian.toggled.connect(lambda value: self.set_property(step, "big_endian", value))
        self.form.addRow(endian)

    def confirm_discard(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "저장되지 않은 시험", "변경한 시나리오를 저장할까요?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_document()
        return answer == QMessageBox.StandardButton.Discard

    def new_document(self):
        if self.runner.running or not self.confirm_discard():
            return
        self.document, self.path = Scenario("새 시험", catalog=self.window.scenario_catalog()), None
        self.populate()
        self.dirty = False
        self.file_label.setText("저장하지 않은 시험")

    def save_to(self, path):
        save_json(path, self.collect().to_dict())
        self.path = Path(path)
        self.dirty = False
        self.file_label.setText(str(self.path))

    def load_from(self, path):
        document = load_scenario(path)
        self.window.apply_catalog(document.catalog if document.catalog is not None else MESSAGES, "시나리오 내장 ICD" if document.catalog is not None else "기본 예시 ICD", reset_scenario=False)
        self.document, self.path = document, Path(path)
        self.palette_search.clear()
        self.rebuild_palette()
        self.populate()
        self.dirty = False
        self.file_label.setText(str(self.path))
        self.status.setText("불러오기 완료 · 이 파일은 시나리오만 저장합니다. 연결 프로파일과 서버 접속 대상을 확인하세요.")

    def save_document(self):
        path = self.path
        if path is None:
            filename, _ = QFileDialog.getSaveFileName(self, "시나리오 저장", "scenario.json", "시나리오 JSON (*.json)")
            if not filename:
                return False
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".json")
        try:
            self.save_to(path)
            self.status.setText("시나리오 저장 완료")
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return False

    def open_document(self):
        if self.runner.running or not self.confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "시나리오 불러오기", "", "시나리오 JSON (*.json)")
        if filename:
            try:
                self.load_from(filename)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "불러오기 실패", str(exc))

    def run(self):
        try:
            self.runner.start(self.collect())
        except ValueError as exc:
            self.status.setText(f"실행할 수 없습니다: {exc}")
            return
        self.set_running(True)

    def set_running(self, running):
        for widget in (self.edit_area, self.name_input, self.new_button, self.load_button, self.save_button, self.run_button):
            widget.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def on_status(self, message):
        self.status.setText(f"{self.window.transport.label} · {message}")

    def on_progress(self, identifier, current, total):
        def find(parent):
            for index in range(parent.childCount()):
                item = parent.child(index)
                if item.data(0, ROLE).id == identifier:
                    return item
                result = find(item)
                if result:
                    return result
            return None
        item = find(self.tree.invisibleRootItem())
        if item:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)
        self.status.setText(f"{self.window.transport.label} · 실행 중 {current}/{total} · {item.text(0).splitlines()[0] if item else ''}")

    def on_finished(self, status):
        self.set_running(False)
        if status == "완료":
            self.status.setText(f"{self.window.transport.label} · 완료 · {self.runner.completed}개 활동 수행 (상대 수신·실제 장비 판정 아님)")
