"""Controles de edición y listas con estado independiente de la navegación."""
from copy import deepcopy
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from app.components import DatePicker
from app.clinical_models import display_date, local_date

def text_editor(parent, value='', height=4, changed=lambda: None):
    widget = tk.Text(parent, height=height, wrap='word', undo=True, relief='flat', highlightthickness=1,
                     padx=10, pady=8, font=('Segoe UI', 11))
    widget.insert('1.0', value)
    widget.edit_modified(False)
    def modified(event=None):
        if widget.edit_modified():
            widget.edit_modified(False)
            changed()
    widget.bind('<<Modified>>', modified)
    menu = tk.Menu(widget, tearoff=False)
    for label, event in [('Deshacer', '<<Undo>>'), ('Rehacer', '<<Redo>>'), ('Cortar', '<<Cut>>'), ('Copiar', '<<Copy>>'), ('Pegar', '<<Paste>>'), ('Seleccionar todo', '<<SelectAll>>')]:
        menu.add_command(label=label, command=lambda e=event: widget.event_generate(e))
    widget.bind('<Button-3>', lambda e: menu.tk_popup(e.x_root, e.y_root))
    return widget

class DateField(DatePicker):
    def __init__(self, parent, theme, value=''):
        super().__init__(parent, theme, display_date(value) if value else '')
        self.var.trace_add('write', self._localized)
    def _localized(self, *args):
        value = self.var.get()
        if len(value) == 10 and value[4] == '-':
            self.var.set(display_date(value))
    def get(self):
        return local_date(self.var.get())

class Form(ttk.Frame):
    def __init__(self, parent, specs, data=None, changed=lambda: None, theme=None):
        super().__init__(parent)
        self.vars, self.inputs, self.cells = {}, {}, []
        self.specs, self.changed = specs, changed
        self.loading = True
        for key, label, options in specs:
            cell = ttk.Frame(self, padding=(0, 0, 12, 10))
            ttk.Label(cell, text=label, style='Subtitle.TLabel').pack(anchor='w', pady=(0, 4))
            value = (data or {}).get(key, '')
            var = tk.StringVar(value='' if value is None else str(value))
            self.vars[key] = var
            if options == 'text':
                widget = text_editor(cell, value or '', 3, self.notify)
            elif options == 'date':
                widget = DateField(cell, theme, value or '')
                self.vars[key] = widget.var
            elif options:
                widget = ttk.Combobox(cell, textvariable=var, values=options, width=20)
            else:
                widget = ttk.Entry(cell, textvariable=var, width=24)
            widget.pack(fill='x')
            self.inputs[key] = widget
            self.vars[key].trace_add('write', lambda *a: self.notify())
            self.cells.append(cell)
        self.columns = 0
        self.bind('<Configure>', self.layout)
        self.loading = False
        self.layout()

    def layout(self, event=None):
        columns = 2 if self.winfo_width() >= 560 else 1
        if columns == self.columns:
            return
        self.columns = columns
        for i in range(2):
            self.columnconfigure(i, weight=1 if i < columns else 0)
        row, col = 0, 0
        for cell, spec in zip(self.cells, self.specs):
            wide = spec[2] == 'text'
            if wide and col:
                row, col = row+1, 0
            cell.grid(row=row, column=col, columnspan=columns if wide else 1, sticky='nsew')
            col += columns if wide else 1
            if col >= columns:
                row, col = row+1, 0

    def notify(self):
        if not self.loading:
            self.changed()

    def values(self, raw=False):
        result = {}
        for key, _, options in self.specs:
            widget = self.inputs[key]
            result[key] = widget.get('1.0', 'end-1c') if options == 'text' else widget.get() if options == 'date' and not raw else self.vars[key].get().strip()
        return result

    def load(self, data):
        self.loading = True
        for key, _, options in self.specs:
            value = data.get(key, '')
            if options == 'text':
                self.inputs[key].delete('1.0', 'end')
                self.inputs[key].insert('1.0', value)
                self.inputs[key].edit_modified(False)
            else:
                self.vars[key].set(display_date(value) if options == 'date' and value else str(value or ''))
        self.loading = False

