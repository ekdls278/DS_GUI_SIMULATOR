"""Display samples only. These are not network sessions or a wire specification."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionPreview:
    identifier: str
    name: str
    mode: str
    local_endpoint: str
    remote_endpoint: str = ""

    @property
    def endpoint(self) -> str:
        return self.local_endpoint if self.mode == "TCP Server" else self.remote_endpoint

    @property
    def title(self) -> str:
        return f"{self.identifier} · {self.name}"


CONNECTIONS = (
    ConnectionPreview("TCP-01", "수신기 A", "TCP Client", "0.0.0.0:0", "192.168.0.10:5000"),
    ConnectionPreview("TCP-02", "수신기 B", "TCP Client", "0.0.0.0:0", "192.168.0.11:5000"),
    ConnectionPreview("SRV-01", "외부 장치 접속", "TCP Server", "0.0.0.0:7000"),
    ConnectionPreview("UDP-01", "스펙트럼 수신", "UDP", "0.0.0.0:6000", "192.168.0.10:6001"),
)


@dataclass(frozen=True)
class SocketPreview:
    """Illustrative runtime endpoints, distinct from the configured bind address."""

    identifier: str
    connection_id: str
    role: str
    state: str
    local_ip: str
    local_port: int
    remote_ip: str = ""
    remote_port: int | None = None

    @property
    def local_endpoint(self) -> str:
        return f"{self.local_ip}:{self.local_port}"

    @property
    def remote_endpoint(self) -> str:
        return f"{self.remote_ip}:{self.remote_port}" if self.remote_ip else ""


# UI IDs, not OS socket handles. No system sockets are opened or inspected.
SOCKETS = (
    SocketPreview("SOCK-001", "TCP-01", "Client", "ESTABLISHED", "192.168.0.100", 52001, "192.168.0.10", 5000),
    SocketPreview("SOCK-002", "TCP-02", "Client", "ESTABLISHED", "192.168.0.100", 52002, "192.168.0.11", 5000),
    SocketPreview("SOCK-003", "SRV-01", "Listen", "LISTENING", "0.0.0.0", 7000),
    SocketPreview("SOCK-004", "SRV-01", "Accepted", "ESTABLISHED", "192.168.0.100", 7000, "192.168.0.21", 51001),
    SocketPreview("SOCK-005", "SRV-01", "Accepted", "ESTABLISHED", "192.168.0.100", 7000, "192.168.0.22", 51002),
    SocketPreview("SOCK-006", "UDP-01", "UDP", "BOUND", "0.0.0.0", 6000),
)


@dataclass(frozen=True)
class MessagePreview:
    description: str
    src: str
    dst: str
    cmd: str
    fields: tuple[tuple[str, ...], ...]

    def field_rows(self) -> list[list[str]]:
        # Hex display does not establish field width, byte order or byte offsets.
        return [
            ["src", "미정 / HEX", self.src, "—", "ICD 송신 식별자"],
            ["dst", "미정 / HEX", self.dst, "—", "ICD 수신 식별자"],
            ["cmd", "미정 / HEX", self.cmd, "—", "ICD 명령 코드"],
            *[list(field) for field in self.fields],
        ]


MESSAGES = {
    "SET_FREQUENCY": MessagePreview("주파수 설정", "0xAAAA", "0xBBBB", "0xCCCC", (
        ("center_frequency", "uint64 (예시)", "1,000,000,000", "Hz", "중심 주파수"),
        ("bandwidth", "uint32 (예시)", "20,000,000", "Hz", "수신 대역폭"),
        ("channel", "uint8 (예시)", "1", "—", "수신 채널"),
    )),
    "REQUEST_STATUS": MessagePreview("상태 조회", "0xAAAA", "0xBBBB", "0xCCCD", (
        ("channel", "uint8 (예시)", "1", "—", "조회할 채널"),
    )),
    "STATUS_RESPONSE": MessagePreview("상태 응답", "0xBBBB", "0xAAAA", "0xCCCE", (
        ("status", "uint8 (예시)", "READY", "—", "수신기 상태"),
        ("temperature", "float32 (예시)", "42.5", "°C", "장비 온도"),
    )),
    "COMMAND_ACK": MessagePreview("명령 응답", "0xBBBB", "0xAAAA", "0xCCCF", (
        ("result", "uint8 (예시)", "0", "—", "명령 처리 결과"),
    )),
    "SPECTRUM_DATA": MessagePreview("스펙트럼 데이터", "0xBBBB", "0xAAAA", "0xDDDD", (
        ("center_frequency", "uint64 (예시)", "1,000,000,000", "Hz", "중심 주파수"),
        ("bin_count", "uint16 (예시)", "1,024", "—", "주파수 구간 수"),
        ("levels", "float32[] (예시)", "예시 배열", "dBm", "주파수별 레벨"),
    )),
}

# Columns: time, direction, connection, peer, src, dst, cmd, message.
SAMPLE_LOG = [
    ["14:32:08.427", "RX", "TCP-01", "192.168.0.10:5000", "0xBBBB", "0xAAAA", "0xCCCE", "STATUS_RESPONSE"],
    ["14:32:08.403", "TX", "TCP-01", "192.168.0.10:5000", "0xAAAA", "0xBBBB", "0xCCCD", "REQUEST_STATUS"],
    ["14:32:08.320", "RX", "UDP-01", "192.168.0.10:6001", "0xBBBB", "0xAAAA", "0xDDDD", "SPECTRUM_DATA"],
    ["14:32:08.220", "RX", "SRV-01", "192.168.0.21:51001", "0xBBBB", "0xAAAA", "0xCCCF", "COMMAND_ACK"],
    ["14:32:07.891", "RX", "TCP-02", "192.168.0.11:5000", "0xBBBB", "0xAAAA", "0xCCCF", "COMMAND_ACK"],
    ["14:32:07.863", "TX", "TCP-02", "192.168.0.11:5000", "0xAAAA", "0xBBBB", "0xCCCC", "SET_FREQUENCY"],
]
