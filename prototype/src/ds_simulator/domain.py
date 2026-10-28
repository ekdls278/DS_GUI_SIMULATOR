"""UI-independent prototype models. No wire format or real device behavior implied."""

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from .preview_data import MESSAGES

CATALOG_VERSION = "sample-1"
MAX_ACTIONS = 10000


def default_values(name):
    return {key: value for key, _, value, _, _ in MESSAGES[name].fields}


def default_headers(name):
    message = MESSAGES[name]
    return {key: getattr(message, key) for key in ("src", "dst", "cmd")}


def validate_message(name, headers, values):
    """Validate sample types only; hardware-specific limits remain unspecified."""
    if name not in MESSAGES:
        raise ValueError(f"알 수 없는 ICD 메시지: {name}")
    if set(headers) != {"src", "dst", "cmd"}:
        raise ValueError("SRC / DST / CMD가 필요합니다.")
    for key, value in headers.items():
        if not isinstance(value, str) or not re.fullmatch(r"0[xX][0-9a-fA-F]+", value):
            raise ValueError(f"{key.upper()}: 0x로 시작하는 HEX 값을 입력하세요.")
    expected = {entry[0] for entry in MESSAGES[name].fields}
    if set(values) != expected:
        raise ValueError(f"{name}: ICD 필드 구성이 일치하지 않습니다.")
    parsed = {}
    for key, data_type, _, _, description in MESSAGES[name].fields:
        raw = values[key]
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{description}: 값을 입력하세요.")
        data_type = data_type.split()[0]
        try:
            if data_type.startswith("uint"):
                text = raw.strip()
                if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", text):
                    raise ValueError()
                value = int(text.replace(",", ""))
                if not 0 <= value < 2 ** int(data_type[4:]):
                    raise ValueError()
            elif data_type == "float32[]":
                value = [float(v.strip()) for v in raw.strip("[] ").split(",")]
                if not value or len(value) > 65536 or not all(math.isfinite(v) and abs(v) <= 3.402823466e38 for v in value):
                    raise ValueError()
            elif data_type == "float32":
                value = float(raw)
                if not math.isfinite(value) or abs(value) > 3.402823466e38:
                    raise ValueError()
            else:
                raise ValueError()
        except (ValueError, OverflowError):
            raise ValueError(f"{description}: {data_type} 형식과 범위를 확인하세요.") from None
        parsed[key] = value
    return parsed


@dataclass
class Step:
    kind: str
    id: str = field(default_factory=lambda: uuid4().hex)
    message: str = "SET_FREQUENCY"
    connection_id: str = "TCP-01"
    socket_id: str = ""
    headers: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    big_endian: bool = False
    count: int = 10
    milliseconds: int = 500
    children: list = field(default_factory=list)

    @classmethod
    def send(cls, name="SET_FREQUENCY"):
        return cls("send", message=name, headers=default_headers(name), values=default_values(name))


@dataclass
class Scenario:
    name: str = "주파수 설정 반복 시험"
    steps: list = field(default_factory=list)

    @classmethod
    def example(cls):
        return cls(steps=[Step("repeat", children=[Step.send(), Step("wait"), Step.send("REQUEST_STATUS")])])

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 200:
            raise ValueError("시험 이름을 1~200자로 입력하세요.")
        ids = set()

        def visit(steps, depth=0):
            if depth > 8 or not isinstance(steps, list):
                raise ValueError("반복 중첩은 8단계까지 지원합니다.")
            total = 0
            for step in steps:
                if not isinstance(step, Step) or step.kind not in ("send", "wait", "repeat"):
                    raise ValueError("지원하지 않는 블록입니다.")
                if not isinstance(step.id, str) or not step.id or step.id in ids:
                    raise ValueError("블록 ID가 비어 있거나 중복됩니다.")
                ids.add(step.id)
                if len(ids) > 1000:
                    raise ValueError("최대 1,000개 블록을 지원합니다.")
                if not isinstance(step.big_endian, bool):
                    raise ValueError("엔디언 설정이 올바르지 않습니다.")
                if step.kind != "repeat" and step.children:
                    raise ValueError("활동은 반복 블록 안에만 넣을 수 있습니다.")
                if step.kind == "repeat":
                    if type(step.count) is not int or not 1 <= step.count <= 1000:
                        raise ValueError("반복 횟수는 1~1,000 사이여야 합니다.")
                    total += step.count * visit(step.children, depth + 1)
                elif step.kind == "wait":
                    if type(step.milliseconds) is not int or not 0 <= step.milliseconds <= 600000:
                        raise ValueError("대기 시간은 0~600,000ms 사이여야 합니다.")
                    total += 1
                else:
                    if not isinstance(step.connection_id, str) or not step.connection_id or not isinstance(step.socket_id, str):
                        raise ValueError("송신 대상을 선택하세요.")
                    validate_message(step.message, step.headers, step.values)
                    total += 1
                if total > MAX_ACTIONS:
                    raise ValueError(f"시험당 최대 {MAX_ACTIONS:,}개 활동을 지원합니다.")
            return total

        return visit(self.steps)

    def to_dict(self):
        self.validate()
        return {"format": "ds-scenario", "version": 1, "catalog": CATALOG_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "ds-scenario" or type(data.get("version")) is not int or data["version"] != 1 or data.get("catalog") != CATALOG_VERSION:
            raise ValueError("지원하는 시나리오 파일(sample-1, version 1)이 아닙니다.")
        nodes = 0

        def parse(items, depth=0):
            nonlocal nodes
            if depth > 8 or not isinstance(items, list):
                raise ValueError("블록 구조가 올바르지 않습니다.")
            result = []
            for item in items:
                nodes += 1
                if nodes > 1000 or not isinstance(item, dict):
                    raise ValueError("블록 개수 또는 형식이 올바르지 않습니다.")
                values = dict(item)
                if "id" not in values or "kind" not in values:
                    raise ValueError("블록 ID와 종류가 필요합니다.")
                values["children"] = parse(values.get("children", []), depth + 1)
                try:
                    result.append(Step(**values))
                except TypeError:
                    raise ValueError("알 수 없는 블록 속성입니다.") from None
            return result

        try:
            scenario = cls(data["name"], parse(data["steps"]))
            scenario.validate()
        except (KeyError, TypeError, AttributeError, RecursionError):
            raise ValueError("시나리오 파일 구조가 올바르지 않습니다.") from None
        return scenario


def iter_actions(steps):
    """Lazy execution; repeat blocks do not allocate expanded action lists."""
    for step in steps:
        if step.kind == "repeat":
            for _ in range(step.count):
                yield from iter_actions(step.children)
        else:
            yield step


def save_json(path, data):
    """Replace only after a complete UTF-8 write; preserve existing file on failure."""
    path = Path(path)
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(content + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_scenario(path):
    if Path(path).stat().st_size > 2_000_000:
        raise ValueError("시나리오 파일은 2MB 이하여야 합니다.")
    try:
        return Scenario.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))
    except (RecursionError, UnicodeError):
        raise ValueError("시나리오 JSON을 읽을 수 없습니다.") from None
