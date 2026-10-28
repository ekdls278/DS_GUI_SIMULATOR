import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ds_simulator.app import SimulatorWindow
from ds_simulator.domain import Scenario, Step
from ds_simulator.preview_data import CONNECTIONS, SOCKETS, ConnectionPreview
from ds_simulator.runtime import MockTransport, ScenarioRunner
from ds_simulator.scenario_editor import ROLE
from ds_simulator.theme import STYLESHEET

APP = QApplication.instance() or QApplication([])
APP.setStyle('Fusion')
APP.setFont(QFont('Noto Sans CJK KR', 10))
APP.setStyleSheet(STYLESHEET)


def wait_until(predicate, timeout=1500):
    for _ in range(timeout // 10):
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError('Timed out waiting for Qt operation')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.sockets = list(SOCKETS)
        self.transport = MockTransport(lambda: list(CONNECTIONS), lambda: self.sockets)
        self.events = []
        self.transport.sent.connect(self.events.append)
        self.runner = ScenarioRunner(self.transport)

    def tearDown(self):
        self.runner.stop()
        self.runner.deleteLater()
        self.transport.deleteLater()
        APP.processEvents()

    def test_three_repeats_share_sender_and_preserve_order(self):
        scenario = Scenario.example()
        scenario.steps[0].count = 3
        scenario.steps[0].children[1].milliseconds = 1
        self.runner.start(scenario)
        wait_until(lambda: not self.runner.running)
        self.assertEqual(self.runner.completed, 9)
        self.assertEqual([e['message'] for e in self.events], ['SET_FREQUENCY', 'REQUEST_STATUS'] * 3)
        self.assertTrue(all(e['mode'] == 'MOCK' and e['source'] == '시나리오' for e in self.events))

    def test_stop_cancels_pending_wait_and_future_sends(self):
        self.runner.start(Scenario(steps=[Step('wait', milliseconds=1000), Step.send()]))
        QTest.qWait(20)
        self.runner.stop()
        QTest.qWait(40)
        self.assertFalse(self.runner.timer.isActive())
        self.assertEqual(self.runner.completed, 0)
        self.assertEqual(self.events, [])

    def test_disconnection_during_wait_stops_without_sending_elsewhere(self):
        states = []
        self.runner.finished.connect(states.append)
        self.runner.start(Scenario(steps=[Step('wait', milliseconds=30), Step.send()]))
        self.sockets = [s for s in self.sockets if s.connection_id != 'TCP-01']
        wait_until(lambda: not self.runner.running)
        self.assertTrue(states[-1].startswith('오류:'))
        self.assertEqual(self.events, [])

    def test_server_listener_cannot_be_used_for_transmission(self):
        step = Step.send()
        step.connection_id = 'SRV-01'
        for identifier in ('', 'SOCK-003'):
            step.socket_id = identifier
            with self.assertRaises(ValueError):
                self.transport.send(step)
        step.socket_id = 'SOCK-005'
        event = self.transport.send(step)
        self.assertEqual(event['peer'], '192.168.0.22:51002')

    def test_snapshot_is_independent_of_editor_changes(self):
        step = Step.send()
        scenario = Scenario(steps=[Step('wait', milliseconds=10), step])
        self.runner.start(scenario)
        step.values['channel'] = '9'
        wait_until(lambda: not self.runner.running)
        self.assertEqual(self.events[0]['values']['channel'], 1)

    def test_empty_repeat_is_not_executed(self):
        with self.assertRaises(ValueError):
            self.runner.start(Scenario(steps=[Step('repeat', children=[]), Step.send()]))
        self.assertFalse(self.runner.running)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.window = SimulatorWindow()
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.scenario_editor.dirty = False
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def connect_first(self):
        QTest.mouseClick(self.window.connect_button, Qt.MouseButton.LeftButton)
        self.window.message_catalog.setCurrentRow(0)
        APP.processEvents()
        self.assertTrue(self.window.send_button.isEnabled())

    def click_peer(self, card, index):
        item = card.root.child(index)
        card.root.setExpanded(True)
        card.tree.scrollToItem(item)
        APP.processEvents()
        QTest.mouseClick(card.tree.viewport(), Qt.MouseButton.LeftButton, pos=card.tree.visualItemRect(item).center())
        APP.processEvents()

    def test_server_tree_selects_exact_client_and_header_is_not_send_target(self):
        self.window.select_connection(2)
        card = self.window.connection_cards['SRV-01']
        self.assertTrue(card.is_server)
        self.assertIn('0.0.0.0:7000', card.header.text())
        self.assertEqual(card.root.childCount(), 2)
        self.assertIn('192.168.0.21:51001', card.root.child(0).text(0))
        self.assertIn('192.168.0.22:51002', card.root.child(1).text(0))
        self.assertFalse(self.window.send_button.isEnabled())
        self.click_peer(card, 1)
        self.assertEqual(self.window.current_socket().identifier, 'SOCK-005')
        self.window.message_catalog.setCurrentRow(0)
        QTest.mouseClick(self.window.send_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.log_events[0]['peer'], '192.168.0.22:51002')
        self.click_peer(card, 0)
        self.assertIsNone(self.window.selected_message_name)
        self.assertFalse(self.window.send_button.isEnabled())
        self.assertEqual(self.window.current_socket().identifier, 'SOCK-004')
        QTest.mouseClick(card.header, Qt.MouseButton.LeftButton)
        self.assertIsNone(self.window.current_socket())
        self.assertEqual(card.tree.selectedItems(), [])

    def test_multiple_servers_have_separate_children_and_borders(self):
        self.window.add_connection_preview(ConnectionPreview('SRV-02', '두 번째 서버', 'TCP Server', '127.0.0.1:7100'))
        second = self.window.connection_cards['SRV-02']
        first = self.window.connection_cards['SRV-01']
        self.assertNotEqual(first.accent, second.accent)
        self.assertIn('3px solid', second.styleSheet())
        self.assertEqual(second.root.childCount(), 0)
        self.window.toggle_preview_connection()
        self.window.accept_preview_peer()
        self.assertEqual(second.root.childCount(), 1)
        self.assertEqual(first.root.childCount(), 2)
        self.assertEqual(self.window.current_socket().connection_id, 'SRV-02')
        self.click_peer(first, 0)
        self.assertEqual(self.window.selected_connection().identifier, 'SRV-01')
        self.assertEqual(self.window.current_socket().identifier, 'SOCK-004')
        self.assertEqual(second.tree.selectedItems(), [])

    def test_server_stop_and_restart_remove_stale_children_and_selection(self):
        self.window.select_connection(2)
        card = self.window.connection_cards['SRV-01']
        self.click_peer(card, 0)
        self.window.message_catalog.setCurrentRow(0)
        self.window.toggle_preview_connection()
        self.assertEqual(card.root.childCount(), 0)
        self.assertIn('서버 중지', card.header.text())
        self.assertFalse(self.window.send_button.isEnabled())
        self.window.toggle_preview_connection()
        self.assertIn('LISTENING', card.header.text())
        self.assertIsNone(self.window.current_socket())
        self.window.accept_preview_peer()
        self.assertEqual(card.root.childCount(), 1)
        self.assertEqual(self.window.current_socket().identifier, card.root.child(0).data(0, Qt.ItemDataRole.UserRole))

    def test_disappearing_peer_clears_tree_and_composer_target(self):
        self.window.select_connection(2)
        card = self.window.connection_cards['SRV-01']
        self.click_peer(card, 0)
        self.window.message_catalog.setCurrentRow(0)
        self.window.sockets = [s for s in self.window.sockets if s.identifier != 'SOCK-004']
        self.window.refresh_socket_monitor()
        self.assertEqual(card.root.childCount(), 1)
        self.assertIsNone(self.window.current_socket())
        self.assertIsNone(self.window.selected_message_name)
        self.assertFalse(self.window.send_button.isEnabled())

    def test_profile_reload_replaces_server_card_groups_without_duplicate_widgets(self):
        old_card = self.window.connection_cards['SRV-01']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'connections.json'
            self.window.save_profiles_to(path)
            self.window.load_profiles_from(path)
        self.assertIsNot(self.window.connection_cards['SRV-01'], old_card)
        self.assertEqual(len(self.window.connection_cards), 4)
        self.assertEqual(self.window.connection_list.count(), 5)  # four cards and stretch
        self.assertEqual(self.window.connection_cards['SRV-01'].root.childCount(), 0)

    def test_manual_send_validation_and_actual_values_in_log(self):
        self.connect_first()
        self.window.payload_inputs['channel'].setText('256')
        self.assertFalse(self.window.send_button.isEnabled())
        self.window.payload_inputs['channel'].setText('2')
        self.window.big_endian.setChecked(True)
        QTest.mouseClick(self.window.send_button, Qt.MouseButton.LeftButton)
        self.assertEqual(len(self.window.log_events), 1)
        event = self.window.log_events[0]
        self.assertEqual(event['values']['channel'], 2)
        self.assertTrue(event['big_endian'])
        self.assertEqual(event['connection_id'], 'TCP-01')
        self.assertEqual(event['source'], '수동')

    def test_add_move_indent_outdent_and_save_reload(self):
        editor = self.window.scenario_editor
        root = editor.tree.topLevelItem(0)
        editor.tree.setCurrentItem(root)
        editor.palette.setCurrentRow(1)  # wait
        editor.add_selected()
        self.assertEqual(root.childCount(), 4)
        added = editor.tree.currentItem()
        editor.move(-1)
        self.assertIs(root.child(2), added)
        editor.outdent()
        self.assertIs(editor.tree.topLevelItem(1), added)
        editor.indent()
        self.assertIs(added.parent(), root)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '한글.json'
            editor.save_to(path)
            saved = editor.collect().to_dict()
            editor.document = Scenario('empty')
            editor.populate()
            editor.load_from(path)
            self.assertEqual(editor.collect().to_dict(), saved)
            self.assertFalse(editor.dirty)

    def test_invalid_load_preserves_editor(self):
        editor = self.window.scenario_editor
        original = editor.collect().to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.json'
            path.write_text('{broken')
            with self.assertRaises(ValueError):
                editor.load_from(path)
        self.assertEqual(editor.collect().to_dict(), original)

    def test_scenario_execution_reaches_shared_log_and_locks_editor(self):
        self.connect_first()
        self.window.show_page(4)
        editor = self.window.scenario_editor
        repeat = editor.tree.topLevelItem(0).data(0, ROLE)
        editor.tree.setCurrentItem(editor.tree.topLevelItem(0).child(0))
        from PySide6.QtWidgets import QComboBox
        target = editor.properties.findChild(QComboBox)
        self.assertNotIn('재선택', target.currentText())
        repeat.count = 2
        editor.tree.topLevelItem(0).child(1).data(0, ROLE).milliseconds = 1
        QTest.mouseClick(editor.run_button, Qt.MouseButton.LeftButton)
        self.assertFalse(editor.edit_area.isEnabled())
        wait_until(lambda: not editor.runner.running)
        self.assertTrue(editor.edit_area.isEnabled())
        self.assertEqual(len(self.window.log_events), 4)
        self.assertEqual(editor.runner.completed, 6)
        self.assertTrue(all(e['source'] == '시나리오' for e in self.window.log_events))

    def test_profiles_roundtrip_clears_sessions_and_requires_reconnect(self):
        self.connect_first()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'connections.json'
            self.window.save_profiles_to(path)
            expected = list(self.window.connections)
            self.window.load_profiles_from(path)
        self.assertEqual(self.window.connections, expected)
        self.assertEqual(self.window.sockets, [])
        self.assertFalse(self.window.send_button.isEnabled())
        self.assertEqual(self.window.socket_table.rowCount(), 0)

    def test_filtered_export_contains_values_and_mock_marker(self):
        self.connect_first()
        self.window.preview_send()
        self.window.mock_receive()
        self.assertEqual(len(self.window.log_events), 2)
        self.window.log_direction.setCurrentIndex(1)  # TX only
        self.assertEqual(len(self.window.visible_events()), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'log.json'
            with patch('ds_simulator.activity.QFileDialog.getSaveFileName', return_value=(str(path), 'JSON (*.json)')):
                self.window.export_log()
            data = json.loads(path.read_text())
            self.assertEqual(len(data['events']), 1)
            self.assertEqual(data['events'][0]['mode'], 'MOCK')
            self.assertEqual(data['events'][0]['values']['center_frequency'], 1000000000)
            path = Path(directory) / 'log.csv'
            with patch('ds_simulator.activity.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV (*.csv)')):
                self.window.export_log()
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertNotIn(b'\r\r\n', path.read_bytes())
            self.assertEqual(len(rows), 2)
            self.assertIn('MOCK', rows[1][7])
