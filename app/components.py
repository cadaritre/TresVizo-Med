import calendar
from datetime import date
import tkinter as tk
from tkinter import ttk


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        top = self.winfo_toplevel()
        binding = top.bind('<MouseWheel>', self.wheel, add='+')
        def cleanup(event):
            if event.widget is self:
                top.unbind('<MouseWheel>', binding)
        self.bind('<Destroy>', cleanup, add='+')

    def wheel(self, event):
        if not self.winfo_exists():
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        if target and str(target).startswith(str(self)):
            self.canvas.yview_scroll(-int(event.delta/120), 'units')


def field(parent, label, value='', width=32, secret=False):
    ttk.Label(parent, text=label).pack(anchor='w', pady=(10, 4))
    var = tk.StringVar(value=value)
    entry = ttk.Entry(parent, textvariable=var, width=width, show='•' if secret else '')
    entry.pack(fill='x')
    return var, entry


class Chart(tk.Canvas):
    def __init__(self, parent, theme, data=None, **kwargs):
        super().__init__(parent, height=190, highlightthickness=0, **kwargs)
        self.data = data or {}
        self.tokens = theme.tokens
        self.bind('<Configure>', lambda e: self.draw())
        theme.subscribe(self, self.retheme)

    def retheme(self, tokens):
        self.tokens = tokens
        self.draw()

    def set(self, data):
        self.data = data
        self.draw()

    def draw(self):
        t = self.tokens
        if not t:
            return
        self.configure(background=t['surface'])
        self.delete('all')
        width = max(self.winfo_width(), 240)
        if not self.data:
            self.create_text(width/2, 80, text='Aún no hay actividad en este periodo.', fill=t['muted'])
            return
        rows = list(self.data.items())[:8]
        maximum = max(max(v for _, v in rows), 1)
        for i, (label, value) in enumerate(rows):
            y = 20+i*22
            self.create_text(10, y, text=str(label)[:22], anchor='w', fill=t['text'], font=('Segoe UI', 9))
            self.create_rectangle(160, y-7, 160+(width-220)*value/maximum, y+7, fill=t[f'chart{i%6+1}'], outline='')
            self.create_text(width-16, y, text=str(value), anchor='e', fill=t['text'])


class DatePicker(ttk.Frame):
    def __init__(self, parent, theme, value=''):
        super().__init__(parent)
        self.theme = theme
        self.var = tk.StringVar(value=value)
        ttk.Entry(self, textvariable=self.var).pack(side='left', fill='x', expand=True)
        ttk.Button(self, text='Calendario', command=self.open).pack(side='left')

    def open(self):
        window = tk.Toplevel(self)
        window.title('Elegir fecha')
        window.transient(self.winfo_toplevel())
        try:
            selected = date.fromisoformat(self.var.get())
        except ValueError:
            selected = date.today()
        month = [selected.year, selected.month]
        title = ttk.Label(window)
        title.pack(pady=10)
        controls = ttk.Frame(window)
        controls.pack(fill='x')
        grid = ttk.Frame(window, padding=12)
        grid.pack()
        def select(day):
            self.var.set(date(*month, day).isoformat())
            window.destroy()
        def render(delta=0):
            y, m = month
            index = y*12+m-1+delta
            month[:] = [index//12, index%12+1]
            title.configure(text=f'{month[0]} · {month[1]:02d}')
            for child in grid.winfo_children():
                child.destroy()
            for col, name in enumerate(('Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sá', 'Do')):
                ttk.Label(grid, text=name).grid(row=0, column=col)
            for row, days in enumerate(calendar.monthcalendar(*month), 1):
                for col, day in enumerate(days):
                    if day:
                        ttk.Button(grid, text=str(day), width=3, command=lambda d=day: select(d)).grid(row=row, column=col)
        ttk.Button(controls, text='‹ Mes anterior', command=lambda: render(-1)).pack(side='left')
        ttk.Button(controls, text='Mes siguiente ›', command=lambda: render(1)).pack(side='right')
        render()
        self.theme._walk(window)


class Tooltip:
    def __init__(self, widget, text, theme):
        self.widget, self.text, self.theme = widget, text, theme
        self.window = None
        widget.bind('<Enter>', self.show, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def show(self, event):
        self.hide()
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.geometry(f'+{event.x_root+16}+{event.y_root+20}')
        ttk.Label(self.window, text=self.text, style='Card.TLabel', padding=10).pack()
        self.theme._walk(self.window)

    def hide(self, event=None):
        if self.window:
            self.window.destroy()
            self.window = None
