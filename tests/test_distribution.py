from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
import pytest
from app.version import VERSION, version_tuple
from app.windows_startup import WindowsStartup, REGISTRY_KEY, RUN_KEY, RUN_NAME
from scripts.generate_msi import UPGRADE_CODE, guid, payload_xml, NS


class MemoryRegistry:
    settings_key, run_key, run_name = REGISTRY_KEY, RUN_KEY, RUN_NAME

    def __init__(self, executable):
        self.values = {(REGISTRY_KEY, 'InstallFolder'): str(executable.parent)}
        self.fail_once = False

    def read(self, key, name):
        return self.values.get((key, name))

    def write(self, key, name, value):
        if key == RUN_KEY and self.fail_once:
            self.fail_once = False
            raise PermissionError('Prueba de acceso denegado')
        if value is None:
            self.values.pop((key, name), None)
        else:
            self.values[key, name] = value


def test_startup_persists_quotes_paths_and_can_be_disabled(tmp_path):
    executable = tmp_path/'Aplicación con espacios'/'TresVizo-Med.exe'
    registry = MemoryRegistry(executable)
    startup = WindowsStartup(registry, executable, True)
    assert startup.available and not startup.enabled()
    startup.set_enabled(True)
    assert registry.read(RUN_KEY, RUN_NAME) == f'"{executable}" --startup'
    restarted = WindowsStartup(registry, executable, True)
    assert restarted.enabled()
    restarted.set_enabled(False)
    assert registry.read(REGISTRY_KEY, 'AutoStart') == '0'
    assert registry.read(RUN_KEY, RUN_NAME) is None
    assert not WindowsStartup(registry, executable, True).enabled()


def test_startup_failure_restores_previous_preference_and_command(tmp_path):
    exe = tmp_path/'TresVizo-Med.exe'
    registry = MemoryRegistry(exe)
    startup = WindowsStartup(registry, exe, True)
    startup.set_enabled(True)
    before = dict(registry.values)
    registry.fail_once = True
    with pytest.raises(PermissionError):
        startup.set_enabled(False)
    assert registry.values == before


def test_source_and_portable_cannot_replace_installed_startup(tmp_path):
    exe = tmp_path/'installed'/'TresVizo-Med.exe'
    registry = MemoryRegistry(exe)
    for startup in (WindowsStartup(registry, exe, False),
                    WindowsStartup(registry, tmp_path/'portable'/'TresVizo-Med.exe', True)):
        assert not startup.available
        with pytest.raises(OSError):
            startup.set_enabled(True)
    assert registry.read(RUN_KEY, RUN_NAME) is None


@pytest.mark.parametrize('value', ['1', '1.2', '1.2.3.4', '01.2.3', '1.2.-1', '256.0.0', '1.256.0', '1.0.65536', '1.0.0-beta'])
def test_invalid_msi_version_rejected(value):
    with pytest.raises(ValueError):
        version_tuple(value)


def test_upgrade_family_stable_and_product_changes_with_version():
    assert version_tuple('1.2.3') == (1, 2, 3)
    version_tuple(VERSION)
    assert guid(UPGRADE_CODE, 'x64/product/1.0.0') == guid(UPGRADE_CODE, 'x64/product/1.0.0')
    assert guid(UPGRADE_CODE, 'x64/product/1.0.0') != guid(UPGRADE_CODE, 'x64/product/1.0.1')


def test_payload_only_installs_explicit_program_files_with_stable_components(tmp_path):
    (tmp_path/'TresVizo-Med.exe').write_bytes(b'payload')
    (tmp_path/'_internal'/'assets').mkdir(parents=True)
    (tmp_path/'_internal'/'assets'/'icon.ico').write_bytes(b'icon')
    first = payload_xml(tmp_path, UPGRADE_CODE, 'x64', REGISTRY_KEY)
    (tmp_path/'TresVizo-Med.exe').write_bytes(b'next version')
    assert payload_xml(tmp_path, UPGRADE_CODE, 'x64', REGISTRY_KEY) == first
    xml = ET.fromstring(first)
    assert len(xml.findall('.//{'+NS+'}File')) == 2
    assert not xml.findall('.//{'+NS+'}RemoveFile')
    (tmp_path/'patients.json').write_text('[]')
    with pytest.raises(ValueError):
        payload_xml(tmp_path, UPGRADE_CODE, 'x64', REGISTRY_KEY)


@pytest.mark.desktop
def test_general_settings_toggle_and_error_feedback(tmp_path):
    import tkinter as tk
    from app.general_ui import GeneralSettings
    root = tk.Tk()
    errors = []
    class App:
        def guard(self, action):
            try:
                action()
            except OSError as exc:
                errors.append(str(exc))
    registry = MemoryRegistry(tmp_path/'TresVizo-Med.exe')
    startup = WindowsStartup(registry, tmp_path/'TresVizo-Med.exe', True)
    page = GeneralSettings(root, App(), startup)
    try:
        page.pack()
        root.update()
        page.toggle.invoke()
        assert startup.enabled() and page.enabled.get()
        registry.fail_once = True
        page.toggle.invoke()
        assert errors and startup.enabled() and page.enabled.get()
        page.toggle.invoke()
        assert not startup.enabled() and 'desactivado' in page.info.get()
    finally:
        root.destroy()
