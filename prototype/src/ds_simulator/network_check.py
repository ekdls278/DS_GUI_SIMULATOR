"""Packaging validation only: real loopback byte exchange in the frozen EXE."""
from contextlib import ExitStack
import json
from pathlib import Path
import select
import socket
import time

from PySide6.QtCore import QCoreApplication

from .domain import Step
from .network import NetworkTransport
from .preview_data import ConnectionPreview


def run_check(report_path):
    connections = []
    transport = NetworkTransport(lambda: connections)
    events, errors = [], []
    transport.received.connect(events.append)
    transport.error.connect(lambda cid, reason: errors.append(f'{cid}: {reason}'))
    results = []

    def wait(predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            QCoreApplication.processEvents()
            if errors:
                raise RuntimeError('; '.join(errors))
            if predicate():
                return
            time.sleep(.002)
        raise RuntimeError('Loopback network validation timed out')

    def receive(peer, expected):
        data = bytearray()
        def read():
            if select.select([peer], [], [], 0)[0]:
                data.extend(peer.recv(len(expected) - len(data)))
            return len(data) == len(expected)
        wait(read)
        if bytes(data) != expected:
            raise RuntimeError('Loopback bytes did not match')

    try:
        with ExitStack() as stack:
            def external(kind=socket.SOCK_STREAM):
                peer = stack.enter_context(socket.socket(socket.AF_INET, kind))
                peer.settimeout(1)
                return peer
            def open_profile(cid, mode, remote=''):
                profile = ConnectionPreview(cid, cid, mode, '127.0.0.1:0', remote)
                connections.append(profile); transport.open(profile)
            open_profile('SERVER', 'TCP Server')
            listener = transport.snapshots()[0]
            peers = [external(), external()]
            for peer in peers:
                peer.connect(('127.0.0.1', listener.local_port))
            wait(lambda: len(transport.snapshots()) == 3)
            selected = next(s for s in transport.snapshots() if s.remote_port == peers[1].getsockname()[1])
            transport.send(Step('raw', connection_id='SERVER', socket_id=selected.identifier, wire_data='00 AB FF'))
            receive(peers[1], b'\x00\xab\xff')
            if select.select([peers[0]], [], [], 0)[0]:
                raise RuntimeError('TCP server sent to an unselected peer')
            peers[1].sendall(b'\xfe\x00')
            wait(lambda: any(e['socket_id'] == selected.identifier and e['values']['hex'] == 'FE 00' for e in events))
            results.append('tcp-server-selected-client-tx-rx')

            server = external(); server.bind(('127.0.0.1', 0)); server.listen()
            open_profile('CLIENT', 'TCP Client', f'127.0.0.1:{server.getsockname()[1]}')
            wait(lambda: any(s.connection_id == 'CLIENT' and s.state == 'ESTABLISHED' for s in transport.snapshots()))
            peer, _ = server.accept(); stack.enter_context(peer)
            transport.send(Step('raw', connection_id='CLIENT', wire_format='utf8', wire_data='시험\r\n'))
            receive(peer, '시험\r\n'.encode())
            peer.sendall(b'\x10\x11')
            wait(lambda: any(e['connection_id'] == 'CLIENT' and e['values']['hex'] == '10 11' for e in events))
            results.append('tcp-client-tx-rx')

            peer = external(socket.SOCK_DGRAM); peer.bind(('127.0.0.1', 0))
            open_profile('UDP', 'UDP', f'127.0.0.1:{peer.getsockname()[1]}')
            local = next(s for s in transport.snapshots() if s.connection_id == 'UDP')
            transport.send(Step('raw', connection_id='UDP', wire_data='AA 00 BB'))
            wait(lambda: bool(select.select([peer], [], [], 0)[0]))
            if peer.recvfrom(10)[0] != b'\xaa\x00\xbb':
                raise RuntimeError('UDP bytes did not match')
            peer.sendto(b'\x00\xff', ('127.0.0.1', local.local_port))
            wait(lambda: any(e['connection_id'] == 'UDP' and e['values']['hex'] == '00 FF' for e in events))
            results.append('udp-datagram-tx-rx')
            transport.close_all()
            if transport.sessions:
                raise RuntimeError('Network sessions were not closed')
            results.append('socket-cleanup')
        report = {'result': 'passed', 'checks': results, 'transport': 'real-ipv4-loopback', 'errors': errors}
        code = 0
    except Exception as exc:
        report = {'result': 'failed', 'checks': results, 'error': str(exc)}
        code = 1
    finally:
        transport.close_all()
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return code
