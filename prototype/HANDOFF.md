# 다음 작업자를 위한 인수인계

한국어로 소통하고 기존 Python/PySide6 Windows 데스크톱 화면을 이어서 개발합니다.
사용자는 GUI 시안 검토 이후, 조작 가능한 기본 프로토타입 구현을 요청했습니다.
현재 범위는 **실제 IPv4 TCP 서버·클라이언트 및 UDP의 원문 송수신**과 기존 모의 시험입니다. ICD wire 규격은 아직 정하지 않았습니다.

## 실제 통신 구조

기본 실행은 LIVE이고 모든 프로파일이 미연결입니다. 기존 GUI 테스트는 `SimulatorWindow(mock=True)`로 예시 상태를 명시합니다.
상단 모드 전환은 모든 실제/모의 소켓과 서버 선택을 해제하고 로그의 모드 표시는 유지합니다. 실행 중 전환은 막습니다.
`network.py`는 QTcpServer/QTcpSocket/QUdpSocket을 사용합니다. 장치 주소는 직접 연결하므로 Qt HTTP/application proxy를 사용하지 않습니다.
연결 시 실제 getsockname에 해당하는 Local/Remote를 조회하며 TCP 접속 시간 초과는 10초입니다.
수신은 자동으로 LIVE 로그에 들어갑니다. TCP 한 로그는 최대 64KiB 읽기 조각, UDP 한 로그는 데이터그램입니다. ICD 경계를 추정하지 않습니다.
TCP 읽기 버퍼 1MB, 송신 대기 버퍼 1MB, 서버당 클라이언트 64개, 한 번 송신 64KiB(UDP 65,507B) 제한입니다. 고속 수신은 별도 설계가 필요합니다.
TX 상태 QUEUED/OS_ACCEPTED는 송신 버퍼/운영체제 접수이지 상대 수신 보장이 아닙니다.
현재 Excel A~E만으로는 바이너리 ICD를 만들 수 없으므로 실제 모드의 기존 ICD send 블록은 사전 거부합니다. 임의 JSON·바이트 헤더를 장치로 보내지 않습니다.
`Step(kind='raw', wire_format='hex'|'utf8', wire_data=...)`와 직접 송신 UI가 명시한 바이트만 전송합니다. raw 시나리오는 version 3, 기존 v1/2 호환을 유지합니다.
수동/시나리오는 같은 전송 계층을 사용하며 실행 시작 시 대상 소켓 ID를 고정합니다. 재접속으로 ID가 바뀌면 기존 블록을 재선택해야 합니다.
`network_check.py`는 패키징 전용 CLI `--network-self-test REPORT`로 Qt와 Python socket 사이의 실제 루프백을 검사합니다. 회사 파일/실장비를 사용하지 않습니다.
`validation/network-check.json`과 EXE SHA-256으로 Windows 결과를 확인합니다.

## 현재 상태

- README의 첫 사용 순서와 현재 범위를 먼저 확인하세요.
- 기존 화면을 유지하고 Qt 기본 위젯 기반 시나리오 편집기를 추가했습니다.
- 송신·대기·반복 블록 추가, 순서 변경, 반복 안팎 이동, 중첩, 삭제, 속성 편집이 가능합니다.
- `domain.py`는 Qt 독립 모델, 예시 필드 검사, 버전 있는 시나리오 JSON, 원자적 JSON 저장을 담당합니다.
- `runtime.py`는 수동/시나리오 공통 TransportRouter(LIVE/MOCK)와 QTimer 기반 실행기입니다.
  대기 중 취소, 실행 스냅샷, 사전 대상 검사, 실행 중 소켓 해제 오류를 처리합니다.
- `activity.py`는 실제 원문/입력값과 LIVE/MOCK 구분을 담은 로그와 필터·상세·JSON/CSV 내보내기를 담당합니다.
  모의 수신은 명시적인 예시 버튼으로만 만듭니다. 자동 장비 응답이나 합격 판정은 없습니다.
- `profiles.py`는 연결 설정 저장/복원입니다. 연결 상태를 복원하지 않습니다.
- 시나리오 JSON은 기본 예시 version 1과 가져온 ICD 정의를 포함한 version 2, 직접 송신을 담은 version 3을 지원합니다. 실제 wire 규격은 아직 미정입니다.
- 시나리오에서 TCP 서버는 Accepted 소켓 ID를 지정합니다. 재시작 후 재선택이 필요합니다.
- `examples/`의 시나리오와 연결 설정은 기본값을 복원하는 데 사용할 수 있습니다.

## Windows 패키징

