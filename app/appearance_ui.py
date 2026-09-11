from pathlib import Path
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, simpledialog, messagebox
from app.components import ScrollFrame
from app.themes import COLORS, BUILTINS, color, derived, issues, repair
from app.storage import DataError


class AppearanceEditor(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=16)
        self.app, self.service = app, app.appearance
        self.selected = self.service.active_key()
        self.variables = {}
        self.saved = self.service.tokens()
        self.loading = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text='Apariencia → Colores', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        top = ttk.Frame(self)
        top.grid(row=1, column=0, sticky='ew', pady=12)
        self.choice = tk.StringVar()
        self.combo = ttk.Combobox(top, textvariable=self.choice, state='readonly', width=24)
        for column in range(3):
            top.columnconfigure(column, weight=1)
        self.combo.grid(row=0, column=0, sticky='ew', padx=3, pady=3)
        self.combo.bind('<<ComboboxSelected>>', self.choose)
        for index, (label, command) in enumerate([('Duplicar', self.duplicate), ('Renombrar', self.rename), ('Eliminar', self.delete),
                               ('Importar JSON', self.import_file), ('Exportar JSON', self.export_file)], 1):
            ttk.Button(top, text=label, command=command).grid(row=index//3, column=index%3, sticky='ew', padx=3, pady=3)
        split = ttk.Panedwindow(self, orient='horizontal')
        split.grid(row=2, column=0, sticky='nsew')
        scroll = ScrollFrame(split)
        split.add(scroll, weight=2)
        form = scroll.body
        form.columnconfigure(1, weight=1)
        for row, (key, label) in enumerate(COLORS.items()):
            ttk.Label(form, text=label, wraplength=125).grid(row=row, column=0, sticky='w', padx=6, pady=6)
            var = tk.StringVar(value=self.saved[key])
            self.variables[key] = var
            entry = ttk.Entry(form, textvariable=var, width=9)
            entry.grid(row=row, column=1, sticky='ew', padx=8)
            swatch = tk.Canvas(form, width=30, height=23, highlightthickness=1, cursor='hand2')
            swatch.own_palette = True
            swatch.grid(row=row, column=2, padx=8)
            swatch.bind('<Button-1>', lambda e, k=key: self.pick(k))
            ttk.Button(form, text='…', width=2, command=lambda k=key: self.pick(k)).grid(row=row, column=3, padx=4)
            var.trace_add('write', lambda *a, k=key, w=swatch, en=entry: self.changed(k, w, en))
            swatch.configure(background=var.get())
        preview_scroll = ScrollFrame(split)
        split.add(preview_scroll, weight=3)
        preview = preview_scroll.body
        ttk.Label(preview, text='Vista previa · datos de ejemplo', style='Subtitle.TLabel').pack(anchor='w')
        self.preview = tk.Canvas(preview, width=440, height=430, highlightthickness=0)
        self.preview.own_palette = True
        self.preview.bind('<Configure>', lambda e: self.draw_preview())
        self.warning = tk.StringVar()
        ttk.Label(preview, text='Las alertas conservan colores, iconos y texto.\nLa impresión tiene su propia paleta en Identidad.',
                  style='Subtitle.TLabel', wraplength=430).pack(side='bottom', anchor='w', pady=8)
        ttk.Button(preview, text='Corregir contraste automáticamente', command=self.auto_fix).pack(side='bottom', anchor='w')
        ttk.Label(preview, textvariable=self.warning, wraplength=440, justify='left').pack(side='bottom', fill='x', pady=8)
        self.preview.pack(fill='both', expand=True, pady=8)
        footer = ttk.Frame(self)
        footer.grid(row=3, column=0, sticky='ew', pady=(14, 0))
        pref = self.service.state['users'].get(app.auth.current['id'], {})
        self.inherit = tk.BooleanVar(value=pref.get('inherit', True))
        self.clinic = tk.BooleanVar(value=False)
        ttk.Checkbutton(footer, text='Usar apariencia de la clínica', variable=self.inherit).pack(anchor='w')
        if app.auth.current['role'] == 'admin':
            ttk.Checkbutton(footer, text='Establecer como predeterminada de la clínica', variable=self.clinic).pack(anchor='w')
        actions = ttk.Frame(footer)
        actions.pack(fill='x', pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        for index, (label, cmd, style) in enumerate([('Aplicar cambios', self.apply, 'Primary.TButton'), ('Cancelar cambios', self.cancel, 'TButton'),
                                  ('Restablecer Clínico', self.reset, 'TButton'), ('Guardar con nombre', self.save_named, 'TButton')]):
            ttk.Button(actions, text=label, command=cmd, style=style).grid(row=index//2, column=index%2, sticky='ew', padx=4, pady=3)
        self.refresh_choices()
        self.draw_preview()

    def guard(self, fn):
        return self.app.guard(fn)

    def refresh_choices(self):
        self.themes = self.service.list()
        self.names = {value['name']: key for key, value in self.themes.items()}
        self.combo.configure(values=[*self.names, 'Personalizada'])
        self.choice.set(self.themes[self.selected]['name'] if self.selected in self.themes else 'Personalizada')

    def values(self):
        return {key: color(var.get()) for key, var in self.variables.items()}

    def load(self, tokens):
        self.loading = True
        for key, value in tokens.items():
            self.variables[key].set(value)
        self.loading = False
        self.draw_preview()

    def choose(self, event=None):
        if self.choice.get() == 'Personalizada':
            self.selected = None
            return
        self.selected = self.names[self.choice.get()]
        self.load(self.themes[self.selected]['tokens'])
        self.inherit.set(False)

    def changed(self, key, swatch, entry):
        try:
            swatch.configure(background=color(self.variables[key].get()))
            entry.state(['!invalid'])
        except DataError:
            entry.state(['invalid'])
        if not self.loading:
            self.selected = None
            self.choice.set('Personalizada')
            self.inherit.set(False)
            self.draw_preview()

    def pick(self, key):
        initial = self.variables[key].get()
        try:
            color(initial)
        except DataError:
            initial = self.saved[key]
        chosen = colorchooser.askcolor(initialcolor=initial, parent=self, title=COLORS[key])[1]
        if chosen:
            self.variables[key].set(chosen.upper())

    def draw_preview(self):
        try:
            values = self.values()
        except DataError:
            self.warning.set('⚠ Color incompleto. Usa el formato #RRGGBB para continuar.')
            return
        problems = issues(values)
        self.warning.set(('⚠ '+str(len(problems))+' combinaciones necesitan revisión.\n'+'\n'.join(problems[:3])) if problems else '✓ Contraste de texto y controles verificado.')
        c, t = self.preview, derived(values)
        c.delete('all')
        w, h = max(c.winfo_width(), 350), max(c.winfo_height(), 340)
        c.configure(background=t['background'])
        def rect(x, y, x2, y2, fill, outline=None):
            c.create_rectangle(x, y, x2, y2, fill=t.get(fill, fill), outline=t.get(outline, '') if outline else '')
        def text(x, y, value, fill='text', size=10):
            c.create_text(x, y, text=value, anchor='w', fill=t[fill], font=('Segoe UI', size))
        rect(0, 0, w, 42, 'header')
        text(15, 21, 'Registro Clínico  /  Consulta', 'on_header', 12)
        rect(10, 54, w-10, 213, 'surface', 'border')
        text(24, 77, 'Tarjeta del paciente · Ejemplo', 'primary', 12)
        text(24, 101, 'Motivo de consulta', 'muted')
        rect(24, 116, w-24, 148, 'surface', 'focus')
        text(34, 132, 'Seguimiento programado')
        for x, key, label in [(24, 'button', 'Guardar'), (140, 'secondary', 'Cancelar'), (258, 'secondary_disabled', 'Inactivo')]:
            rect(x, 166, min(x+105, w-20), 197, key)
            text(x+8, 181, label, 'on_'+key, 9)
        rect(10, 226, w-10, 257, 'selection')
        text(24, 242, '✓ Fila seleccionada · 09:30', 'on_selection')
        rect(10, 269, w-10, 303, 'warning_bg')
        text(24, 286, '⚠ Alergia registrada · Revisar expediente', 'warning_fg', 9)
        if h > 370:
            text(24, 327, 'Consultas por día · valores de ejemplo', 'text', 9)
            for i, n in enumerate((3, 6, 4, 7, 5, 2)):
                x = 32+i*(w-55)/6
                rect(x, h-30-n*5, x+24, h-30, f'chart{i+1}')
                text(x+5, h-16, str(n), 'text', 9)

    def auto_fix(self):
        self.guard(lambda: self.load(repair(self.values())))
        self.selected = None
        self.choice.set('Personalizada')
        self.inherit.set(False)

    def save_named(self):
        name = simpledialog.askstring('Guardar tema', 'Nombre de la combinación:', parent=self)
        if name:
            def action():
                self.selected = self.service.save_theme(name, self.values())
                self.refresh_choices()
            self.guard(action)

    def duplicate(self):
        self.save_named()

    def rename(self):
        name = simpledialog.askstring('Renombrar tema', 'Nuevo nombre:', parent=self)
        if name:
            def action():
                self.service.rename(self.selected, name)
                self.refresh_choices()
            self.guard(action)

    def delete(self):
        if not messagebox.askyesno('Eliminar tema', '¿Eliminar esta combinación personalizada?', parent=self):
            return
        def action():
            self.service.delete(self.selected)
            self.selected = self.service.active_key()
            self.refresh_choices()
            self.load(self.service.tokens())
        self.guard(action)

    def import_file(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('Tema JSON', '*.json')])
        if path:
            def action():
                self.selected = self.service.import_theme(Path(path))
                self.refresh_choices()
                self.load(self.themes[self.selected]['tokens'])
                self.inherit.set(False)
            self.guard(action)

    def export_file(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.json', filetypes=[('Tema JSON', '*.json')])
        if path:
            def action():
                from app.themes import validate_theme
                from app.storage import atomic_json
                name = self.choice.get() or 'Personalizada'
                atomic_json(Path(path), validate_theme({'schema_version': 1, 'name': name, 'tokens': self.values()}))
            self.guard(action)

    def apply(self):
        def action():
            tokens = self.values()
            if not self.inherit.get() or self.clinic.get():
                if issues(tokens):
                    raise DataError('Corrige las combinaciones de contraste señaladas antes de aplicar.')
                if not self.selected:
                    name = simpledialog.askstring('Guardar personalización', 'Nombre para conservar esta paleta:', parent=self)
                    if not name:
                        return
                    self.selected = self.service.save_theme(name, tokens)
            key = self.selected or self.service.state['clinic']
            self.service.apply(key, self.inherit.get(), self.clinic.get())
            self.saved = self.service.tokens()
            self.app.theme.apply(self.saved)
            self.refresh_choices()
            self.app.status.set('Apariencia guardada. Los formularios siguen abiertos.')
        self.guard(action)

    def cancel(self):
        self.selected = self.service.active_key()
        self.load(self.service.tokens())
        self.refresh_choices()
        pref = self.service.state['users'].get(self.app.auth.current['id'], {})
        self.inherit.set(pref.get('inherit', True))
        self.clinic.set(False)

    def reset(self):
        self.selected = 'Clínico'
        self.load(BUILTINS['Clínico'])
        self.choice.set('Clínico')
        self.inherit.set(False)
