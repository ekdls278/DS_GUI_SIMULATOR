"""All workbooks in this suite are synthetic and contain no customer ICD data."""
from datetime import datetime
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import Workbook

from ds_simulator.icd import IcdMessage, message_id, data_sheet_names, read_icd_sheet, catalog_payload, catalog_from_payload
from ds_simulator.domain import Scenario, Step, load_scenario, save_json, validate_message
from ds_simulator.preview_data import MESSAGES

HEADERS = ['opcode', '연동자료명', '순번', '데이터 요소', '고정 설명', '가상 자료형', '가상 크기', '가상 최소', '가상 최대', '가상 초기', '고정 비고', '미사용', '사용자 선택값']


def icd_row(opcode, name, sequence, element, choices='', fixed=None):
    return [opcode, name, sequence, element, *(fixed or ['고정 0 1', 'uint8 예시', 1, 0, 255, 0, '원본 유지']), '사용하지 않는 L열', choices]


def make_workbook(path):
    book = Workbook()
    notes = book.active
    notes.title = '설명'
    notes.append(['이 시트는 ICD가 아닙니다'])
    notes.append(['IMPORT-MUST-NOT-SEE-THIS', '설명 내용', 1, '무시할 필드', 'X Y'])
    first = book.create_sheet('가상 장치 A(데이터)')
    first.append(HEADERS)
    first.append(icd_row('0x0010', '가상 운용 설정', 1, '운용 모드', 'OFF\nON\nAUTO\nHOLD'))
    first.append(icd_row(None, None, 2, '채널', '1\n2\n3'))
    first.merge_cells('A2:A3'); first.merge_cells('B2:B3')
    first.append(icd_row('0x0010', '가상 운용 설정', 3, '비고', None))
    first.append(icd_row('0x0011', '가상 상태 조회', 1, '조회 대상', 'A\nB\nA'))
    second = book.create_sheet('가상 장치 B(데이터)')
    second.append(HEADERS)
    second.append(icd_row('0x0020', '가상 출력 설정', 1, '출력 모드', 'LOW\nMEDIUM\nHIGH'))
    second.append(icd_row(None, None, 2, '설명', None))
    book.create_sheet('이전(데이터) 백업').append(['불러오지 않습니다'])
    book.save(path)
    book.close()


def set_formula_caches(path, values):
    """Simulate results saved by Excel; openpyxl itself never calculates formulas."""
    namespace = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with ZipFile(path) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    with ZipFile(path, 'w') as archive:
        for item, content in entries:
            if item.filename == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(content)
                for cell in root.iter(namespace + 'c'):
                    if cell.attrib['r'] in values:
                        kind, value = values[cell.attrib['r']]
                        cell.set('t', kind)
                        result = cell.find(namespace + 'v')
                        if result is None:
                            result = ET.SubElement(cell, namespace + 'v')
                        result.text = str(value)
                content = ET.tostring(root, encoding='utf-8')
            archive.writestr(item, content)


class IcdReaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'synthetic-icd.xlsx'
        make_workbook(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_only_data_suffix_sheets_are_listed_and_only_chosen_sheet_is_imported(self):
        self.assertEqual(data_sheet_names(self.path), ['가상 장치 A(데이터)', '가상 장치 B(데이터)'])
        messages = read_icd_sheet(self.path, '가상 장치 B(데이터)')
        self.assertEqual([(m.opcode, m.description) for m in messages.values()], [('0x0020', '가상 출력 설정')])
        with self.assertRaises(ValueError):
            read_icd_sheet(self.path, '설명')

    def test_merged_and_repeated_identity_rows_are_grouped_without_losing_fields(self):
        messages = read_icd_sheet(self.path, '가상 장치 A(데이터)')
        self.assertEqual(len(messages), 2)
        message = next(iter(messages.values()))
        self.assertEqual([f.sequence for f in message.elements], ['1', '2', '3'])
        self.assertEqual([f.name for f in message.elements], ['운용 모드', '채널', '비고'])
        self.assertEqual(message.elements[0].choices, ('OFF', 'ON', 'AUTO', 'HOLD'))
        self.assertEqual(message.elements[2].choices, ())
        self.assertEqual(list(messages.values())[1].elements[0].choices, ('A', 'B'))

    def test_numeric_opcode_zero_and_excel_zero_padding_are_preserved(self):
        book = Workbook(); sheet = book.active; sheet.title = '숫자(데이터)'
        sheet.append(HEADERS); sheet.append(icd_row(0, '가상 정지', 1, '선택', '0\n1'))
        sheet['A2'].number_format = '0000'
        book.save(self.path); book.close()
        message = next(iter(read_icd_sheet(self.path, sheet.title).values()))
        self.assertEqual(message.opcode, '0000')
        self.assertEqual(message.elements[0].choices, ('0', '1'))

    def test_new_opcode_does_not_silently_inherit_previous_message_name(self):
        book = Workbook(); sheet = book.active; sheet.title = '가상(데이터)'
        sheet.append(['header'] * 5)
        sheet.append(['0x1', '가상 첫 메시지', 1, '요소', 'A B'])
        sheet.append(['0x2', None, 1, '다른 요소', 'C D'])
        book.save(self.path); book.close()
        with self.assertRaisesRegex(ValueError, '3행'):
            read_icd_sheet(self.path, sheet.title)

    def test_l_and_n_are_ignored_and_uncached_formulas_in_m_are_reported(self):
        book = Workbook(); sheet = book.active; sheet.title = '가상(데이터)'
        sheet.append(HEADERS)
        sheet.append(icd_row('0x1', '가상 메시지', 1, '요소', 'A\nB'))
        sheet['L2'] = '=1+1'; sheet['N2'] = '=1+1'
        book.save(self.path)
        self.assertEqual(len(read_icd_sheet(self.path, sheet.title)), 1)
        sheet['M2'] = '=1+1'; book.save(self.path); book.close()
        with self.assertRaisesRegex(ValueError, 'M2'):
            read_icd_sheet(self.path, sheet.title)

    def test_formula_results_in_all_imported_columns_use_saved_values_and_preserve_original_file(self):
        book = Workbook(); sheet = book.active; sheet.title = '수식(데이터)'
        sheet.append(HEADERS)
        sheet.append(icd_row('="0x00A1"', '="가상 설정"', '=1+0', '="운용 모드"', '="OFF"&CHAR(10)&"ON"&CHAR(10)&"AUTO"'))
        sheet['E2'] = '="원본 고정"'; sheet['K2'] = '="고정 비고"'
        book.save(self.path); book.close()
        set_formula_caches(self.path, {'A2': ('str', '0x00A1'), 'B2': ('str', '가상 설정'),
                                      'C2': ('n', 1), 'D2': ('str', '운용 모드'), 'E2': ('str', '원본 고정'),
                                      'K2': ('str', '고정 비고'), 'M2': ('str', 'OFF\nON\nAUTO')})
        before = self.path.read_bytes()
        message = next(iter(read_icd_sheet(self.path, sheet.title).values()))
        self.assertEqual((message.opcode, message.description), ('0x00A1', '가상 설정'))
        self.assertEqual(message.elements[0].sequence, '1')
        self.assertEqual(message.elements[0].name, '운용 모드')
        self.assertEqual(message.elements[0].choices, ('OFF', 'ON', 'AUTO'))
        self.assertEqual(message.elements[0].fixed[2], '원본 고정')
        self.assertEqual(message.elements[0].fixed[8], '고정 비고')
        self.assertEqual(self.path.read_bytes(), before)

    def test_formula_numeric_zero_and_format_are_preserved_and_blank_result_can_continue_message(self):
        book = Workbook(); sheet = book.active; sheet.title = '수식(데이터)'
        sheet.append(['header'] * 5)
        sheet.append(['=0+0', '가상 메시지', 1, '선택', '0 1'])
        sheet['A2'].number_format = '0000'
        sheet.append(['=""', '=""', 2, '설명', '=""'])
        book.save(self.path); book.close()
        set_formula_caches(self.path, {'A2': ('n', 0), 'A3': ('str', ''), 'B3': ('str', ''), 'E3': ('str', '')})
        message = next(iter(read_icd_sheet(self.path, sheet.title).values()))
        self.assertEqual(message.opcode, '0000')
        self.assertEqual(len(message.elements), 2)
        self.assertEqual(message.elements[1].choices, ())

    def test_formula_without_saved_result_includes_recalculation_instructions(self):
        book = Workbook(); sheet = book.active; sheet.title = '수식(데이터)'
        sheet.append(['header'] * 5)
        sheet.append(['=1+1', '가상 메시지', 1, '요소', 'A B'])
        book.save(self.path); book.close()
        with self.assertRaisesRegex(ValueError, r'A2:.*Ctrl\+Alt\+F9.*저장'):
            read_icd_sheet(self.path, sheet.title)

    def test_uncached_formula_in_continuation_row_is_not_silently_forward_filled(self):
        book = Workbook(); sheet = book.active; sheet.title = '수식(데이터)'
        sheet.append(['header'] * 5)
        sheet.append(['0x0001', '가상 메시지', 1, '요소', 'A B'])
        sheet.append(['=1+1', None, 2, '다른 요소', 'C D'])
        book.save(self.path); book.close()
        with self.assertRaisesRegex(ValueError, 'A3:.*계산 결과가 없습니다'):
            read_icd_sheet(self.path, sheet.title)

    def test_excel_error_results_are_reported_instead_of_used_as_opcodes(self):
        book = Workbook(); sheet = book.active; sheet.title = '수식(데이터)'
        sheet.append(['header'] * 5)
        sheet.append(['=1/0', '가상 메시지', 1, '요소', 'A B'])
        book.save(self.path); book.close()
        set_formula_caches(self.path, {'A2': ('e', '#DIV/0!')})
        with self.assertRaisesRegex(ValueError, r'A2:.*#DIV/0!'):
            read_icd_sheet(self.path, sheet.title)

    def test_duplicate_element_names_have_independent_values_and_file_is_unchanged(self):
        book = Workbook(); sheet = book.active; sheet.title = '가상(데이터)'
        sheet.append(['header'] * 5)
        sheet.append(['0x1', '가상 메시지', 1, '같은 이름', 'A B'])
        sheet.append([None, None, 2, '같은 이름', 'C D'])
        book.save(self.path); book.close()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        message = next(iter(read_icd_sheet(self.path, sheet.title).values()))
        self.assertNotEqual(message.elements[0].key, message.elements[1].key)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_catalog_and_scenario_roundtrip_does_not_require_the_original_workbook(self):
        catalog = read_icd_sheet(self.path, '가상 장치 B(데이터)')
        key = next(iter(catalog)); step = Step.send(key, catalog)
        step.values['field_0001'] = 'HIGH'
        scenario = Scenario('가상 엑셀 시험', [step], catalog=catalog)
        path = self.path.with_suffix('.json')
        save_json(path, scenario.to_dict()); self.path.unlink()
        restored = load_scenario(path)
        self.assertEqual(restored.to_dict(), scenario.to_dict())
        self.assertEqual(restored.to_dict()['version'], 2)
        self.assertEqual(catalog_from_payload(catalog_payload(catalog)), catalog)

    def test_choice_validation_rejects_undefined_values_without_guessing_wire_types(self):
        catalog = read_icd_sheet(self.path, '가상 장치 B(데이터)')
        key = next(iter(catalog)); step = Step.send(key, catalog)
        step.values['field_0001'] = 'HIGH'
        self.assertEqual(validate_message(key, step.headers, step.values, catalog)['field_0001'], 'HIGH')
        step.values['field_0001'] = 'NOT_AN_OPTION'
        with self.assertRaises(ValueError):
            validate_message(key, step.headers, step.values, catalog)

    def test_invalid_excel_is_a_readable_error(self):
        self.path.write_text('not a zip workbook')
        with self.assertRaises(ValueError):
            data_sheet_names(self.path)

    def test_fixed_columns_are_preserved_and_only_m_newlines_create_choices(self):
        book = Workbook(); sheet = book.active; sheet.title = '새 형식(데이터)'
        sheet.append(HEADERS)
        fixed = ['  고정  설명\n둘째 줄  ', 'uint16', '2', '0', '65535', '0001', '고정 비고']
        sheet.append(icd_row('0x1', '가상 시험', 1, '운용 모드', ' 저속 운용 \r\n\r\n고속  운용\n저속 운용\r자동\t선택 ', fixed))
        sheet.append(icd_row(None, None, 2, '한 줄 항목', 'OFF ON AUTO'))
        book.save(self.path); book.close()
        message = next(iter(read_icd_sheet(self.path, sheet.title).values()))
        self.assertEqual(message.fixed_headers, tuple(HEADERS[2:11]))
        self.assertEqual(message.elements[0].fixed, ('1', '운용 모드', *fixed))
        self.assertEqual(message.elements[0].choices, ('저속 운용', '고속  운용', '자동\t선택'))
        self.assertEqual(message.elements[1].choices, ('OFF ON AUTO',))

    def test_blank_m_rejects_free_text_and_selected_values_do_not_mutate_fixed_definitions(self):
        catalog = read_icd_sheet(self.path, '가상 장치 B(데이터)')
        key = next(iter(catalog)); message = catalog[key]
        original = message.elements[0].fixed
        step = Step.send(key, catalog)
        step.values['field_0001'] = 'HIGH'
        validate_message(key, step.headers, step.values, catalog)
        self.assertEqual(message.elements[0].fixed, original)
        self.assertEqual(message.event_elements(step.values)[0]['fixed']['E'], '고정 0 1')
        step.values['field_0002'] = '임의 입력'
        with self.assertRaisesRegex(ValueError, 'M열.*변경'):
            validate_message(key, step.headers, step.values, catalog)

    def test_saved_catalog_includes_all_fixed_columns_and_detects_modified_definitions(self):
        catalog = read_icd_sheet(self.path, '가상 장치 B(데이터)')
        payload = catalog_payload(catalog)
        self.assertEqual(payload['version'], 2)
        self.assertEqual(payload['messages'][0]['fixed_headers'], HEADERS[2:11])
        self.assertEqual(len(payload['messages'][0]['fields'][0]['fixed']), 9)
        modified = deepcopy(payload)
        modified['messages'][0]['fields'][0]['fixed'][8] = '변경된 K열'
        with self.assertRaises(ValueError):
            catalog_from_payload(modified)
        malformed = deepcopy(payload)
        malformed['messages'][0]['fields'][0]['fixed'].pop()
        with self.assertRaises(ValueError):
            catalog_from_payload(malformed)

    def test_legacy_catalog_roundtrip_keeps_its_original_schema_and_is_not_treated_as_m(self):
        rows = [{'id': message_id('0x1', '이전 시험'), 'opcode': '0x1', 'name': '이전 시험', 'fields': [
            {'key': 'field_0001', 'sequence': '1', 'name': '이전 요소', 'choices': ['OLD', 'NEW'], 'default': 'OLD'},
            {'key': 'field_0002', 'sequence': '2', 'name': '이전 텍스트', 'choices': [], 'default': ''}]}]
        fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        payload = {'format': 'ds-icd-catalog', 'version': 1, 'messages': rows, 'fingerprint': fingerprint}
        catalog = catalog_from_payload(payload)
        self.assertFalse(next(iter(catalog.values())).current_layout)
        self.assertEqual(catalog_payload(catalog), payload)

    def test_empty_sheet_reports_a_readable_error(self):
        book = Workbook(); sheet = book.active; sheet.title = '빈 시트(데이터)'
        book.save(self.path); book.close()
        with self.assertRaises(ValueError):
            read_icd_sheet(self.path, sheet.title)
