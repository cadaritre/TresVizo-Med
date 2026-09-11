"""Inicio al entrar a Windows, para la cuenta local y la instalación MSI activa."""
import os
from pathlib import Path
import sys

REGISTRY_KEY = r'Software\TresVizo\Med'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'TresVizoMed'


class Registry:
    def __init__(self, settings_key=REGISTRY_KEY, run_key=RUN_KEY, run_name=RUN_NAME):
        import winreg
        self.api = winreg
        self.settings_key, self.run_key, self.run_name = settings_key, run_key, run_name

    def read(self, key, name):
        api = self.api
        try:
            with api.OpenKey(api.HKEY_CURRENT_USER, key, 0, api.KEY_READ | api.KEY_WOW64_32KEY) as handle:
                return api.QueryValueEx(handle, name)[0]
        except FileNotFoundError:
            return None

    def write(self, key, name, value):
        api = self.api
        with api.CreateKeyEx(api.HKEY_CURRENT_USER, key, 0, api.KEY_SET_VALUE | api.KEY_WOW64_32KEY) as handle:
            if value is None:
                try:
                    api.DeleteValue(handle, name)
                except FileNotFoundError:
                    pass
            else:
                api.SetValueEx(handle, name, 0, api.REG_SZ, value)


class WindowsStartup:
    def __init__(self, registry=None, executable=None, installed_runtime=None):
        self.registry = registry if registry is not None else (Registry() if os.name == 'nt' else None)
        self.executable = Path(executable or sys.executable).resolve()
        self.runtime = (bool(getattr(sys, 'frozen', False)) if installed_runtime is None else installed_runtime)

    @property
    def available(self):
        if not self.runtime or self.registry is None:
            return False
        location = self.registry.read(self.registry.settings_key, 'InstallFolder')
        return bool(location and (Path(location)/'TresVizo-Med.exe').resolve() == self.executable)

    @property
    def command(self):
        return f'"{self.executable}" --startup'

    def enabled(self):
        if not self.available:
            return False
        reg = self.registry
        return (reg.read(reg.settings_key, 'AutoStart') == '1'
                and reg.read(reg.run_key, reg.run_name) == self.command)

    def set_enabled(self, enabled):
        if not self.available:
            raise OSError('Esta opción está disponible en la aplicación instalada con el MSI.')
        if type(enabled) is not bool:
            raise ValueError('El inicio automático debe estar activado o desactivado.')
        reg = self.registry
        old_preference = reg.read(reg.settings_key, 'AutoStart')
        old_command = reg.read(reg.run_key, reg.run_name)
        try:
            reg.write(reg.settings_key, 'AutoStart', '1' if enabled else '0')
            reg.write(reg.run_key, reg.run_name, self.command if enabled else None)
        except OSError:
            reg.write(reg.settings_key, 'AutoStart', old_preference)
            reg.write(reg.run_key, reg.run_name, old_command)
            raise
