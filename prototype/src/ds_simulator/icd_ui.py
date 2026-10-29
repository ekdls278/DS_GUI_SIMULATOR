"""Excel sheet chooser and the live ICD definition page."""
from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QListWidget, QMessageBox, QTableWidgetItem, QVBoxLayout

from .icd import IcdMessage, data_sheet_names, read_icd_sheet
from .widgets import Card, button, label, row, table


class SheetSelectionDialog(QDialog):
    def __init__(self, names, parent=None):
        super().__init__(parent)
        self.setWindowTitle('(데이터) 시트 선택')
        self.resize(470, 300)
        body = QVBoxLayout(self)
        body.addWidget(label('가져올 시트 하나를 선택하세요.', 'heading'))
        self.sheets = QListWidget()
        self.sheets.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.sheets.addItems(names)
        body.addWidget(self.sheets, 1)
        note = label('선택한 시트의 A~E열, 2행부터 읽습니다.\n확인하면 ICD 목록을 교체하고 시나리오는 새 시험으로 초기화합니다.', 'caption')
        note.setWordWrap(True)
        body.addWidget(note)
        self.actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.actions.button(QDialogButtonBox.StandardButton.Ok).setText('확인')
        self.actions.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.actions.accepted.connect(self.accept)
        self.actions.rejected.connect(self.reject)
        self.sheets.currentRowChanged.connect(lambda index: self.actions.button(QDialogButtonBox.StandardButton.Ok).setEnabled(index >= 0))
        self.actions.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(names))
        if names:
            self.sheets.setCurrentRow(0)
        body.addWidget(self.actions)

    def selected_sheet(self):
        item = self.sheets.currentItem()
        return item.text() if item else None


class IcdMixin:
    def scenario_catalog(self):
        return dict(self.messages) if self.messages and all(isinstance(message, IcdMessage) for message in self.messages.values()) else None

    def make_icd_page(self):
        page, layout = self.page('ICD 정의', 'Excel에서 시트를 선택하고 opcode·연동자료명·데이터 요소를 확인합니다.')
        source = Card()
        heading = row(label('ICD 원본', 'heading'))
        heading.addStretch()
        self.import_icd_button = button('엑셀 가져오기', primary=True, icon_name='plus')
        self.import_icd_button.clicked.connect(self.import_excel_dialog)
        heading.addWidget(self.import_icd_button)
        source.body.addLayout(heading)
        self.definition_source = label(self.catalog_source, 'muted')
        self.definition_source.setWordWrap(True)
        source.body.addWidget(self.definition_source)
        source.body.addWidget(label('E열의 공백 구분 항목은 선택값으로 사용합니다. 선택값이 없으면 직접 입력합니다.', 'caption'))
        layout.addWidget(source)
        panels = QHBoxLayout()
        catalog = Card('opcode · 연동자료명')
        catalog.setMinimumWidth(310)
        self.definition_catalog = table(['opcode', '연동자료명'], [])
        catalog.body.addWidget(self.definition_catalog, 1)
        panels.addWidget(catalog, 3)
        detail = Card()
        self.definition_title = label('', 'heading')
        self.definition_note = label('', 'muted')
        detail.body.addWidget(self.definition_title)
        detail.body.addWidget(self.definition_note)
        self.definition_fields = table(['순번', '데이터 요소', '입력 방식', '선택 가능 값', '초기값'], [], stretch_column=3)
        self.definition_fields.setMinimumHeight(360)
        detail.body.addWidget(self.definition_fields, 1)
        detail.body.addWidget(label('A~E열만으로는 바이트 길이·타입·엔디언을 확정하지 않습니다. 현재 송수신은 모의 동작입니다.', 'caption'))
        panels.addWidget(detail, 7)
        layout.addLayout(panels, 1)
        self.definition_catalog.itemSelectionChanged.connect(self.show_definition)
        self.refresh_icd_definition()
        return page

    def refresh_icd_definition(self):
        self.definition_keys = list(self.messages)
        self.definition_source.setText(self.catalog_source)
        self.definition_catalog.blockSignals(True)
        self.definition_catalog.setRowCount(len(self.definition_keys))
        for index, key in enumerate(self.definition_keys):
            message = self.messages[key]
            self.definition_catalog.setItem(index, 0, QTableWidgetItem(message.cmd))
            self.definition_catalog.setItem(index, 1, QTableWidgetItem(message.description))
        self.definition_catalog.blockSignals(False)
        if self.definition_keys:
            self.definition_catalog.selectRow(0)
        self.show_definition()

    def show_definition(self):
        index = self.definition_catalog.currentRow()
        if not 0 <= index < len(self.definition_keys):
            return
        message = self.messages[self.definition_keys[index]]
        self.definition_title.setText(message.description)
        self.definition_note.setText(f'opcode {message.cmd} · 데이터 요소 {len(message.fields)}개')
        if isinstance(message, IcdMessage):
            rows = message.field_rows()
        else:
            rows = [[str(index), description, data_type, unit if unit != '—' else '', value] for index, (_, data_type, value, unit, description) in enumerate(message.fields, 1)]
        self.definition_fields.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                self.definition_fields.setItem(row_index, column, QTableWidgetItem(value))

    def apply_catalog(self, messages, source, reset_scenario=True):
        if self.scenario_editor.runner.running:
            raise ValueError('시나리오 실행을 중지한 뒤 ICD를 변경하세요.')
        self.clear_message_selection()
        self.messages = dict(messages)
        self.catalog_source = source
        self.refresh_message_catalog()
        self.refresh_icd_definition()
        self.sidebar_messages.setText(f'      ICD 메시지            {len(messages):02}')
        if reset_scenario:
            self.scenario_editor.reset_for_catalog()
        self.update_send_button()

    def import_excel_dialog(self):
        if self.scenario_editor.runner.running:
            QMessageBox.information(self, '시나리오 실행 중', '시나리오 실행을 중지한 뒤 ICD를 가져오세요.')
            return
        path, _ = QFileDialog.getOpenFileName(self, 'ICD Excel 파일 선택', '', 'Excel (*.xlsx *.xlsm)')
        if not path:
            return
        try:
            names = data_sheet_names(path)
            if not names:
                raise ValueError('이름이 (데이터)로 끝나는 시트가 없습니다.')
            chooser = SheetSelectionDialog(names, self)
            if chooser.exec() != QDialog.DialogCode.Accepted:
                return
            messages = read_icd_sheet(path, chooser.selected_sheet())
            if not self.scenario_editor.confirm_discard():
                return
            self.apply_catalog(messages, f'{Path(path).name} · {chooser.selected_sheet()}')
            self.statusBar().showMessage(f'선택한 시트에서 ICD {len(messages)}개를 가져왔습니다.', 6000)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'ICD 가져오기 실패', str(exc))
