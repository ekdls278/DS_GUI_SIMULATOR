"""Real loopback sockets against Python's socket module; no private ICD files."""
import json
from pathlib import Path
import select
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QSpinBox, QPlainTextEdit
from PySide6.QtCore import QTimer

from ds_simulator.app import SimulatorWindow
from ds_simulator.domain import Scenario, Step, load_scenario, save_json
from ds_simulator.network import NetworkTransport
from ds_simulator.preview_data import ConnectionPreview
from ds_simulator.runtime import ScenarioRunner
from ds_simulator.wire import encode_raw

APP = QApplication.instance() or QApplication([])


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return
        time.sleep(.002)
    raise AssertionError('Timed out waiting for loopback network event')


def receive(sock, length):
    data = bytearray()
    def read():
        if select.select([sock], [], [], 0)[0]:
            data.extend(sock.recv(length - len(data)))
        return len(data) == length
    wait_for(read)
    return bytes(data)


class WireTests(unittest.TestCase):
    def test_explicit_hex_utf8_and_no_automatic_headers_or_line_endings(self):
        self.assertEqual(encode_raw('hex', '0xAA bb\n00\t01'), b'\xaa\xbb\x00\x01')
        self.assertEqual(encode_raw('hex', 'AABB0001'), b'\xaa\xbb\x00\x01')
        self.assertEqual(encode_raw('utf8', '시험\r\n'), '시험\r\n'.encode())
        for kind, text in [('hex', 'A B'), ('hex', '0x'), ('hex', 'GG'), ('hex', ''), ('utf8', ''), ('other', 'AA'), ('hex', 'AA' * 65537)]:
            with self.subTest(kind=kind, text=text[:20]), self.assertRaises(ValueError):
                encode_raw(kind, text)

    def test_raw_scenario_roundtrip_uses_version_three_and_preserves_bytes(self):
        scenario = Scenario('통신 시험', [Step('repeat', count=2, children=[Step('raw', wire_data='00 FF 0D 0A'), Step('wait', milliseconds=1)])])
        self.assertEqual(scenario.validate(), 4)
        payload = scenario.to_dict()
        self.assertEqual(payload['version'], 3)
        self.assertEqual(Scenario.from_dict(payload).to_dict(), payload)
        with self.assertRaises(ValueError):
            Scenario.from_dict({**payload, 'version': 1})