`.github/workflows/windows-executable.yml`은 Windows x64에서 76개 테스트를 실행하고
`packaging/build_windows.py`로 PyInstaller onefile EXE를 만듭니다. EXE 파일 하나만 새 임시 폴더에 복사하여
workspace/scenario/logs/spectrum/excel-import PNG와 frozen EXE의 실제 TCP/UDP 루프백 왕복을 확인한 뒤 EXE·SHA-256을 GitHub prerelease에 올립니다.
Python 설치, 압축 해제, 추가 폴더 없이 EXE 하나로 실행합니다.
실제 장비와 Windows 대화형 GUI의 모든 조작을 검증하는 과정은 별도로 필요합니다.

## 서버 소켓 트리

`connection_cards.py`의 ConnectionCard/PeerTree를 통합 송수신 화면에 사용합니다.
모든 역할을 공통 카드로 표시합니다. 역할 배지, 상태 배지, 선택 강조를 분리했습니다.
서버만 굵은 테두리를 쓰지 않으며 선택한 연결만 공통 파란 테두리·배경을 사용합니다.
서버의 Accepted 트리는 유지하고 현재 선택된 행에 송신 대상을 명시합니다.
`selected_peers[connection_id]`가 선택의 기준이며 별도의 클라이언트 콤보박스는 제거했습니다.
상위 서버 헤더를 클릭하면 하위 선택을 해제합니다. 프로파일 복원 시 카드 전체를 교체합니다.
정확한 송신 대상, 다중 서버, 서버 중지/재시작, 접속 소멸, 프로파일 복원 GUI 검사를 추가했습니다.
전체 역할의 화면 예시는 `docs/prototype-socket-cards.png`, 다중 서버는 `docs/prototype-server-tree.png`에 있습니다. 실제 모드에서는 외부 접속이 트리에 자동 반영됩니다.

## 로그와 스펙트럼 창

스펙트럼은 `open_spectrum()`에서 비모달 QDialog를 한 개만 만들고 닫을 때는 숨깁니다.
메인 창 종료 시 팝업도 닫습니다. PAGE_NAMES의 ID 3은 팝업, 4는 시나리오, 5는 로그입니다.
`page_indices`가 실제 QStackedWidget 인덱스로 변환하므로 navigation ID를 stack에 직접 쓰지 마세요.
`--page spectrum --screenshot`은 팝업 자체를 캡처합니다.

`initialize_activity()`에서 TransportRouter의 송신/수신 신호를 한 번만 연결합니다.
수집은 `TrafficHistory`와 최신 2,000건 로그에 즉시 반영하고, 테이블과 모니터는 100ms 간격으로 표시합니다.
`traffic.py`의 누적/초당 건수는 개별 로그가 버퍼에서 제거돼도 유지됩니다. 초당 버킷은 최근 120개만 유지합니다.
타임라인 일시정지는 snapshot만 고정하며 실제 수집/시나리오/전용 로그에 영향을 주지 않습니다.
서버는 Accepted 소켓별로 줄을 나누고, 고빈도 스펙트럼과 겹치는 메시지는 묶어 표시합니다.
메시지 그룹 클릭 시 최근 100건의 상세를 표시합니다. 요청-응답 추정이나 자동 판정은 없습니다.
전용 로그는 새 기록이 들어와도 선택된 상세를 유지하고, 선택한 기록이 버퍼에서 제거되면 해제합니다.
새 화면은 docs/prototype-traffic-monitor.png, prototype-logs.png, prototype-spectrum-popup.png에 있습니다.

## Excel ICD 가져오기

`icd.py`는 openpyxl read-only로 선택한 `(데이터)` 워크시트의 2행부터 A~E열만 읽습니다.
A=opcode, B=연동자료명, C=순번, D=데이터 요소, E=공백 구분 선택값입니다.
같은 메시지의 빈 A/B와 병합 셀을 이어 읽고, 새 opcode의 이름이 없으면 잘못 이어 붙이지 않고 행 번호를 안내합니다.
데이터 타입·바이트 길이·선택값의 숫자 의미를 추정하지 않습니다. E가 비면 자유 텍스트입니다.
수식은 실행하지 않고 formula/data-only read-only 뷰를 나란히 읽어 Excel이 저장한 계산 결과를 사용합니다.
계산 결과가 없는 수식은 빈칸처럼 이어 붙이지 않고 재계산·저장을 안내합니다. Excel 오류 값도 거부합니다.
문자열 빈 결과와 캐시 없는 수식을 구별하고 숫자 0 및 zero padding을 보존합니다.
캐시의 최신 여부는 확인할 수 없으므로 최신 값은 Excel에서 재계산·저장해야 합니다.
실제 회사 데이터가 아닌 가상 워크북만 테스트/배포에 사용합니다. Windows frozen 검사도 가상 A2 수식의 저장된 결과를 읽습니다.

