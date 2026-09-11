"""Controles de edición y listas con estado independiente de la navegación."""
from copy import deepcopy
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from app.components import DatePicker
from app.clinical_models import display_date, local_date

def wrap_actions(frame, buttons):
    """Distribuir acciones en filas sin recortar sus etiquetas al escalar."""
    for button in buttons:
        button.pack_forget()
    def layout(event=None):
        available = max(1, frame.winfo_width())
        row, column, occupied = 0, 0, 0
        for button in buttons:
            width = button.winfo_reqwidth()+8
            if column and occupied+width > available:
                row, column, occupied = row+1, 0, 0
            button.grid(row=row, column=column, sticky='w', padx=(0, 8), pady=3)
            column, occupied = column+1, occupied+width
    frame.bind('<Configure>', layout, add='+')
    frame.after_idle(layout)

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
    def __init__(self, parent, specs, data=None, changed=lambda: None, theme=None, date_type=None):
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
                widget = (date_type or DateField)(cell, theme, value or '')
                self.vars[key] = widget.var
            elif options == 'number':
                widget = ttk.Spinbox(cell, textvariable=var, from_=0, to=1000000, increment=1, width=20)
            elif options:
                widget = ttk.Combobox(cell, textvariable=var, values=options, width=20)
                candidates = tuple(options)
                def filter_options(event, box=widget, values=candidates, variable=var):
                    if event.keysym not in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
                        query = variable.get().casefold()
                        box.configure(values=[v for v in values if query in str(v).casefold()])
                widget.bind('<KeyRelease>', filter_options)
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
        self.edit_id = None
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
        import uuid
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            row.setdefault('id', str(uuid.uuid4()))
            self.tree.insert('', 'end', iid=row['id'], values=(('⚠ Revisar pauta · ' if row.get('needs_review') else '')+self.summary(row),))
        self.tree.selection_set([key for key in selected if self.tree.exists(key)])
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
        if self.editor.winfo_manager():
            next(iter(self.form.inputs.values())).focus_set()
            return
        self.edit_index = None
        self.edit_id = None
        self.form.load(self.defaults)
        self.editor.pack(fill='x', pady=8)
        self.app.theme._walk(self.editor)
        self.pending = False
        next(iter(self.form.inputs.values())).focus_set()

    def edit(self):
        if not self.tree.selection():
            return
        if self.pending and not messagebox.askyesno('Elemento sin confirmar', '¿Descartar los cambios del elemento que estás editando?', parent=self):
            return
        self.edit_id = self.tree.selection()[0]
        self.edit_index = next(i for i, row in enumerate(self.rows) if row['id'] == self.edit_id)
        self.form.load(self.rows[self.edit_index])
        self.editor.pack(fill='x', pady=8)
        self.app.theme._walk(self.editor)
        self.pending = False

    def confirm(self):
        try:
            row = self.form.values()
            if not next(iter(row.values()), '').strip():
                next(iter(self.form.inputs.values())).focus_set()
                raise ValueError('Completa '+self.form.specs[0][1]+'.')
            if self.edit_id is None:
                import uuid
                row['id'] = str(uuid.uuid4())
                self.rows.append(row)
            else:
                index = next((i for i, item in enumerate(self.rows) if item['id'] == self.edit_id), None)
                if index is None:
                    raise ValueError('El elemento ya no está en esta colección. Conserva la captura y revisa la lista.')
                self.rows[index] = {**self.rows[index], **row, 'needs_review': False}
            self.cancel()
            self.refresh()
            self.changed()
        except ValueError as exc:
            self.error.configure(text=str(exc))
            self.error.pack(fill='x')

    def show_preview(self, render):
        self.preview = ttk.Label(self.editor, text='', style='Card.TLabel', padding=12, wraplength=750)
        self.preview.pack(fill='x', before=self.form, pady=(0,8))
        def update(*args):
            self.preview.configure(text=render(self.form.values(raw=True)))
        for variable in self.form.vars.values(): variable.trace_add('write', update)
        update()

    def cancel(self):
        changed = self.pending
        self.pending = False
        self.edit_id = self.edit_index = None
        self.editor.pack_forget()
        self.error.pack_forget()
        if changed:
            self.changed()

    def remove(self):
        if self.tree.selection():
            identifier = self.tree.selection()[0]
            if self.editor.winfo_manager() and identifier == self.edit_id:
                self.error.configure(text='Confirma o cancela el elemento en edición antes de quitar una fila.')
                self.error.pack(fill='x')
                return
            self.rows = [r for r in self.rows if r['id'] != identifier]
            self.refresh()
            self.changed()

    def state(self):
        import uuid
        for row in self.rows:
            row.setdefault('id', str(uuid.uuid4()))
        return {'rows': deepcopy(self.rows), 'pending': self.form.values(raw=True) if self.pending else None,
                'edit_id': self.edit_id, 'index': next((i for i, r in enumerate(self.rows) if r['id'] == self.edit_id), None)}

    def restore(self, state):
        if state and 'rows' in state:
            self.rows = deepcopy(state['rows'])
            self.refresh()
        if state and state.get('pending') is not None:
            self.form.load(state['pending'])
            self.edit_index = state.get('index')
            self.edit_id = state.get('edit_id')
            if self.edit_id is None and isinstance(self.edit_index, int) and 0 <= self.edit_index < len(self.rows):
                self.edit_id = self.rows[self.edit_index]['id']
            self.editor.pack(fill='x', pady=8)
            self.pending = True