class NetworkTests(unittest.TestCase):
    def setUp(self):
        hook = patch('sys.excepthook'); exceptions = hook.start()
        self.addCleanup(hook.stop); self.addCleanup(exceptions.assert_not_called)
        self.connections = []
        self.transport = NetworkTransport(lambda: self.connections)
        self.events = []; self.errors = []
        self.transport.sent.connect(self.events.append)
        self.transport.received.connect(self.events.append)
        self.transport.error.connect(lambda cid, message: self.errors.append((cid, message)))
        self.external = []

    def tearDown(self):
        self.transport.close_all()
        for sock in self.external:
            sock.close()
        self.transport.deleteLater()
        APP.processEvents()

    def external_socket(self, kind=socket.SOCK_STREAM):
        sock = socket.socket(socket.AF_INET, kind); sock.settimeout(1)
        self.external.append(sock)
        return sock

    def open(self, mode, remote='', cid='TEST'):
        profile = ConnectionPreview(cid, cid, mode, '127.0.0.1:0', remote)
        self.connections.append(profile)
        return self.transport.open(profile)

    def test_tcp_server_accepts_two_clients_and_routes_exact_bytes_to_selected_peer(self):
        self.open('TCP Server')
        listener = self.transport.snapshots()[0]
        clients = [self.external_socket(), self.external_socket()]
        for client in clients:
            client.connect(('127.0.0.1', listener.local_port))
        wait_for(lambda: len(self.transport.snapshots()) == 3)
        peers = {p.remote_port: p for p in self.transport.snapshots() if p.role == 'Accepted'}
        selected = peers[clients[1].getsockname()[1]]
        event = self.transport.send(Step('raw', connection_id='TEST', socket_id=selected.identifier, wire_data='00 AB FF'))
        self.assertEqual(receive(clients[1], 3), b'\x00\xab\xff')
        self.assertFalse(select.select([clients[0]], [], [], 0)[0])
        self.assertEqual(event['status'], 'QUEUED')
        self.assertEqual(event['peer'], selected.remote_endpoint)
        clients[0].sendall(b'\x10\x00\xfe')
        wait_for(lambda: any(e['direction'] == 'RX' for e in self.events))
        received = next(e for e in self.events if e['direction'] == 'RX')
        self.assertEqual(received['values']['hex'], '10 00 FE')
        self.assertEqual(received['socket_id'], peers[clients[0].getsockname()[1]].identifier)
        with self.assertRaises(ValueError):
            self.transport.send(Step('raw', connection_id='TEST', socket_id=listener.identifier, wire_data='AA'))
        clients[1].close()
        wait_for(lambda: len(self.transport.snapshots()) == 2)
        with self.assertRaises(ValueError):
            self.transport.resolve('TEST', selected.identifier)

    def test_tcp_client_binds_actual_local_address_and_bidirectional_stream(self):
        server = self.external_socket(); server.bind(('127.0.0.1', 0)); server.listen()
        sid = self.open('TCP Client', f'127.0.0.1:{server.getsockname()[1]}')
        wait_for(lambda: self.transport.snapshots()[0].state == 'ESTABLISHED')
        peer, _ = server.accept(); self.external.append(peer)
        current = self.transport.snapshots()[0]
        self.assertEqual(current.local_ip, '127.0.0.1')
        self.assertGreater(current.local_port, 0)
        text = '실제 통신\r\n'
        self.transport.send(Step('raw', connection_id='TEST', wire_format='utf8', wire_data=text))
        self.assertEqual(receive(peer, len(text.encode())), text.encode())
        payload = bytes(range(256)) * 256
        peer.sendall(payload)
        wait_for(lambda: sum(e['values']['bytes'] for e in self.events if e['direction'] == 'RX') == len(payload))
        self.assertEqual(b''.join(bytes.fromhex(e['values']['hex']) for e in self.events if e['direction'] == 'RX'), payload)
        self.assertTrue(all(e['mode'] == 'LIVE' for e in self.events))
        peer.close()
        wait_for(lambda: not self.transport.snapshots())
        self.assertFalse(self.errors)
        with self.assertRaises(ValueError):
            self.transport.resolve('TEST', sid)

    def test_udp_preserves_datagrams_sender_and_binary_values_in_both_directions(self):
        peer = self.external_socket(socket.SOCK_DGRAM); peer.bind(('127.0.0.1', 0))
        self.open('UDP', f'127.0.0.1:{peer.getsockname()[1]}')
        local = self.transport.snapshots()[0]
        self.transport.send(Step('raw', connection_id='TEST', wire_data='AA 00 FF'))
        wait_for(lambda: bool(select.select([peer], [], [], 0)[0]))
        data, sender = peer.recvfrom(65536)
        self.assertEqual(data, b'\xaa\x00\xff')
        self.assertEqual(sender[1], local.local_port)
        for data in (b'\x00\x01', b'\xff\x10\x20', b''):
            peer.sendto(data, ('127.0.0.1', local.local_port))
        wait_for(lambda: len([e for e in self.events if e['direction'] == 'RX']) == 3)
        rx = [e for e in self.events if e['direction'] == 'RX']
        self.assertEqual([e['values']['hex'] for e in rx], ['00 01', 'FF 10 20', ''])
        self.assertTrue(all(e['peer'] == f'127.0.0.1:{peer.getsockname()[1]}' for e in rx))
        self.assertEqual(self.events[0]['status'], 'OS_ACCEPTED')
        with self.assertRaisesRegex(ValueError, '65,507'):
            self.transport.send(Step('raw', connection_id='TEST', wire_data='AA' * 65508))

    def test_bind_conflict_invalid_profile_and_connection_refusal_do_not_fabricate_sessions(self):
        peer = self.external_socket(socket.SOCK_DGRAM); peer.bind(('127.0.0.1', 0))
        profile = ConnectionPreview('BUSY', 'busy', 'UDP', f'127.0.0.1:{peer.getsockname()[1]}', '127.0.0.1:9')
        with self.assertRaises(ValueError):
            self.transport.open(profile)
        with self.assertRaises(ValueError):
            self.transport.open(ConnectionPreview('BAD', 'bad', 'TCP Client', 'bad', '127.0.0.1:9'))
        self.assertEqual(self.transport.snapshots(), [])
        closed = self.external_socket(); closed.bind(('127.0.0.1', 0))
        port = closed.getsockname()[1]  # Reserve a non-listening port until the check finishes.
        self.open('TCP Client', f'127.0.0.1:{port}')
        wait_for(lambda: bool(self.errors))
        self.assertEqual(self.transport.snapshots(), [])

    def test_repeated_raw_scenario_reaches_real_udp_peer_and_stop_cancels_future_sends(self):
        peer = self.external_socket(socket.SOCK_DGRAM); peer.bind(('127.0.0.1', 0))
        self.open('UDP', f'127.0.0.1:{peer.getsockname()[1]}')
        runner = ScenarioRunner(self.transport)
        self.addCleanup(runner.stop)
        scenario = Scenario('반복', [Step('repeat', count=3, children=[Step('raw', connection_id='TEST', wire_data='AB CD'), Step('wait', milliseconds=1)])])
        runner.start(scenario)
        wait_for(lambda: not runner.running)
        self.assertEqual(runner.completed, 6)
        self.assertEqual([peer.recvfrom(10)[0] for _ in range(3)], [b'\xab\xcd'] * 3)
        runner.start(Scenario('중지', [Step('wait', milliseconds=100), Step('raw', connection_id='TEST', wire_data='FF')]))
        APP.processEvents(); runner.stop()
        deadline = time.monotonic() + .15
        while time.monotonic() < deadline:
            APP.processEvents(); time.sleep(.002)
        self.assertFalse(select.select([peer], [], [], 0)[0])

    def test_real_scenario_rejects_unencoded_icd_before_any_raw_data_is_sent(self):
        peer = self.external_socket(socket.SOCK_DGRAM); peer.bind(('127.0.0.1', 0))
        self.open('UDP', f'127.0.0.1:{peer.getsockname()[1]}')
        runner = ScenarioRunner(self.transport)
        icd = Step.send(); icd.connection_id = 'TEST'
        with self.assertRaisesRegex(ValueError, 'ICD'):
            runner.start(Scenario('잘못된 시험', [Step('raw', connection_id='TEST', wire_data='AA'), icd]))
        self.assertFalse(runner.running)
        self.assertEqual(self.events, [])
        self.assertFalse(select.select([peer], [], [], 0)[0])

    def test_reconnect_does_not_reuse_old_socket_target(self):
        peer = self.external_socket(socket.SOCK_DGRAM); peer.bind(('127.0.0.1', 0))
        old = self.open('UDP', f'127.0.0.1:{peer.getsockname()[1]}')
        self.transport.close_connection('TEST')
        new = self.transport.open(self.connections[0])
        self.assertNotEqual(new, old)
        with self.assertRaises(ValueError):
            self.transport.send(Step('raw', connection_id='TEST', socket_id=old, wire_data='AA'))
        self.assertFalse(select.select([peer], [], [], 0)[0])


