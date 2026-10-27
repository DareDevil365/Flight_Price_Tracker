"""Run the complete suite in a disposable copy, protecting profiles and models."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='flight-finder-tests-') as temporary:
    target=Path(temporary)/'project'
    shutil.copytree(root,target,ignore=shutil.ignore_patterns(
        '.git','.venv','venv','node_modules','dist','sessions','logs','config',
        '__pycache__','.pytest_cache','.env','.env.*','*.db','*.db-wal','*.db-shm',
        '*.sqlite','*.sqlite3','*.png','*.jpg'))
    env={**os.environ,'FLIGHT_FINDER_DB':str(target/'isolated.db'),
         'FLIGHT_FINDER_CONFIG_DIR':str(target/'config')}
    result=subprocess.run([sys.executable,'-m','pytest','tests','-q',*sys.argv[1:]],
                          cwd=target/'backend',env=env)
    code=result.returncode
sys.exit(code)
