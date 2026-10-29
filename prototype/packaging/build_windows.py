"""Build and test one standalone Windows EXE; no adjacent files are required."""

import hashlib
from importlib.metadata import distribution, version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'DS-Simulator'


def main():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Windows x64 Python is required. Use the Windows executable GitHub Actions workflow.')
    if sys.maxsize <= 2 ** 32:
        raise SystemExit('Use 64-bit Python.')

    # Bundle notices and samples inside the EXE rather than requiring sibling folders.
    resources = ROOT / 'build' / 'onefile-resources'
    if resources.exists():
        shutil.rmtree(resources)
    resources.mkdir(parents=True)
    shutil.copytree(ROOT / 'examples', resources / 'examples')
    shutil.copytree(ROOT / 'packaging' / 'licenses', resources / 'licenses')
    shutil.copy2(ROOT / 'packaging' / 'README-WINDOWS.txt', resources / 'README-WINDOWS.txt')
    for package in ('PySide6-Essentials', 'shiboken6', 'PyInstaller', 'openpyxl', 'et-xmlfile', 'defusedxml'):
        package_distribution = distribution(package)
        for file in package_distribution.files or []:
            if any(word in str(file).lower() for word in ('license', 'licence', 'copying')):
                source = Path(package_distribution.locate_file(file))
                if source.is_file():
                    relative = Path(*[part for part in Path(str(file)).parts if part not in ('.', '..')])
                    destination = resources / 'licenses' / package / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, resources / 'licenses' / 'PYTHON-LICENSE.txt')

    report = {
        'platform': platform.platform(), 'python': platform.python_version(),
        'pyinstaller': version('PyInstaller'), 'pyside6': version('PySide6-Essentials'),
        'openpyxl': version('openpyxl'), 'defusedxml': version('defusedxml'),
        'commit': os.environ.get('GITHUB_SHA', 'local'),
        'packaging': 'onefile', 'frozen_smoke_checks': [],
    }
    (resources / 'build-info.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onefile', '--windowed', '--noupx', '--name', NAME,
        '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / 'pyinstaller'),
        '--specpath', str(ROOT / 'build'), '--paths', str(ROOT / 'src'),
        '--add-data', f'{resources}{os.pathsep}resources',
        str(ROOT / 'packaging' / 'launcher.py'),
    ], cwd=ROOT, check=True)
    executable = ROOT / 'dist' / f'{NAME}.exe'
    with executable.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise RuntimeError('The build did not produce a Windows PE executable.')

    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    validation = ROOT / 'dist' / 'validation'
    validation.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ds-standalone-check-') as directory:
        # Copy ONLY the EXE to a fresh directory: an onedir executable would fail here.
        standalone = Path(directory) / executable.name
        shutil.copy2(executable, standalone)
        for page in ('workspace', 'scenario', 'logs', 'spectrum'):
            screenshot = Path(directory) / f'{page}.png'
            subprocess.run(
                [str(standalone), '--page', page, '--screenshot', str(screenshot)],
                cwd=directory, env=environment, check=True, timeout=120,
            )
            if not screenshot.is_file() or screenshot.stat().st_size < 1000 or screenshot.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError(f'Standalone EXE failed to render the {page} page.')
            shutil.copy2(screenshot, validation / screenshot.name)
            report['frozen_smoke_checks'].append({'page': page, 'result': 'passed', 'standalone_copy': True})

        from openpyxl import Workbook
        network_report = Path(directory) / 'network-check.json'
        subprocess.run([str(standalone), '--network-self-test', str(network_report)],
                       cwd=directory, env=environment, check=True, timeout=90)
        network_result = json.loads(network_report.read_text(encoding='utf-8'))
        if network_result.get('result') != 'passed' or len(network_result.get('checks', [])) != 4:
            raise RuntimeError('Standalone EXE failed real TCP/UDP loopback validation.')
        shutil.copy2(network_report, validation / network_report.name)
        report['frozen_smoke_checks'].append({'page': 'network-loopback', 'result': 'passed', 'standalone_copy': True})
        workbook_path = Path(directory) / '가상-icd.xlsx'
        book = Workbook()
        sheet = book.active
        sheet.title = '가상 장치(데이터)'
        sheet.append(['opcode', '연동자료명', '순번', '데이터 요소', '고정 설명', '가상 자료형', '가상 크기', '가상 최소', '가상 최대', '가상 초기', '고정 비고', '미사용', '선택값'])
        sheet.append(['="0x0001"', '가상 모드 설정', 1, '운용 모드', '고정 0 1', 'uint8', 1, 0, 255, 0, '원본 유지', None,
                      '="중지 상태"&CHAR(10)&"자동 운용"'])
        book.save(workbook_path)
        book.close()
        # Synthetic fixture only: simulate Excel's saved string formula result.
        # openpyxl writes formulas but does not calculate or cache their results.
        with ZipFile(workbook_path) as archive:
            entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
        with ZipFile(workbook_path, 'w') as archive:
            for item, content in entries:
                if item.filename == 'xl/worksheets/sheet1.xml':
                    namespace = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                    root = ET.fromstring(content)
                    for cell in root.iter(namespace + 'c'):
                        if cell.attrib['r'] in ('A2', 'M2'):
                            cell.set('t', 'str')
                            cell.find(namespace + 'v').text = '0x0001' if cell.attrib['r'] == 'A2' else '중지 상태\n자동 운용'
                    content = ET.tostring(root, encoding='utf-8')
                archive.writestr(item, content)
        screenshot = Path(directory) / 'excel-import.png'
        subprocess.run([str(standalone), '--mock', '--icd-excel', str(workbook_path), '--icd-sheet', sheet.title,
                        '--preview-stage', 'ready', '--screenshot', str(screenshot)],
                       cwd=directory, env=environment, check=True, timeout=120)
        if not screenshot.is_file() or screenshot.stat().st_size < 1000 or screenshot.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
            raise RuntimeError('Standalone EXE failed to import the synthetic Excel ICD.')
        shutil.copy2(screenshot, validation / screenshot.name)
        report['frozen_smoke_checks'].append({'page': 'excel-import', 'result': 'passed', 'standalone_copy': True,
                                             'saved_formula_result': True, 'icd_layout': 'C:K-fixed/M-newline'})

    (validation / 'build-info.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with executable.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    executable.with_suffix('.exe.sha256').write_text(f'{checksum}  {executable.name}\n', encoding='ascii')
    print(f'Created and tested standalone EXE: {executable} ({executable.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
