"""PyInstaller entry point; independent of the user's working directory."""
from ds_simulator.app import main

if __name__ == '__main__':
    raise SystemExit(main())
