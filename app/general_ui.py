"""Preferencias de esta instalación, independientes de los expedientes."""
import struct
import tkinter as tk
from tkinter import ttk
from app.version import VERSION
from app.windows_startup import WindowsStartup


class GeneralSettings(ttk.Frame):
    def __init__(self, parent, app, startup=None):
        super().__init__(parent, padding=20)
        self.startup = startup if startup is not None else WindowsStartup()
        ttk.Label(self, text=f'TresVizo Med · {VERSION} · {struct.calcsize("P")*8} bits', style='Section.TLabel').pack(anchor='w')
        ttk.Label(self, text='Inicio de Windows', style='Section.TLabel').pack(anchor='w', pady=(24, 8))
        self.enabled = tk.BooleanVar(self, False)
        self.info = tk.StringVar(self)
        self.toggle = ttk.Checkbutton(self, text='Abrir TresVizo Med al iniciar sesión en Windows', variable=self.enabled, command=lambda: app.guard(self.save))
        self.toggle.pack(anchor='w', pady=8)
        ttk.Label(self, text='Se abre la pantalla de acceso. Cada doctor conserva su contraseña.\nEsta opción afecta a la cuenta de Windows de esta PC.', wraplength=670, style='Subtitle.TLabel').pack(anchor='w', pady=8)
        ttk.Label(self, textvariable=self.info, wraplength=670).pack(anchor='w', pady=8)
        ttk.Label(self, text='Para actualizar, guarda tu trabajo, cierra la aplicación y ejecuta el MSI de la nueva versión. Los expedientes y preferencias permanecen en Documentos.', wraplength=670).pack(anchor='w', pady=(24, 8))
        self.refresh()

    def refresh(self):
        try:
            available = self.startup.available
            self.enabled.set(self.startup.enabled())
            self.toggle.state(['!disabled'] if available else ['disabled'])
            self.info.set(('Inicio automático activado.' if self.enabled.get() else 'Inicio automático desactivado.') if available else 'Instala la aplicación con el MSI para configurar el inicio de Windows.')
        except OSError as exc:
            self.toggle.state(['disabled'])
            self.info.set('No se pudo leer la configuración de Windows: '+str(exc))

    def save(self):
        try:
            self.startup.set_enabled(self.enabled.get())
        finally:
            self.refresh()