class Collapsible(ttk.Frame):
    def __init__(self, parent, title, opened=False, summary='', changed=None):
        super().__init__(parent)
        self.opened = opened
        self.animation = None
        self.title = title
        self.changed = changed
        self.button = ttk.Button(self, text=('− ' if opened else '+ ')+title, command=self.toggle, style='Disclosure.Link.TButton')
        self.button.pack(fill='x', pady=6)
        self.summary = ttk.Label(self, text=summary, style='Subtitle.TLabel', wraplength=760, justify='left')
        self.summary.pack(fill='x', padx=12)
        self.bind('<Configure>', lambda e: self.summary.configure(wraplength=max(160, e.width-24)))
        if not summary:
            self.summary.pack_forget()
        self.body = ttk.Frame(self, padding=(12, 0, 0, 8))
        if opened:
            self.body.pack(fill='x')
    def set_summary(self, text):
        self.summary.configure(text=text)
        if text and not self.summary.winfo_manager():
            self.summary.pack(fill='x', padx=12, after=self.button)
        elif not text:
            self.summary.pack_forget()

    def reveal(self):
        if not self.opened:
            self.toggle()
        if self.animation:
            self.after_cancel(self.animation)
            self.animation = None
        self.body.pack_propagate(True)
        self.body.pack(fill='x')

    def toggle(self):
        if self.animation:
            self.after_cancel(self.animation)
            self.animation = None
        self.opened = not self.opened
        self.button.configure(text=('− ' if self.opened else '+ ')+self.title)
        if self.changed:
            self.changed()
        app = self.winfo_toplevel()
        reduced = not hasattr(app, 'profiles') or not app.auth.current or app.profiles.get(app.auth.current['id']).get('reduce_motion', False)
        if reduced:
            self.body.pack_propagate(True)
            self.body.pack(fill='x') if self.opened else self.body.pack_forget()
            return
        self.body.pack_propagate(True)
        self.body.update_idletasks()
        height = max(1, self.body.winfo_reqheight())
        self.body.pack_propagate(False)
        self.body.pack(fill='x')
        def step(index=0):
            portion = index/10
            self.body.configure(height=max(1, int(height*(portion if self.opened else 1-portion))))
            if index < 10:
                self.animation = self.after(15, lambda: step(index+1))
            else:
                self.animation = None
                self.body.pack_propagate(True)
                if not self.opened:
                    self.body.pack_forget()
        step()
