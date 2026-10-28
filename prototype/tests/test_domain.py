import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ds_simulator.domain import Scenario, Step, default_headers, default_values, iter_actions, load_scenario, save_json, validate_message
from ds_simulator.profiles import read_profiles
from ds_simulator.preview_data import MESSAGES


class DomainTests(unittest.TestCase):
    def test_all_sample_messages_validate(self):
        for name in MESSAGES:
            with self.subTest(message=name):
                self.assertTrue(validate_message(name, default_headers(name), default_values(name)))

    def test_integer_ranges_and_numeric_formats(self):
        values = default_values('SET_FREQUENCY')
        for invalid in ('-1', '256', '1.5', '1,2', 'nan', ''):
            values['channel'] = invalid
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                validate_message('SET_FREQUENCY', default_headers('SET_FREQUENCY'), values)
        values['channel'] = '255'
        parsed = validate_message('SET_FREQUENCY', default_headers('SET_FREQUENCY'), values)
        self.assertEqual(parsed['center_frequency'], 1000000000)
        self.assertEqual(parsed['channel'], 255)

    def test_invalid_headers_and_fields(self):
        for headers, fields in [({'src': 'AAAA', 'dst': '0x1', 'cmd': '0x2'}, default_values('REQUEST_STATUS')), (default_headers('REQUEST_STATUS'), {})]:
            with self.assertRaises(ValueError):
                validate_message('REQUEST_STATUS', headers, fields)

    def test_nonfinite_and_float_overflow_rejected(self):
        for value in ('nan', 'inf', '1e100'):
            fields = default_values('STATUS_RESPONSE')
            fields['temperature'] = value
            with self.assertRaises(ValueError):
                validate_message('STATUS_RESPONSE', default_headers('STATUS_RESPONSE'), fields)

    def test_nested_repetition_order(self):
        scenario = Scenario(steps=[Step('repeat', count=2, children=[Step.send(), Step('repeat', count=3, children=[Step('wait', milliseconds=0)])])])
        self.assertEqual(scenario.validate(), 8)
        self.assertEqual([s.kind for s in iter_actions(scenario.steps)], ['send', 'wait', 'wait', 'wait'] * 2)

    def test_roundtrip_preserves_values_targets_and_endian(self):
        scenario = Scenario.example()
        step = scenario.steps[0].children[0]
        step.values['channel'] = '2'
        step.socket_id = 'SOCK-004'
        step.big_endian = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '한글 시험.json'
            save_json(path, scenario.to_dict())
            loaded = load_scenario(path)
        self.assertEqual(loaded.to_dict(), scenario.to_dict())

    def test_invalid_files_fail_without_silent_defaults(self):
        baseline = Scenario.example().to_dict()
        examples = [[], {}, {**baseline, 'version': 2}, {**baseline, 'catalog': 'other'}]
        malformed = copy.deepcopy(baseline)
        malformed['steps'][0]['children'][0]['id'] = malformed['steps'][0]['id']
        examples.append(malformed)
        malformed = copy.deepcopy(baseline)
        malformed['steps'][0]['children'][0]['values'] = None
        examples.append(malformed)
        malformed = copy.deepcopy(baseline)
        malformed['steps'][0]['count'] = True
        examples.append(malformed)
        for data in examples:
            with self.subTest(data=data), self.assertRaises(ValueError):
                Scenario.from_dict(data)

    def test_execution_limit(self):
        scenario = Scenario(steps=[Step('repeat', count=1000, children=[Step('repeat', count=1000, children=[Step.send()])])])
        with self.assertRaises(ValueError):
            scenario.validate()

    def test_atomic_write_preserves_existing_file_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scenario.json'
            path.write_text('original')
            with patch('ds_simulator.domain.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    save_json(path, Scenario.example().to_dict())
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_profiles_validate_duplicates_and_port_ranges(self):
        entry = {'identifier': 'A', 'name': '장치', 'mode': 'TCP Client', 'local_endpoint': '0.0.0.0:0', 'remote_endpoint': '127.0.0.1:5000'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'connections.json'
            for rows in ([entry, entry], [{**entry, 'remote_endpoint': '127.0.0.1:70000'}], [{**entry, 'mode': 'unknown'}]):
                save_json(path, {'format': 'ds-connections', 'version': 1, 'connections': rows})
                with self.assertRaises(ValueError):
                    read_profiles(path)
