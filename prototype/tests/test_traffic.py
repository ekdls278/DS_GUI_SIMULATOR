from datetime import datetime, timezone
import unittest

from ds_simulator.traffic import TrafficHistory, display_groups

BASE = 1800000000


def event(stamp=BASE, connection='TCP-01', direction='TX', message='SET_FREQUENCY', socket='SOCK-1', mode='TCP Client'):
    return {'time': datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='milliseconds'), 'connection_id': connection, 'connection_mode': mode, 'socket_id': socket, 'direction': direction, 'message': message, 'peer': '127.0.0.1:5000', 'values': {'channel': 1}, 'headers': {'src': '0x1', 'dst': '0x2', 'cmd': '0x3'}, 'mode': 'MOCK', 'source': 'test', 'big_endian': False}


class TrafficTests(unittest.TestCase):
    def test_bounded_records_keep_accurate_totals_and_rates(self):
        history = TrafficHistory()
        for _ in range(2501):
            history.append(event())
        snapshot = history.snapshot(BASE)
        self.assertEqual(len(snapshot.records), 2000)
        self.assertEqual(snapshot.stats()['TX'], 2501)
        self.assertEqual(snapshot.rate_series(BASE, 1), [(BASE, 2501, 0)])

    def test_snapshot_is_stable_and_caller_cannot_change_recorded_values(self):
        history = TrafficHistory()
        original = event()
        history.append(original)
        snapshot = history.snapshot(BASE)
        original['values']['channel'] = 99
        history.append(event(direction='RX'))
        self.assertEqual(len(snapshot.records), 1)
        self.assertEqual(snapshot.records[0]['values']['channel'], 1)
        self.assertEqual(snapshot.stats()['RX'], 0)
        self.assertEqual(history.snapshot(BASE).stats()['RX'], 1)

    def test_server_clients_are_separate_even_when_messages_overlap(self):
        history = TrafficHistory()
        history.append(event(socket='SOCK-A', mode='TCP Server', connection='SRV-01'))
        history.append(event(socket='SOCK-B', mode='TCP Server', connection='SRV-01'))
        groups = display_groups(history.records, BASE - 1, BASE + 1, 1)
        self.assertEqual({key[0] for key, _ in groups}, {('SRV-01', 'SOCK-A'), ('SRV-01', 'SOCK-B')})

    def test_spectrum_is_grouped_per_second_and_tx_rx_remain_distinct(self):
        history = TrafficHistory()
        for i in range(100):
            history.append(event(BASE + i / 1000, direction='RX', message='SPECTRUM_DATA'))
        history.append(event(BASE, direction='TX', message='SPECTRUM_DATA'))
        groups = display_groups(history.records, BASE, BASE + 2, 100)
        self.assertEqual(sorted((key[1], len(records)) for key, records in groups), [('RX', 100), ('TX', 1)])

    def test_window_and_connection_filters_exclude_other_records(self):
        history = TrafficHistory()
        history.append(event(BASE - 10))
        history.append(event(BASE, connection='TCP-02'))
        history.append(event(BASE, direction='RX'))
        groups = display_groups(history.records, BASE - 1, BASE + 1, 5, 'TCP-01')
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0][1], 'RX')
        self.assertEqual(history.snapshot(BASE).stats('TCP-02')['TX'], 1)

    def test_rate_gaps_and_connection_filters_are_correct(self):
        history = TrafficHistory()
        history.append(event(BASE - 2))
        history.append(event(BASE, direction='RX'))
        history.append(event(BASE, connection='TCP-02'))
        self.assertEqual(history.snapshot(BASE).rate_series(BASE, 3, 'TCP-01'), [(BASE - 2, 1, 0), (BASE - 1, 0, 0), (BASE, 0, 1)])

    def test_invalid_timestamp_does_not_increment_counts(self):
        history = TrafficHistory()
        broken = event()
        broken['time'] = 'not-a-time'
        with self.assertRaises(ValueError):
            history.append(broken)
        self.assertEqual(history.received, 0)
        self.assertEqual(len(history.records), 0)
