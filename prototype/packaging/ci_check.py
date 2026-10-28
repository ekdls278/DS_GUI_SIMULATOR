"""Preserve command exit status and expose useful failure diagnostics in Actions annotations."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    label, *arguments = sys.argv[1:]
    environment = dict(os.environ)
    environment['PYTHONUTF8'] = '1'
    result = subprocess.run([sys.executable, *arguments], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8', errors='replace')
    print(output, end='', flush=True)
    destination = Path('dist/validation')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f'{label}.log').write_text(output, encoding='utf-8')
    if result.returncode:
        details = '\n'.join(output.splitlines()[-55:])
        details = details.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error title={label} failed::{details}', flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
