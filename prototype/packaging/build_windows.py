"""Build and smoke-test a native Windows x64 distribution. Run on Windows."""

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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'DS-Simulator'


def main():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Windows x64 Python is required. Use the Windows executable GitHub Actions workflow.')
    if sys.maxsize <= 2 ** 32:
        raise SystemExit('Use 64-bit Python.')
    command = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--windowed', '--noupx', '--name', NAME,
        '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / 'pyinstaller'),
        '--specpath', str(ROOT / 'build'), '--paths', str(ROOT / 'src'),
        str(ROOT / 'packaging' / 'launcher.py'),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    folder = ROOT / 'dist' / NAME
    executable = folder / f'{NAME}.exe'
    with executable.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise RuntimeError('The build did not produce a Windows PE executable.')

    # Execute the frozen program outside the checkout: source imports and cwd must not be required.
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    report = {
        'platform': platform.platform(), 'python': platform.python_version(),
        'pyinstaller': version('PyInstaller'), 'pyside6': version('PySide6-Essentials'),
        'commit': os.environ.get('GITHUB_SHA', 'local'), 'frozen_smoke_checks': [],
    }
    validation = ROOT / 'dist' / 'validation'
    validation.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ds-frozen-check-') as directory:
        for page in ('workspace', 'scenario'):
            screenshot = Path(directory) / f'{page}.png'
            subprocess.run(
                [str(executable), '--page', page, '--screenshot', str(screenshot)],
                cwd=directory, env=environment, check=True, timeout=90,
            )
            if not screenshot.is_file() or screenshot.stat().st_size < 1000 or screenshot.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError(f'Frozen application failed to render the {page} page.')
            shutil.copy2(screenshot, validation / screenshot.name)
            report['frozen_smoke_checks'].append({'page': page, 'result': 'passed'})

    shutil.copytree(ROOT / 'examples', folder / 'examples', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'packaging' / 'README-WINDOWS.txt', folder / 'README-WINDOWS.txt')
    shutil.copytree(ROOT / 'packaging' / 'licenses', folder / 'licenses', dirs_exist_ok=True)
    # Include any license files supplied by the installed distributions as well.
    for package in ('PySide6-Essentials', 'shiboken6', 'PyInstaller'):
        package_distribution = distribution(package)
        for file in package_distribution.files or []:
            if 'license' in str(file).lower() or 'copying' in str(file).lower():
                source = Path(package_distribution.locate_file(file))
                if source.is_file():
                    relative = Path(*[part for part in Path(str(file)).parts if part not in ('.', '..')])
                    destination = folder / 'licenses' / package / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, folder / 'licenses' / 'PYTHON-LICENSE.txt')
    report_text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    (folder / 'build-info.json').write_text(report_text, encoding='utf-8')
    (validation / 'build-info.json').write_text(report_text, encoding='utf-8')

    archive = ROOT / 'dist' / 'DS-Simulator-Windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                output.write(path, path.relative_to(folder.parent))
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:
            raise RuntimeError('ZIP integrity check failed.')
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'Created and smoke-tested: {archive} ({archive.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
