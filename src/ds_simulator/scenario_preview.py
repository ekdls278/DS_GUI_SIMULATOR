"""Static scenario design preview; no Blockly, drag/drop or execution engine yet."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QFormLayout, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from .widgets import Card, button, chip, label, row


class BlockCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(450, 550)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#f8faff"))
        p.setPen(QColor("#dce4f1"))
        for x in range(12, self.width(), 20):
            for y in range(12, self.height(), 20):
                p.drawPoint(x, y)
        scale = min(self.width() / 620, self.height() / 650)
        p.translate((self.width() - 620 * scale) / 2, (self.height() - 650 * scale) / 2)
        p.scale(scale, scale)

        def text(x, y, value, color="#ffffff", size=13, bold=False):
            font = QFont(self.font())
            font.setPixelSize(size)
            font.setBold(bold)
            p.setFont(font)
            p.setPen(QColor(color))
            p.drawText(QRectF(x, y, 520, 28), Qt.AlignmentFlag.AlignVCenter, value)

        def block(x, y, width, height, color, selected=False):
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, width, height), 8, 8)
            path.addRoundedRect(QRectF(x + 25, y + height - 3, 34, 11), 4, 4)
            if selected:
                p.setPen(QPen(QColor("#b8cdff"), 8))
                p.setBrush(QColor(color))
                p.drawPath(path)
            p.setPen(QPen(QColor(color).darker(115), 1))
            p.setBrush(QColor(color))
            p.drawPath(path)
            p.setBrush(QColor("#ffffff"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x + 25, y - 1, 34, 7), 3, 3)

        block(40, 28, 240, 52, "#28a078")
        text(59, 40, "▶  시험 시작", size=16, bold=True)
        text(298, 41, "주파수 설정 반복 시험", "#8593a8", 12)

        outer = QPainterPath()
        outer.addRoundedRect(QRectF(40, 106, 535, 412), 10, 10)
        cut = QPainterPath()
        cut.addRoundedRect(QRectF(62, 170, 550, 308), 6, 6)
        p.setPen(QPen(QColor("#cf8d24"), 1))
        p.setBrush(QColor("#e8a638"))
        p.drawPath(outer.subtracted(cut))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#fff8e9"))
        p.drawRoundedRect(QRectF(109, 123, 55, 30), 5, 5)
        text(57, 123, "반복", size=16, bold=True)
        text(125, 124, "10", "#9b6217", 16, True)
        text(176, 124, "회  반복하기", size=16, bold=True)
        text(382, 125, "아래 활동 전체를 반복", "#fff9ee", 12)
        text(71, 483, "↻  마지막 활동 완료 후 처음으로", "#fff9ee", 12)

        block(78, 182, 473, 96, "#4a71dd", selected=True)
        text(96, 194, "01   ICD 메시지 송신", size=16, bold=True)
        text(96, 226, "SET_FREQUENCY   ·   주파수 설정", size=14)
        text(96, 248, "TCP-01   |   1,000 MHz   |   CH 1", "#dce7ff", 12)

        block(78, 292, 360, 60, "#5c9fba")
        text(96, 307, "02   대기     500   ms", size=16, bold=True)

        block(78, 366, 473, 96, "#4a71dd")
        text(96, 378, "03   ICD 메시지 송신", size=16, bold=True)
        text(96, 410, "REQUEST_STATUS   ·   상태 조회", size=14)
        text(96, 432, "TCP-01   |   CMD 0xCCCD", "#dce7ff", 12)

        block(40, 546, 240, 52, "#76849a")
        text(59, 558, "■  시험 종료", size=16, bold=True)
        text(40, 614, "반복 블록 안에 활동 하나 또는 여러 활동을 넣을 수 있습니다.", "#8392a8", 12)
        p.end()


def make_scenario_page(window):
    page, layout = window.page("시나리오 편집기", "ICD 메시지를 블록으로 연결하고, 반복할 시험 순서를 구성합니다.")
    layout.setSpacing(14)
    toolbar = Card()
    toolbar.body.setContentsMargins(16, 10, 16, 10)
    actions = row(label("주파수 설정 반복 시험", "heading"), chip("화면 시안"))
    actions.addStretch()
    for title, primary in (("불러오기", False), ("저장", False), ("시험 실행", True)):
        control = button(title, primary=primary, icon_name="arrow" if primary else "")
        control.clicked.connect(lambda checked=False, name=title: window.preview_notice(f"시나리오 {name} 버튼"))
        actions.addWidget(control)
    toolbar.body.addLayout(actions)
    layout.addWidget(toolbar)

    panels = QHBoxLayout()
    panels.setSpacing(14)
    palette = Card("블록 목록")
    palette.setMinimumWidth(235)
    search = QLineEdit()
    search.setPlaceholderText("블록 검색")
    search.setReadOnly(True)
    palette.body.addWidget(search)
    palette.body.addWidget(label("흐름 제어", "heading"))
    for title, color in (("▶  시험 시작", "#28a078"), ("↻  횟수 반복", "#d59a33"), ("◷  시간 대기", "#5c9fba")):
        item = label(title)
        item.setStyleSheet(f"color: {color}; background: #f7f9fc; border-left: 4px solid {color}; border-radius: 6px; padding: 10px;")
        palette.body.addWidget(item)
    palette.body.addSpacing(3)
    palette.body.addLayout(row(label("ICD 메시지", "heading"), chip("05", "neutralChip")))
    palette.body.addWidget(label("Receiver_ICD_v0.1.xlsx", "caption"))
    for name, description in (("SET_FREQUENCY", "주파수 설정"), ("REQUEST_STATUS", "상태 조회"), ("STATUS_RESPONSE", "상태 응답"), ("COMMAND_ACK", "명령 응답"), ("SPECTRUM_DATA", "스펙트럼 데이터")):
        item = label(f"{description}\n{name}")
        item.setStyleSheet("color: #4165bd; background: #eff4ff; border-left: 4px solid #4a71dd; border-radius: 6px; padding: 8px; font-size: 11px;")
        palette.body.addWidget(item)
    palette.body.addStretch()
    palette.body.addWidget(label("ICD 가져오기 → 메시지 블록 생성", "caption"))
    panels.addWidget(palette, 22)

    canvas_card = Card()
    canvas_card.body.setContentsMargins(12, 12, 12, 12)
    canvas_header = row(label("블록 조립 영역", "heading"))
    canvas_header.addStretch()
    canvas_header.addWidget(chip("100%", "neutralChip"))
    canvas_card.body.addLayout(canvas_header)
    canvas_card.body.addWidget(BlockCanvas(), 1)
    canvas_card.body.addWidget(label("선택한 블록: 01 · 주파수 설정", "caption"))
    panels.addWidget(canvas_card, 49)

    inspector = Card("블록 설정", "01")
    inspector.setMinimumWidth(300)
    inspector.body.addWidget(label("ICD 메시지 송신", "heading"))
    inspector.body.addWidget(label("SET_FREQUENCY", "muted"))
    inspector.body.addWidget(label("송신 소켓", "caption"))
    target = QComboBox()
    target.addItem("TCP-01 · 수신기 A")
    inspector.body.addWidget(target)
    inspector.body.addWidget(label("Local    192.168.0.100:52001\nRemote  192.168.0.10:5000", "caption"))
    inspector.body.addSpacing(6)
    inspector.body.addWidget(label("ICD 헤더", "heading"))
    form = QFormLayout()
    form.setVerticalSpacing(9)
    for name, value in (("SRC", "0xAAAA"), ("DST", "0xBBBB"), ("CMD", "0xCCCC")):
        edit = QLineEdit(value)
        edit.setReadOnly(True)
        form.addRow(label(name, "muted"), edit)
    inspector.body.addLayout(form)
    inspector.body.addSpacing(6)
    inspector.body.addWidget(label("메시지 필드", "heading"))
    fields = QFormLayout()
    fields.setVerticalSpacing(9)
    for name, value in (("중심 주파수", "1,000 MHz"), ("대역폭", "20 MHz"), ("채널", "CH 1")):
        edit = QLineEdit(value)
        edit.setReadOnly(True)
        fields.addRow(label(name, "muted"), edit)
    inspector.body.addLayout(fields)
    inspector.body.addStretch()
    context = QFrame()
    context.setObjectName("inset")
    context_layout = QVBoxLayout(context)
    context_layout.setSpacing(7)
    context_layout.addWidget(label("포함된 반복", "heading"))
    context_layout.addWidget(label("10회 반복 · 활동 3개", "muted"))
    note = label("이 메시지는 반복 블록 안에서\n총 10번 수행됩니다.", "caption")
    context_layout.addWidget(note)
    inspector.body.addWidget(context)
    panels.addWidget(inspector, 29)
    layout.addLayout(panels, 1)
    return page
