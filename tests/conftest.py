"""Aislar intérpretes Tcl/Tk nativos, igual que cada ejecución de escritorio."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

def pytest_configure(config):
    config.addinivalue_line('markers', 'desktop: prueba con una instancia nativa de la aplicación')

@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    if pyfuncitem.get_closest_marker('desktop') and not os.environ.get('TRESVIZO_DESKTOP_TEST'):
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', pyfuncitem.nodeid],
            cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'TRESVIZO_DESKTOP_TEST': '1'},
            capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout+'\n'+result.stderr
        return True
