DS Simulator - Windows x64 prototype

실행 방법
1. ZIP 전체를 원하는 폴더에 압축 해제합니다.
2. DS-Simulator 폴더의 DS-Simulator.exe를 더블클릭합니다.
3. Python, VS Code, CMD 파일은 필요하지 않습니다.

DS-Simulator.exe와 _internal 폴더를 함께 유지하세요.
ZIP 안에서 바로 실행하거나 EXE만 다른 곳으로 옮기지 마세요.

첫 사용
- ICD 송수신: TCP-01을 선택하고 연결을 누른 뒤 ICD 메시지를 선택합니다.
- 필드값을 수정하고 송신을 누르면 MOCK 로그가 기록됩니다.
- 시나리오: 블록 추가·이동·속성 편집 후 모의 실행할 수 있습니다.
- 기본 예제는 주파수 설정 → 500ms 대기 → 상태 조회를 10회 반복합니다.
- examples 폴더에 연결 설정과 시나리오 JSON 예제가 있습니다.
- 저장 파일은 사용자가 파일 대화상자에서 선택한 위치에 저장됩니다.

이 버전은 모의 프로토타입입니다.
실제 TCP/UDP 장비 연결, Excel ICD 변환, 계측기 제어, FFT는 구현하지 않았습니다.
스펙트럼은 정적 예시이며 실제 장비 측정 결과가 아닙니다.

검증 정보
build-info.json에서 빌드 커밋·도구 버전과 패키징된 EXE의 화면 실행 검사 결과를 확인할 수 있습니다.
검사는 GUI를 화면 밖에서 렌더링하는 방식이며 실제 장비 시험을 의미하지 않습니다.

소스: https://github.com/ekdls278/DS_GUI_SIMULATOR/tree/main/prototype
