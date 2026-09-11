"""Aislar intérpretes Tcl/Tk nativos, igual que cada ejecución de escritorio."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

def pytest_configure(config):
    config.addinivalue_line('markers', 'desktop: prueba con una instancia nativa de la aplicación')

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    if item.get_closest_marker('desktop') and not os.environ.get('TRESVIZO_DESKTOP_TEST'):
        # Aislar también las fixtures; ejecutar solamente la función dejaba
        # intérpretes Tk adicionales y ventanas competidoras en el padre.
        from _pytest.runner import CallInfo
        from _pytest.reports import TestReport
        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        def run():
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', item.nodeid],
                cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'TRESVIZO_DESKTOP_TEST': '1'},
                capture_output=True, text=True, timeout=90)
            assert result.returncode == 0, result.stdout+'\n'+result.stderr
        call = CallInfo.from_call(run, when='call')
        item.ihook.pytest_runtest_logreport(report=TestReport.from_item_and_call(item, call))
        item.session._setupstate.teardown_exact(nextitem)
        item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
        return True


@pytest.fixture(autouse=True)
def synthetic_desktop_input(request, monkeypatch):
    if not request.node.get_closest_marker('desktop') or not os.environ.get('TRESVIZO_DESKTOP_TEST'):
        return
    import tkinter as tk
    original_root = tk.Tk.__init__
    original_widget = tk.BaseWidget.__init__
    original_event = tk.Misc.event_generate
    tag = 'SyntheticDesktopInput'
    def initialize_root(widget, *args, **kwargs):
        original_root(widget, *args, **kwargs)
        for pattern in ('<KeyPress>', '<KeyRelease>', '<ButtonPress>', '<ButtonRelease>', '<MouseWheel>'):
            widget.bind_class(tag, pattern, lambda event: None if event.send_event else 'break')
        widget.bindtags((tag, *widget.bindtags()))
    def initialize_widget(widget, *args, **kwargs):
        original_widget(widget, *args, **kwargs)
        if not isinstance(widget, tk.Menu):
            widget.bindtags((tag, *widget.bindtags()))
    def generate(widget, sequence, **kwargs):
        kwargs.setdefault('sendevent', True)
        return original_event(widget, sequence, **kwargs)
    monkeypatch.setattr(tk.Tk, '__init__', initialize_root)
    monkeypatch.setattr(tk.BaseWidget, '__init__', initialize_widget)
    monkeypatch.setattr(tk.Misc, 'event_generate', generate)