활성 ICD는 `window.messages`에만 보관하며 전역 MESSAGES를 수정하지 않습니다.
`IcdMixin.apply_catalog()`는 수동 목록과 정의 화면을 교체하고 기본적으로 시나리오를 새 시험으로 만듭니다.
사용자 파일 선택·시트 선택 취소와 파싱 실패는 기존 상태를 유지합니다. 실행 중인 시나리오가 있으면 가져오기를 막습니다.
수동/시나리오 모두 `icd_widgets.py`의 입력을 사용합니다. 가져온 메시지는 SRC/DST를 임의로 채우지 않고 opcode만 정의로 사용합니다.
도메인 함수와 MockTransport는 카탈로그를 주입받습니다. 로그에는 연동자료명과 이름이 있는 data_elements도 기록합니다.
시나리오 version 2/3은 가져온 ICD 정의와 fingerprint를 포함합니다. version 1 기본 예시와 호환됩니다.
JSON 로드 시 카탈로그도 복원하며 트리 재구성 중 선택 신호를 막아 이전 ICD 콜백이 남지 않도록 합니다.
원본 파일을 복사하거나 네트워크로 올리지 않습니다. 사용자가 선택한 시나리오 저장에는 ICD 내용이 포함되며 기존 2MB 제한이 있습니다.

## 다음 단계

1. Windows에서 화면 크기, 드래그 이동, 네이티브 파일 대화상자를 수동 검토합니다.
2. 사용자가 공유 가능한 메타데이터로 필드 길이·타입·순서·엔디언·프레이밍을 확정합니다. 실제 회사 Excel을 요청하거나 저장소에 포함하지 마세요.
3. 현재 A~E열 가져오기 모델을 확장하고 장치 규격에 맞는 ICD 인코더·디코더를 추가합니다.
4. 모의 상대와 실제 TCP/UDP를 검증한 뒤 시나리오에 응답 대기·판정을 추가합니다.
5. 실제 스펙트럼 형식과 계측기 명령을 받은 뒤 해당 기능을 구현합니다.

Blockly + QtWebEngine/QWebChannel은 검토 후보였으며 아직 도입하지 않았습니다.
현재는 추가 의존성 없이 편집기/실행기를 분리한 기본 프로토타입입니다.
스펙트럼은 정적 QPainter 예시이며 실제 FFT나 수신 결과가 아닙니다.
최소·최대 입력 검사는 예시 자료형 기준이며 장치의 실제 허용 범위를 뜻하지 않습니다.
빅엔디안 체크는 설정만 기록합니다. 실제 패킷 바이트를 만들지 않습니다.

## 성능과 검증

PySide6-Essentials 6.8.3을 유지했습니다. 6.12에서 종료 불안정이 관찰됐다는 기존 기록이 있습니다.
64KB × 초당 250개는 약 16MB/s, 시간당 약 57.6GB입니다. 성능 보장은 없습니다.
UDP IPv4 단일 페이로드 최대 65,507바이트이므로 64KiB 메시지는 하나에 담을 수 없습니다.
고속 수신은 수신/해석/저장/화면 갱신 분리 및 실제 Windows 부하 시험이 필요합니다.

검증: `QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests -v`
실제 루프백 15개를 포함해 76개 테스트가 있으며 Linux Qt offscreen에서 통과했습니다.
현재 UI 캡처: `docs/prototype-workspace.png`, `docs/prototype-scenario.png`.
Windows 대화형 수동 조작·실장비·10G·FFT·계측기 검증은 아직 수행하지 않았습니다.
Windows CI에서 전체 테스트와 frozen EXE의 offscreen 실행을 검사합니다.
Windows에서 CSV 줄바꿈이 중복 변환되던 오류를 newline=""로 수정했으며 기존 내보내기 검사에 회귀 검증을 추가했습니다.
현재 마우스 드래그 자체는 자동화하지 않았으며 이동 버튼/모델 순서/저장 복원을 검사했습니다.

설치는 `uv sync --locked`, 실행은 `uv run ds-simulator`입니다.
이 프로토타입의 작업 디렉터리는 `/workspace/DS_GUI_SIMULATOR/prototype`입니다.
현재 cloud 작업은 이미 격리된 checkout을 사용합니다. 별도 Git worktree를 만들 필요가 없습니다.
소스 ZIP에는 `.git`, `.venv`, 캐시, 비밀 설정을 넣지 않습니다.
