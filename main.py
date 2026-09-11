import argparse
import ctypes
import os
import tkinter as tk
from tkinter import messagebox


def main():
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
    parser = argparse.ArgumentParser(description='Registro Clínico')
    parser.add_argument('--data-dir', help='Carpeta separada para pruebas; por defecto Documentos/RegistroClinico')
    args = parser.parse_args()
    from app.main_window import Application
    try:
        app = Application(args.data_dir)
    except (OSError, ValueError) as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('No se puede iniciar', str(exc), parent=root)
        root.destroy()
        return
    app.mainloop()


if __name__ == '__main__':
    main()
