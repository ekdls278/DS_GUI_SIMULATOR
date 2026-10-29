"""Event-driven IPv4 TCP/UDP sockets; no blocking calls on the GUI thread."""
from datetime import datetime
from dataclasses import replace
import ipaddress

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket, QUdpSocket, QNetworkProxy

from .preview_data import SocketPreview
from .wire import encode_raw


def endpoint(value, *, local=False):
    try:
        host, port = value.rsplit(':', 1)
        ipaddress.IPv4Address(host)
        if not port.isdecimal() or not (0 if local else 1) <= int(port) <= 65535:
            raise ValueError()
        return QHostAddress(host), int(port)
    except (ValueError, AttributeError):
        raise ValueError('IPv4 주소와 포트를 확인하세요. 예: 127.0.0.1:5000') from None


class NetworkTransport(QObject):
    changed = Signal()
    sent = Signal(dict)
    received = Signal(dict)
    error = Signal(str, str)
    label = 'LIVE'

    def __init__(self, connections, parent=None):
        super().__init__(parent)
        self.connections = connections
        self.sessions = {}  # socket_id -> (connection_id, role, Qt socket/server)
        self.sequence = 0
        self.last_endpoints = {}

    def snapshots(self):
        result = []
        for sid, (cid, role, sock) in self.sessions.items():
            state = 'LISTENING' if role == 'Listen' else ('BOUND' if role == 'UDP' else
                    ('ESTABLISHED' if sock.state() == QAbstractSocket.SocketState.ConnectedState else 'CONNECTING'))
            snapshot = SocketPreview(sid, cid, role, state, sock.serverAddress().toString() if role == 'Listen' else sock.localAddress().toString(),
                                        sock.serverPort() if role == 'Listen' else sock.localPort(),
                                        sock.peerAddress().toString() if role in ('Client', 'Accepted') and state == 'ESTABLISHED' else '',
                                        sock.peerPort() if role in ('Client', 'Accepted') and state == 'ESTABLISHED' else None)
            if state == 'CONNECTING' and sid in self.last_endpoints:
                snapshot = replace(self.last_endpoints[sid], state=state)
            else:
                self.last_endpoints[sid] = snapshot
            result.append(snapshot)
        return result

    def register(self, cid, role, sock):
        self.sequence += 1
        sid = f'NET-{self.sequence:06}'
        self.sessions[sid] = (cid, role, sock)
        if role != 'Listen':
            sock.readyRead.connect(lambda: self.read(sid))
            sock.errorOccurred.connect(lambda code: self.socket_error(sid, code))
        if role in ('Client', 'Accepted'):
            sock.setReadBufferSize(1024 * 1024)
            sock.disconnected.connect(lambda: self.disconnected(sid))
        return sid

    def open(self, connection):
        cid = connection.identifier
        if any(c == cid for c, _, _ in self.sessions.values()):
            raise ValueError('이미 연결 중이거나 열린 프로파일입니다.')
        local, port = endpoint(connection.local_endpoint, local=True)
        if connection.mode not in ('TCP Server', 'TCP Client', 'UDP'):
            raise ValueError('TCP Server, TCP Client, UDP를 지원합니다.')
        remote = endpoint(connection.remote_endpoint) if connection.mode != 'TCP Server' else None
        sock = QTcpServer(self) if connection.mode == 'TCP Server' else (QUdpSocket(self) if connection.mode == 'UDP' else QTcpSocket(self))
        # Device addresses are direct endpoints; an OS/application HTTP proxy cannot bind them.
        sock.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        if connection.mode == 'TCP Server':
            if not sock.listen(local, port):
                message = sock.errorString(); sock.deleteLater()
                raise ValueError(f'{cid}: 서버 대기 실패 · {message}')
            sid = self.register(cid, 'Listen', sock)
            sock.newConnection.connect(lambda: self.accept(sid))
            sock.acceptError.connect(lambda _: self.error.emit(cid, sock.errorString()))
        else:
            # Do not share/reuse UDP binds: a second profile must not steal traffic.
            if not sock.bind(local, port, QAbstractSocket.BindFlag.DontShareAddress):
                message = sock.errorString(); sock.deleteLater()
                raise ValueError(f'{cid}: 로컬 바인딩 실패 · {message}')
            sid = self.register(cid, 'UDP' if connection.mode == 'UDP' else 'Client', sock)
            if connection.mode == 'TCP Client':
                sock.connected.connect(self.changed)
                timer = QTimer(sock); timer.setSingleShot(True)
                timer.timeout.connect(lambda: self.connect_timeout(sid))
                sock.connected.connect(timer.stop)
                timer.start(10000)
                sock.connectToHost(*remote)
        self.changed.emit()
        return sid

    def connect_timeout(self, sid):
        entry = self.sessions.get(sid)
        if entry and entry[2].state() != QAbstractSocket.SocketState.ConnectedState:
            self.error.emit(entry[0], 'TCP 연결 시간 초과 (10초)')
            self.remove(sid)

    def accept(self, sid):
        entry = self.sessions.get(sid)
        if not entry:
            return
        cid, _, server = entry
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            if sum(c == cid and role == 'Accepted' for c, role, _ in self.sessions.values()) >= 64:
                sock.abort(); sock.deleteLater()
                self.error.emit(cid, '서버별 접속 클라이언트는 최대 64개입니다.')
                continue
            peer_id = self.register(cid, 'Accepted', sock)
            self.changed.emit()
            if sock.bytesAvailable():
                self.read(peer_id)

    def remove(self, sid):
        entry = self.sessions.pop(sid, None)
        if not entry:
            return
        sock = entry[2]
        self.last_endpoints.pop(sid, None)
        if entry[1] == 'Listen':
            sock.close()
        else:
            sock.abort()
        sock.deleteLater()
        self.changed.emit()

    def close_connection(self, cid):
        for sid in [s for s, (c, _, _) in self.sessions.items() if c == cid]:
            self.remove(sid)

    def close_all(self):
        for sid in list(self.sessions):
            self.remove(sid)

    def socket_error(self, sid, code):
        entry = self.sessions.get(sid)
        if entry and code != QAbstractSocket.SocketError.RemoteHostClosedError:
            self.error.emit(entry[0], entry[2].errorString())
            self.remove(sid)

    def disconnected(self, sid):
        if sid in self.sessions:
            self.read(sid)
            self.remove(sid)

    def resolve(self, connection_id, socket_id=''):
        connection = next((c for c in self.connections() if c.identifier == connection_id), None)
        if connection is None:
            raise ValueError('연결 프로파일을 찾을 수 없습니다.')
        candidates = [s for s in self.snapshots() if s.connection_id == connection_id and s.state in ('ESTABLISHED', 'BOUND')]
        if connection.mode == 'TCP Server' and not socket_id:
            raise ValueError('서버의 접속 클라이언트를 선택하세요.')
        current = next((s for s in candidates if s.identifier == socket_id), None) if socket_id else next(iter(candidates), None)
        if current is None:
            raise ValueError('실제 연결이 없거나 선택한 소켓이 해제됐습니다.')
        peer = current.remote_endpoint if connection.mode != 'UDP' else connection.remote_endpoint
        return current, peer

    def validate_step(self, step):
        if step.kind != 'raw':
            raise ValueError('ICD 바이트 규격이 미정입니다. 실제 통신은 HEX 또는 UTF-8 직접 송신을 사용하세요.')
        data = encode_raw(step.wire_format, step.wire_data)
        current, _ = self.resolve(step.connection_id, step.socket_id)
        if current.role == 'UDP' and len(data) > 65507:
            raise ValueError('IPv4 UDP 데이터는 최대 65,507바이트입니다.')
        return data

    def send(self, step, source='수동'):
        data = self.validate_step(step)
        current, peer = self.resolve(step.connection_id, step.socket_id)
        sock = self.sessions[current.identifier][2]
        if current.role == 'UDP':
            written = sock.writeDatagram(data, *endpoint(peer))
        else:
            if sock.bytesToWrite() + len(data) > 1024 * 1024:
                raise ValueError('송신 대기 버퍼가 1MB를 초과합니다. 잠시 후 다시 송신하세요.')
            written = sock.write(data)
        if written != len(data):
            raise ValueError(f'송신 실패 · {sock.errorString()}')
        event = self.event(current, peer, data, 'TX', source)
        event['status'] = 'OS_ACCEPTED' if current.role == 'UDP' else 'QUEUED'
        self.sent.emit(event)
        return event

    @staticmethod
    def event(current, peer, data, direction, source):
        return {'time': datetime.now().astimezone().isoformat(timespec='milliseconds'), 'mode': 'LIVE',
                'direction': direction, 'source': source, 'connection_id': current.connection_id,
                'socket_id': current.identifier, 'local': current.local_endpoint, 'peer': peer,
                'message': 'UDP 데이터그램' if current.role == 'UDP' else 'TCP 바이트 스트림',
                'message_id': 'RAW', 'headers': {'src': '', 'dst': '', 'cmd': ''},
                'values': {'bytes': len(data), 'hex': data.hex(' ').upper(), 'utf8': data.decode('utf-8', errors='replace')},
                'big_endian': False, 'status': 'RECEIVED' if direction == 'RX' else 'QUEUED'}

    def read(self, sid):
        entry = self.sessions.get(sid)
        if not entry or entry[1] == 'Listen':
            return
        sock = entry[2]
        current = next(s for s in self.snapshots() if s.identifier == sid)
        # Yield regularly to paint and cancel; TCP chunks are not ICD message frames.
        for _ in range(16):
            if current.role == 'UDP':
                if not sock.hasPendingDatagrams():
                    return
                data, host, port = sock.readDatagram(65536)
                data = bytes(data)
                peer = f'{host.toString()}:{port}'
            else:
                if not sock.bytesAvailable():
                    return
                data = bytes(sock.read(65536)); peer = current.remote_endpoint
            self.received.emit(self.event(current, peer, data, 'RX', '실제 수신'))
        if sid in self.sessions and (sock.hasPendingDatagrams() if current.role == 'UDP' else sock.bytesAvailable()):
            QTimer.singleShot(0, lambda: self.read(sid))
