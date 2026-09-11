import argparse
import ctypes
import os
import sys
import tkinter as tk
from tkinter import messagebox


def main():
    from app.version import VERSION
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
    parser = argparse.ArgumentParser(description='Registro Clínico')
    parser.add_argument('--data-dir', help='Carpeta separada para pruebas; por defecto Documentos/RegistroClinico')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--startup', action='store_true', help='Inicio de sesión de Windows; conserva la autenticación médica.')
    parser.add_argument('--self-test', metavar='INFORME_JSON', help='Verifica el paquete con archivos sintéticos temporales y termina.')
    args = parser.parse_args()
    if args.self_test:
        from app.package_check import run_check
        return run_check(args.self_test)
    if args.startup:
        from app.windows_startup import WindowsStartup
        if not WindowsStartup().enabled():
            return 0
    from app.main_window import Application
    from app.storage import AlreadyRunning
    try:
        app = Application(args.data_dir)
    except AlreadyRunning:
        if args.startup:
            return 0
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo('TresVizo Med', 'La aplicación ya está abierta para esta carpeta de datos.', parent=root)
        root.destroy()
        return 0
    except (OSError, ValueError) as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('No se puede iniciar', str(exc), parent=root)
        root.destroy()
        return
    app.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
