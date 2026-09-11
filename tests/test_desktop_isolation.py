import tkinter as tk
from tkinter import ttk
import pytest


@pytest.mark.desktop
def test_native_keys_cannot_modify_synthetic_forms_but_test_keys_still_work():
    root = tk.Tk()
    try:
        entry = ttk.Entry(root)
        entry.pack()
        root.update()
        entry.focus_force()
        root.update()
        root.tk.call('event', 'generate', str(entry), '<KeyPress-s>', '-sendevent', False)
        root.update()
        assert entry.get() == ''
        entry.event_generate('<KeyPress-s>')
        root.update()
        assert entry.get() == 's'
    finally:
        root.destroy()
