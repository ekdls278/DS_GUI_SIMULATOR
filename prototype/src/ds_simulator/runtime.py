"""Switchable network/mock sender and cancellable Qt scenario runner."""

from copy import deepcopy
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from .domain import iter_actions, validate_message
from .preview_data import MESSAGES
from .icd import IcdMessage
from .network import NetworkTransport
from .wire import encode_raw


class MockTransport(QObject):
    sent = Signal(dict)
    label = 'MOCK'

    def __init__(self, connections, sockets, parent=None, catalog=None):
        super().__init__(parent)
        self.connections = connections
        self.sockets = sockets
        self.catalog = catalog or (lambda: MESSAGES)

    def resolve(self, connection_id, socket_id=""):
        connection = next((c for c in self.connections() if c.identifier == connection_id), None)
        if connection is None:
            raise ValueError(f"연결 프로파일을 찾을 수 없습니다: {connection_id}")
        candidates = [s for s in self.sockets() if s.connection_id == connection_id and s.role != "Listen" and s.state in ("ESTABLISHED", "BOUND")]
        if connection.mode == "TCP Server" and not socket_id:
            raise ValueError(f"{connection_id}: 접속 클라이언트를 선택하세요.")
        socket = next((s for s in candidates if s.identifier == socket_id), None) if socket_id else next(iter(candidates), None)
        if socket is None:
            raise ValueError(f"{connection_id}: 모의 연결 또는 선택 소켓이 해제되어 있습니다.")
        peer = socket.remote_endpoint if connection.mode == "TCP Server" else connection.remote_endpoint
        if not peer:
            raise ValueError(f"{connection_id}: 송신 목적지가 없습니다.")
        return socket, peer

    def send(self, step, source="수동"):
        if step.kind == 'raw':
            data = encode_raw(step.wire_format, step.wire_data)
            current, peer = self.resolve(step.connection_id, step.socket_id)
            event = NetworkTransport.event(current, peer, data, 'TX', source)
            event.update(mode='MOCK', status='SIMULATED')
            self.sent.emit(event)
            return event
        messages = self.catalog()
        values = validate_message(step.message, step.headers, step.values, messages)
        message = messages[step.message]
        socket, peer = self.resolve(step.connection_id, step.socket_id)
        event = {
            "time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "mode": "MOCK", "direction": "TX", "source": source,
            "connection_id": step.connection_id, "socket_id": socket.identifier,
            "peer": peer, "message": message.description if isinstance(message, IcdMessage) else step.message, "message_id": step.message, "headers": dict(step.headers),
            "values": values, "big_endian": step.big_endian,
        }
        if isinstance(message, IcdMessage):
            event['data_elements'] = [{'sequence': field.sequence, 'name': field.name, 'value': values[field.key]} for field in message.elements]
        self.sent.emit(event)
        return event


class TransportRouter(QObject):
    sent = Signal(dict)
    received = Signal(dict)

    def __init__(self, connections, sockets, parent=None, catalog=None, live=True):
        super().__init__(parent)
        self.live = live
        self.mock = MockTransport(connections, sockets, self, catalog)
        self.network = NetworkTransport(connections, self)
        self.mock.sent.connect(self.sent)
        self.network.sent.connect(self.sent)
        self.network.received.connect(self.received)

    @property
    def label(self):
        return 'LIVE' if self.live else 'MOCK'

    def resolve(self, connection_id, socket_id=''):
        return (self.network if self.live else self.mock).resolve(connection_id, socket_id)

    def validate_step(self, step):
        if self.live:
            self.network.validate_step(step)

    def send(self, step, source='수동'):
        return (self.network if self.live else self.mock).send(step, source)


class ScenarioRunner(QObject):
    changed = Signal(str)
    progress = Signal(str, int, int)
    finished = Signal(str)

    def __init__(self, transport, parent=None):
        super().__init__(parent)
        self.transport = transport
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.advance)
        self.running = False
        self.completed = 0
        self.total = 0
        self.pending = None

    def start(self, scenario):
        if self.running:
            raise ValueError("이미 시험이 실행 중입니다.")
        snapshot = deepcopy(scenario)
        total = snapshot.validate()
        if not total:
            raise ValueError("실행할 활동을 추가하세요.")

        def bind(steps):
            for step in steps:
                if step.kind == "repeat" and not step.children:
                    raise ValueError("빈 반복 블록에 활동을 추가하세요.")
                if step.kind in ("send", 'raw'):
                    if hasattr(self.transport, 'validate_step'):
                        self.transport.validate_step(step)
                    socket, _ = self.transport.resolve(step.connection_id, step.socket_id)
                    step.socket_id = socket.identifier
                bind(step.children)

        bind(snapshot.steps)
        self.actions = iter(iter_actions(snapshot.steps))
        self.completed, self.total = 0, total
        self.pending = None
        self.running = True
        self.changed.emit(f"{self.transport.label} 실행 중")
        self.timer.start(0)

    def advance(self):
        if not self.running:
            return
        if self.pending is not None:
            self.completed += 1
            self.pending = None
        step = next(self.actions, None)
        if step is None:
            self.finish("완료")
            return
        self.progress.emit(step.id, self.completed + 1, self.total)
        if step.kind == "wait":
            self.pending = step
            self.timer.start(step.milliseconds)
        else:
            try:
                self.transport.send(step, "시나리오")
            except ValueError as exc:
                self.finish(f"오류: {exc}")
                return
            self.completed += 1
            self.timer.start(25)

    def stop(self):
        if self.running:
            self.finish("중지")

    def finish(self, status):
        self.timer.stop()
        self.pending = None
        self.running = False
        self.changed.emit(f"{status} · {self.completed}/{self.total} 활동 완료")
        self.finished.emit(status)
