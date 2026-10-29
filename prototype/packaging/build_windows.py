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
    for package in ('PySide6-Essentials', 'shiboken6', 'PyInstaller'):
        package_distribution = distribution(package)
        for file in package_distribution.files or []:
            if 'license' in str(file).lower() or 'copying' in str(file).lower():
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

    (validation / 'build-info.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with executable.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    executable.with_suffix('.exe.sha256').write_text(f'{checksum}  {executable.name}\n', encoding='ascii')
    print(f'Created and tested standalone EXE: {executable} ({executable.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