class Collection(ttk.Frame):
    def __init__(self, parent, app, title, specs, rows=None, summary=None, changed=lambda: None, defaults=None):
        super().__init__(parent)
        self.app, self.rows, self.changed = app, deepcopy(rows or []), changed
        self.summary = summary or (lambda r: ' · '.join(str(v) for k, v in r.items() if k not in ('id',) and v))
        self.defaults = defaults or {}
        self.edit_index = None
        self.pending = False
        header = ttk.Frame(self)
        header.pack(fill='x', pady=(10, 8))
        self.heading = ttk.Label(header, text=title, style='Section.TLabel')
        self.heading.pack(side='left')
        ttk.Button(header, text='+ Añadir', command=self.new).pack(side='right')
        self.tree = ttk.Treeview(self, columns=('value',), show='headings', height=4, selectmode='browse')
        self.tree.heading('value', text='Registros · doble clic para editar')
        self.tree.column('value', width=480, minwidth=140)
        self.tree.pack(fill='x')
        self.empty = ttk.Label(self, text='Sin registros. Usa Añadir para incorporar uno.', style='Subtitle.TLabel', padding=(8,6))
        self.tree.bind('<Double-1>', lambda e: self.edit())
        actions = self.list_actions = ttk.Frame(self)
        actions.pack(fill='x', pady=4)
        ttk.Button(actions, text='Editar', style='Link.TButton', command=self.edit).pack(side='left')
        ttk.Button(actions, text='Quitar de esta edición', style='Link.TButton', command=self.remove).pack(side='left', padx=8)
        self.editor = ttk.Frame(self, padding=12)
        self.form = Form(self.editor, specs, changed=self.on_pending, theme=app.theme)
        self.form.pack(fill='x')
        self.error = ttk.Label(self.editor, style='error.TLabel', wraplength=500)
        bottom = ttk.Frame(self.editor)
        bottom.pack(fill='x', pady=6)
        ttk.Button(bottom, text='Confirmar elemento', style='Primary.TButton', command=self.confirm).pack(side='left')
        ttk.Button(bottom, text='Cancelar elemento', command=self.cancel).pack(side='left', padx=8)
        self.refresh()

    def on_pending(self):
        self.pending = True
        self.changed()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            self.tree.insert('', 'end', iid=str(index), values=(self.summary(row),))
        self.tree.configure(height=max(1, min(5, len(self.rows))))
        self.empty.pack_forget()
        if not self.rows:
            self.tree.pack_forget()
            self.list_actions.pack_forget()
            self.empty.pack(fill='x', after=self.heading.master)
        else:
            self.tree.pack(fill='x', after=self.heading.master)
            self.list_actions.pack(fill='x', pady=4, after=self.tree)

    def new(self):
        self.edit_index = None
        self.form.load(self.defaults)
        self.editor.pack(fill='x', pady=8)
        self.app.theme._walk(self.editor)
        self.pending = False
        next(iter(self.form.inputs.values())).focus_set()

    def edit(self):
        if not self.tree.selection():
            return
        self.edit_index = int(self.tree.selection()[0])
        self.form.load(self.rows[self.edit_index])
        self.editor.pack(fill='x', pady=8)
        self.app.theme._walk(self.editor)
        self.pending = False

    def confirm(self):
        try:
            row = self.form.values()
            if not next(iter(row.values()), '').strip():
                raise ValueError('Completa el primer campo del elemento.')
            if self.edit_index is None:
                self.rows.append(row)
            else:
                self.rows[self.edit_index] = {**self.rows[self.edit_index], **row, 'needs_review': False}
            self.cancel()
            self.refresh()
            self.changed()
        except ValueError as exc:
            self.error.configure(text=str(exc))
            self.error.pack(fill='x')

    def cancel(self):
        self.pending = False
        self.editor.pack_forget()
        self.error.pack_forget()
        self.changed()

    def remove(self):
        if self.tree.selection():
            del self.rows[int(self.tree.selection()[0])]
            self.refresh()
            self.changed()

    def state(self):
        return {'rows': deepcopy(self.rows), 'pending': self.form.values(raw=True) if self.editor.winfo_manager() else None, 'index': self.edit_index}

    def restore(self, state):
        if state and state.get('pending') is not None:
            self.form.load(state['pending'])
            self.edit_index = state.get('index')
            self.editor.pack(fill='x', pady=8)
            self.pending = True

class Collapsible(ttk.Frame):
    def __init__(self, parent, title, opened=False):
        super().__init__(parent)
        self.opened = opened
        self.title = title
        self.button = ttk.Button(self, text=('− ' if opened else '+ ')+title, command=self.toggle, style='Link.TButton')
        self.button.pack(fill='x', pady=6)
        self.body = ttk.Frame(self, padding=(12, 0, 0, 8))
        if opened:
            self.body.pack(fill='x')
    def toggle(self):
        self.opened = not self.opened
        self.button.configure(text=('− ' if self.opened else '+ ')+self.title)
        self.body.pack(fill='x') if self.opened else self.body.pack_forget()
