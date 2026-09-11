import calendar
from datetime import date
import tkinter as tk
from tkinter import ttk


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.scroll_surface = True
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        def set_scroll(first, last):
            bar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                bar.pack_forget()
            elif not bar.winfo_manager():
                bar.pack(side='right', fill='y', before=self.canvas)
        self.canvas.configure(yscrollcommand=set_scroll)
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
            if isinstance(target, (tk.Text, ttk.Treeview, ttk.Combobox)):
                return
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
        self.entry = ttk.Entry(self, textvariable=self.var)
        self.entry.pack(side='left', fill='x', expand=True)
        self.button = ttk.Button(self, text='Calendario', command=self.open)
        self.button.pack(side='left')
        self.popup = None

    def set_enabled(self, enabled):
        # Un calendario abierto es un Toplevel; su state() controla la ventana.
        for control in (self.entry, self.button):
            control.state(['!disabled'] if enabled else ['disabled'])
        if not enabled and self.popup is not None and self.popup.winfo_exists():
            self.popup.destroy()

    def selected_date(self):
        from app.clinical_models import local_date
        return date.fromisoformat(local_date(self.var.get()))

    def set_date(self, value):
        self.var.set(value.isoformat())

    def open(self):
        if self.entry.instate(['disabled']):
            return
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
            return self.popup
        window = tk.Toplevel(self)
        self.popup = window
        window.title('Elegir fecha')
        window.transient(self.winfo_toplevel())
        from app.branding import set_window_icon
        set_window_icon(window)
        window.bind('<Escape>', lambda event: (window.destroy(), 'break')[1])
        try:
            selected = self.selected_date()
        except ValueError:
            selected = date.today()
        month = [selected.year, selected.month]
        title = ttk.Label(window)
        title.pack(pady=10)
        controls = ttk.Frame(window)
        controls.pack(fill='x')
        year = tk.StringVar(value=str(month[0]))
        month_var = tk.StringVar(value=str(month[1]))
        direct = ttk.Frame(window, padding=8)
        direct.pack(fill='x')
        ttk.Label(direct, text='Mes').pack(side='left')
        month_box = ttk.Combobox(direct, textvariable=month_var, values=list(range(1, 13)), width=5, state='readonly')
        month_box.pack(side='left', padx=6)
        ttk.Label(direct, text='Año').pack(side='left')
        year_box = ttk.Spinbox(direct, from_=1800, to=2200, textvariable=year, width=8)
        year_box.pack(side='left', padx=6)
        grid = ttk.Frame(window, padding=12)
        grid.pack()
        def select(day):
            self.set_date(date(*month, day))
            window.destroy()
            self.entry.focus_set()
        def render(delta=0):
            y, m = month
            index = y*12+m-1+delta
            month[:] = [index//12, index%12+1]
            year.set(str(month[0]))
            month_var.set(str(month[1]))
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
        def jump(event=None):
            try:
                y, m = int(year.get()), int(month_var.get())
                if 1800 <= y <= 2200 and 1 <= m <= 12:
                    month[:] = [y, m]
                    render()
            except ValueError:
                pass
        month_box.bind('<<ComboboxSelected>>', jump)
        year_box.bind('<Return>', jump)
        ttk.Button(direct, text='Ir', command=jump).pack(side='left')
        render()
        self.theme._walk(window)
        return window


class Tooltip:
    def __init__(self, widget, text, theme):
        self.widget, self.text, self.theme = widget, text, theme
        self.window = None
        self.pending = None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<FocusIn>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<FocusOut>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.bind('<Unmap>', self.hide, add='+')
        widget.bind('<Escape>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.pending = self.widget.after(450, self.show)

    def show(self, event=None):
        self.hide()
        if not self.widget.winfo_viewable() or getattr(self.widget._root(), 'locked', False):
            return
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()
        self.window.overrideredirect(True)
        ttk.Label(self.window, text=self.text, style='Card.TLabel', padding=10, wraplength=300).pack()
        self.theme._walk(self.window)
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth()-self.window.winfo_reqwidth()-8)
        y = self.widget.winfo_rooty()+self.widget.winfo_height()+6
        if y+self.window.winfo_reqheight() > self.widget.winfo_screenheight():
            y = self.widget.winfo_rooty()-self.window.winfo_reqheight()-6
        self.window.geometry(f'+{max(0,x)}+{max(0,y)}')
        self.window.deiconify()

    def hide(self, event=None):
        if self.pending is not None:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window:
            self.window.destroy()
            self.window = None
