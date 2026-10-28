# 다음 작업자를 위한 인수인계

이 문서는 기존 대화의 작업 요약이며 대화 원문은 아닙니다. 코드와 GUI 이미지의 현재 상태를 함께 전달합니다.

## 다음 작업 시작 방법
먼저 이 문서와 소스를 읽고 현재 구현 상태를 확인하세요. 사용자는 GUI 검토 단계입니다. 명시적인 추가 요청 없이 실제 통신이나 시나리오 실행을 구현하지 마세요. 한국어로 소통하고 기존 화면을 이어서 수정하세요. 현재 코드와 이 문서를 함께 참고하세요.

## 목적과 요구사항
Windows PC에서 실행할 확장 가능한 장비 모의 소프트웨어입니다.
- 복수 TCP/UDP 클라이언트, TCP 서버 통신.
- Excel ICD 가져오기, ICD 선택 및 필드 편집 후 메시지 송신.
- ICD 헤더 예: SRC 0xAAAA, DST 0xBBBB, CMD 0xCCCC. 필드 길이, 엔디언, 패킷 구조는 미정.
- ICD 수신으로 BIT 상태와 스펙트럼 표시, 데이터 저장. 실제 수신 형식은 사용자가 프로토타입 진행 중 제공 예정.
- 연결별 Local IP/Port와 Remote IP/Port를 명확히 표시. 서버 Listen 소켓과 Accepted 소켓 구분.
- 소켓 현황과 ICD 메시지는 같은 화면: 왼쪽 소켓 선택 → 연결 → ICD 선택 → 송신. 이미 연결된 소켓은 연결 단계를 생략.
- 가장 중요한 후속 기능은 Scratch 형태의 블록형 시나리오 편집과 자동 시험. ICD를 가져오면 메시지 블록 생성. 각 활동 또는 활동 묶음 반복 지원. 추후 신호 발생기 제어와 추가 요구사항 예정.

## 현재 구현 범위
Python + PySide6로 GUI 프로토타입만 구현했습니다. 소켓 연결/해제, 송신은 메모리상의 예시 상태 전환이며 실제 네트워크 작업을 하지 않습니다. Excel 파싱, 실수신, 저장, 실제 FFT, 장비 제어, 시나리오 실행은 미구현입니다.
- ICD 송수신: 소켓 목록, 연결 상태, ICD 목록, SRC/DST/CMD 및 예시 페이로드 편집, 송신 미리보기, 로그.
- 소켓 상세: Local/Remote, Listen/Accepted 구분, 필터, 송신 대상으로 선택.
- ICD 정의와 정적 스펙트럼 화면.
- 연결 추가 대화상자와 예시 서버 클라이언트 접속.
- 시나리오: 왼쪽 블록 팔레트, 가운데 반복 블록, 오른쪽 소켓/ICD 필드 속성. 주파수 설정 → 500ms 대기 → 상태 조회를 10회 반복하는 정적 시안.
- 시나리오 블록은 QPainter로 그린 화면입니다. 드래그/조립, 자동 블록 생성, 실행은 구현하지 않았습니다. 시나리오 속성은 실제 연결 상태와 별개인 고정 예시입니다.
- 송신 대상 변경 시 ICD 선택을 초기화합니다. 서버 Listen 소켓으로 송신할 수 없으며 Accepted 소켓을 선택합니다. ICD DST는 네트워크 소켓을 변경하지 않습니다.

## 개발 방향 및 성능 논의
현재 설치 의존성은 PySide6-Essentials 6.8.3뿐입니다. 향후 NumPy/PyQtGraph, openpyxl, PyVISA 등을 검토했습니다. Blockly를 QtWebEngine/QWebChannel로 임베딩하고 Python 실행 엔진을 분리하는 방향을 추천했지만 아직 도입하지 않았습니다. QtWebEngine에는 추가 의존성이 필요합니다.
64KB 메시지 초당 250개는 약 16MB/s, 시간당 57.6GB입니다(64KiB라면 약 16.384MB/s). 스택의 성능은 수신/파싱/저장/화면 갱신 분리, 바이너리 일괄 저장, 제한된 큐, 화면 갱신 20~30fps 등 실제 설계와 Windows 부하 시험에 달려 있습니다. 성능 보장 또는 벤치마크 결과는 없습니다. UDP IPv4 단일 데이터그램 최대 페이로드 65507바이트이므로 64KiB는 하나에 담을 수 없습니다. 실제 메시지 형식, FFT 조건, 연결별/총 데이터율은 미정입니다.

## 파일 안내
- src/ds_simulator/app.py: 창, 페이지 이동, 소켓 상세, ICD 정의, 스펙트럼, 연결 설정, 실행 CLI.
- workspace.py: 통합 소켓/ICD 송수신 화면과 예시 상태 관리.
- preview_data.py: 연결/소켓/ICD 샘플 데이터.
- scenario_preview.py: 정적 블록 시나리오 화면.
- widgets.py, theme.py: 공통 위젯, 정적 그래프, 스타일.
- docs/ui-scenario.png: 최신 시나리오 시안.
- docs/ui-workspace.png: 통합 송수신 화면의 송신 준비 상태.
- docs/ui-before-connect.png: 연결 전 상태.
- 나머지 이미지 일부는 이전 단계 캡처이며 최신 내비게이션과 차이가 있을 수 있습니다.

## 실행
Windows Python 3.12 권장:
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m ds_simulator.app
```
uv 사용 시 `uv sync --locked`, `uv run ds-simulator`.
Linux 무화면 캡처 예:
```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m ds_simulator.app --page scenario --screenshot docs/ui-scenario.png
```
페이지: workspace, sockets, icd, spectrum, scenario.
송수신 예시 상태: --preview-stage initial / connected / ready.

## 검증 및 전달 상태
Linux Qt offscreen으로 화면 캡처 및 예시 연결/해제, 대상 변경, ICD 선택, HEX 유효성, 필터, 서버 Accepted 선택 흐름을 확인했습니다. 영구 테스트 파일은 없으며 Windows 실기 검증은 하지 않았습니다. PySide6 6.12에서 종료 불안정이 관찰되어 6.8.3으로 고정했습니다.
원본 저장소: ekdls278/DS_GUI_SIMULATOR, main. GUI 소스, 화면 이미지, 이 인수인계 문서를 함께 버전 관리합니다. 새 작업자는 이 문서가 포함된 최신 커밋을 가져와 시작하세요. ZIP에는 .git, .venv, 캐시, 비밀 설정을 포함하지 않습니다.

## 마지막 진행 상황
사용자가 개발 전에 시나리오 GUI만 요청했고 docs/ui-scenario.png를 제공했습니다. 그 다음 공유 링크가 스크롤 중 흰 화면이 되는 문제 때문에 다른 계정으로 작업을 이어갈 방법을 요청하여 이 인수인계 패키지를 만들었습니다. 다음 단계는 사용자의 GUI 피드백 또는 후속 요구사항을 받아 진행하는 것입니다.
