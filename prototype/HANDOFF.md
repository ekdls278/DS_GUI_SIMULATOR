# 다음 작업자를 위한 인수인계

한국어로 소통하고 기존 Python/PySide6 Windows 데스크톱 화면을 이어서 개발합니다.
사용자는 GUI 시안 검토 이후, 조작 가능한 기본 프로토타입 구현을 요청했습니다.
이번 범위는 **블록 편집과 모의 실행**입니다. 실제 장비 연결이나 wire 규격은 아직 정하지 않았습니다.

## 현재 상태

- README의 첫 사용 순서와 현재 범위를 먼저 확인하세요.
- 기존 화면을 유지하고 Qt 기본 위젯 기반 시나리오 편집기를 추가했습니다.
- 송신·대기·반복 블록 추가, 순서 변경, 반복 안팎 이동, 중첩, 삭제, 속성 편집이 가능합니다.
- `domain.py`는 Qt 독립 모델, 예시 필드 검사, 버전 있는 시나리오 JSON, 원자적 JSON 저장을 담당합니다.
- `runtime.py`는 수동/시나리오 공통 MockTransport와 QTimer 기반 실행기입니다.
  대기 중 취소, 실행 스냅샷, 사전 대상 검사, 실행 중 소켓 해제 오류를 처리합니다.
- `activity.py`는 실제 입력값을 담은 MOCK 로그와 필터·상세·JSON/CSV 내보내기를 담당합니다.
  모의 수신은 명시적인 예시 버튼으로만 만듭니다. 자동 장비 응답이나 합격 판정은 없습니다.
- `profiles.py`는 연결 설정 저장/복원입니다. 연결 상태를 복원하지 않습니다.
- 시나리오 JSON은 sample-1 예시 ICD와 버전 1을 사용합니다. 실제 ICD 호환 형식이 아닙니다.
- 시나리오에서 TCP 서버는 Accepted 소켓 ID를 지정합니다. 재시작 후 재선택이 필요합니다.
- `examples/`의 시나리오와 연결 설정은 기본값을 복원하는 데 사용할 수 있습니다.

## Windows 패키징

`.github/workflows/windows-executable.yml`은 Windows x64에서 22개 테스트를 실행하고
`packaging/build_windows.py`로 PyInstaller onefile EXE를 만듭니다. EXE 파일 하나만 새 임시 폴더에 복사하여
workspace/scenario PNG 생성을 확인한 뒤 EXE·SHA-256을 GitHub prerelease에 올립니다.
Python 설치, 압축 해제, 추가 폴더 없이 EXE 하나로 실행합니다.
실제 장비와 Windows 대화형 GUI의 모든 조작을 검증하는 과정은 별도로 필요합니다.

## 다음 단계

1. Windows에서 화면 크기, 드래그 이동, 네이티브 파일 대화상자를 수동 검토합니다.
2. 실제 Excel/JSON과 패킷 예시로 필드 길이·타입·순서·엔디언·프레이밍을 확정합니다.
3. 공통 ICD 모델과 Excel 변환, 실제 전송 계층을 추가합니다.
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
22개 테스트가 있으며 Linux Qt offscreen에서 통과했습니다.
현재 UI 캡처: `docs/prototype-workspace.png`, `docs/prototype-scenario.png`.
Windows 대화형 수동 조작·실장비·10G·FFT·계측기 검증은 아직 수행하지 않았습니다.
Windows CI에서 전체 테스트와 frozen EXE의 offscreen 실행을 검사합니다.
Windows에서 CSV 줄바꿈이 중복 변환되던 오류를 newline=""로 수정했으며 기존 내보내기 검사에 회귀 검증을 추가했습니다.
현재 마우스 드래그 자체는 자동화하지 않았으며 이동 버튼/모델 순서/저장 복원을 검사했습니다.

설치는 `uv sync --locked`, 실행은 `uv run ds-simulator`입니다.
이 프로토타입의 작업 디렉터리는 `/workspace/DS_GUI_SIMULATOR/prototype`입니다.
현재 cloud 작업은 이미 격리된 checkout을 사용합니다. 별도 Git worktree를 만들 필요가 없습니다.
소스 ZIP에는 `.git`, `.venv`, 캐시, 비밀 설정을 넣지 않습니다.