class LiveGuiTests(unittest.TestCase):
    def setUp(self):
        hook = patch('sys.excepthook'); exceptions = hook.start()
        self.addCleanup(hook.stop); self.addCleanup(exceptions.assert_not_called)
        self.window = SimulatorWindow()
        self.window.show(); APP.processEvents()

    def tearDown(self):
        self.window.scenario_editor.dirty = False
        self.window.close(); self.window.deleteLater(); APP.processEvents()

    def test_default_is_disconnected_live_and_real_raw_send_and_receive_reach_log(self):
        window = self.window
        self.assertTrue(window.transport.live)
        self.assertEqual(window.sockets, [])
        self.assertFalse(window.log_receive_button.isVisible())
        self.assertFalse(window.send_button.isEnabled())
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            peer.bind(('127.0.0.1', 0))
            window.add_connection_preview(ConnectionPreview('LOOP', '루프백', 'UDP', '127.0.0.1:0', f'127.0.0.1:{peer.getsockname()[1]}'))
            window.toggle_preview_connection()
            window.raw_editor.setPlainText('00 AB FF')
            self.assertTrue(window.send_button.isEnabled())
            window.send_button.click()
            wait_for(lambda: bool(select.select([peer], [], [], 0)[0]))
            self.assertEqual(peer.recvfrom(10)[0], b'\x00\xab\xff')
            peer.sendto(b'\xfe\x00', ('127.0.0.1', window.current_socket().local_port))
            wait_for(lambda: len(window.log_events) == 2)
            self.assertEqual(window.log_events[0]['values']['hex'], 'FE 00')
            window.flush_log_view()
            self.assertIn('LIVE', window.log_table.item(0, 7).text())
            window.log_table.selectRow(0)
            self.assertIn('FE 00', window.log_detail.toPlainText())
            with tempfile.TemporaryDirectory() as directory:
                filename = Path(directory) / 'live.json'
                with patch('ds_simulator.activity.QFileDialog.getSaveFileName', return_value=(str(filename), 'JSON')):
                    window.export_log()
                exported = json.loads(filename.read_text())
                self.assertEqual(exported['format'], 'ds-communication-log')
                self.assertEqual(exported['events'][0]['mode'], 'LIVE')
            window.mock_receive()
            self.assertEqual(len(window.log_events), 2)
            window.mode_select.setCurrentIndex(1)
            self.assertFalse(window.transport.network.sessions)
            self.assertEqual(window.sockets, [])
            self.assertFalse(window.send_button.isEnabled())
            window.mode_select.setCurrentIndex(0)
            self.assertEqual(window.sockets, [])

    def test_real_server_tree_tracks_connections_and_selected_client(self):
        window = self.window
        window.add_connection_preview(ConnectionPreview('LOOP', '서버', 'TCP Server', '127.0.0.1:0'))
        window.toggle_preview_connection()
        port = window.connection_sockets(window.selected_connection())[0].local_port
        with socket.create_connection(('127.0.0.1', port)) as first, socket.create_connection(('127.0.0.1', port)) as second:
            wait_for(lambda: len(window.server_peers(window.selected_connection())) == 2)
            card = window.connection_cards['LOOP']
            self.assertEqual(card.root.childCount(), 2)
            self.assertFalse(window.send_button.isEnabled())
            selected = next(p for p in window.server_peers(window.selected_connection()) if p.remote_port == second.getsockname()[1])
            window.select_server_peer('LOOP', selected.identifier)
            window.raw_editor.setPlainText('DE AD')
            window.send_button.click()
            self.assertEqual(receive(second, 2), b'\xde\xad')
            self.assertFalse(select.select([first], [], [], 0)[0])
            second.close()
            wait_for(lambda: card.root.childCount() == 1)
            self.assertIsNone(window.current_socket())
            self.assertFalse(window.send_button.isEnabled())

    def test_profile_edit_dialog_updates_disconnected_ip_and_port(self):
        window = self.window
        def edit():
            dialog = next(w for w in APP.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible())
            dialog.findChild(QLineEdit, 'remoteHost').setText('127.0.0.1')
            dialog.findChild(QSpinBox, 'remotePort').setValue(54321)
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        QTimer.singleShot(20, edit)
        window.show_connection_dialog(edit=True)
        self.assertEqual(window.selected_connection().remote_endpoint, '127.0.0.1:54321')
        self.assertEqual(window.selected_connection().identifier, 'TCP-01')

    def test_utf8_line_ending_is_explicit_and_profile_reload_closes_real_socket(self):
        window = self.window
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            peer.bind(('127.0.0.1', 0))
            window.add_connection_preview(ConnectionPreview('LOOP', 'UDP', 'UDP', '127.0.0.1:0', f'127.0.0.1:{peer.getsockname()[1]}'))
            window.toggle_preview_connection()
            port = window.current_socket().local_port
            window.send_format.setCurrentIndex(2)
            window.raw_editor.setPlainText('한글')
            window.raw_ending.setCurrentIndex(2)
            window.send_button.click()
            wait_for(lambda: bool(select.select([peer], [], [], 0)[0]))
            self.assertEqual(peer.recvfrom(100)[0], '한글\r\n'.encode())
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'profiles.json'
                window.save_profiles_to(path); window.load_profiles_from(path)
            self.assertFalse(window.transport.network.sessions)
            self.assertEqual(window.sockets, [])
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1', port))

    def test_mode_switch_is_blocked_during_a_running_scenario(self):
        window = self.window
        runner = window.scenario_editor.runner
        runner.start(Scenario('대기', [Step('wait', milliseconds=1000)]))
        window.mode_select.setCurrentIndex(1)
        self.assertTrue(window.transport.live)
        self.assertEqual(window.mode_select.currentIndex(), 0)
        runner.stop()

    def test_raw_scenario_editor_can_save_reload_and_run_actual_datagrams(self):
        window = self.window
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            peer.bind(('127.0.0.1', 0))
            window.add_connection_preview(ConnectionPreview('LOOP', 'UDP', 'UDP', '127.0.0.1:0', f'127.0.0.1:{peer.getsockname()[1]}'))
            window.toggle_preview_connection()
            editor = window.scenario_editor
            editor.palette.setCurrentRow(editor.palette.count() - 1)
            editor.add_selected()
            editor.properties.findChild(QPlainTextEdit).setPlainText('AB 01')
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'raw.json'
                editor.save_to(path); editor.load_from(path)
                self.assertEqual(load_scenario(path).steps[0].wire_data, 'AB 01')
            editor.run()
            wait_for(lambda: not editor.runner.running)
            wait_for(lambda: bool(select.select([peer], [], [], 0)[0]))
            self.assertEqual(peer.recvfrom(10)[0], b'\xab\x01')
            self.assertEqual(window.log_events[0]['mode'], 'LIVE')
