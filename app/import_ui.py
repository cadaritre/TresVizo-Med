"""Mapeo y revisión de lotes CSV antes de una única transacción."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from app.consultation_tools import action, fit_window
from app.components import ScrollFrame
from app.widgets import Form


class ImportWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.source, self.preview = app, None, None
        self.selected, self.accepted_duplicates = set(), set()
        self.page, self.busy = 0, False
        self.title('Importar pacientes · revisar CSV')
        self.transient(app)
        fit_window(self, app, 900, 700)
        footer = ttk.Frame(self, padding=12)
        footer.pack(side='bottom', fill='x')
        self.commit = action(footer, app, 'Importar seleccionados', self.import_selected, primary=True)
        self.commit.pack(side='right')
        self.commit.state(['disabled'])
        action(footer, app, 'Cerrar', self.close).pack(side='right', padx=8)
        self.notice = ttk.Label(footer, wraplength=750, style='Subtitle.TLabel')
        self.notice.pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        body = ScrollFrame(self)
        body.pack(fill='both', expand=True)
        ttk.Label(body.body, text='Se crean personas nuevas. No se fusionan ni reemplazan expedientes. CSV UTF-8; fechas AAAA-MM-DD.', wraplength=780).pack(fill='x', pady=8)
        bar = ttk.Frame(body.body)
        bar.pack(fill='x')
        self.delimiter = tk.StringVar(value='Coma')
        ttk.Combobox(bar, textvariable=self.delimiter, values=['Coma', 'Punto y coma', 'Tabulación'], state='readonly', width=18).pack(side='left')
        action(bar, app, 'Elegir CSV', self.choose).pack(side='left', padx=8)
        self.mapping_box = ttk.Frame(body.body)
        self.mapping_box.pack(fill='x', pady=8)
        action(body.body, app, 'Validar y mostrar vista previa', self.inspect).pack(anchor='w')
        self.tree = ttk.Treeview(body.body, columns=('decision', 'row', 'name', 'state'), show='headings', height=8)
        for key, label in [('decision', 'Importar'), ('row', 'Fila'), ('name', 'Nombre'), ('state', 'Resultado')]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=250 if key in ('name', 'state') else 75, minwidth=50)
        self.tree.pack(fill='x', pady=8)
        self.tree.bind('<<TreeviewSelect>>', self.details)
        actions = ttk.Frame(body.body)
        actions.pack(fill='x')
        action(actions, app, 'Incluir / excluir fila', self.toggle).pack(side='left')
        action(actions, app, 'Anterior', lambda: self.turn(-1)).pack(side='right')
        action(actions, app, 'Siguiente', lambda: self.turn(1)).pack(side='right')
        self.detail = ttk.Label(body.body, style='Subtitle.TLabel', wraplength=800, justify='left')
        self.detail.pack(fill='x', pady=8)
        self.app.theme._walk(self)

    def invalidate(self):
        self.preview = None
        self.commit.state(['disabled'])
        self.notice.configure(text='Mapeo modificado · vuelve a validar antes de importar.')

    def choose(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[('Pacientes CSV', '*.csv')])
        if not path:
            return
        try:
            self.source = self.app.transfer.read_csv(path, {'Coma': ',', 'Punto y coma': ';', 'Tabulación': '\t'}[self.delimiter.get()])
            for child in self.mapping_box.winfo_children():
                child.destroy()
            fields = [('name', 'Nombre *'), ('birth_date', 'Nacimiento'), ('phone', 'Teléfono'), ('email', 'Correo')]
            self.mapping = Form(self.mapping_box, [(k, label, ['', *self.source['columns']]) for k, label in fields],
                {k: k if k in self.source['columns'] else '' for k, _ in fields}, changed=self.invalidate, theme=self.app.theme)
            self.mapping.pack(fill='x')
            self.invalidate()
            self.notice.configure(text=f"{len(self.source['rows'])} filas leídas. Revisa el mapeo y valida.")
        except (ValueError, OSError) as exc:
            self.notice.configure(text=str(exc))

    def inspect(self):
        if not self.source or self.busy:
            return
        try:
            self.preview = self.app.transfer.inspect_import(self.source, self.mapping.values())
            self.selected = {r['number'] for r in self.preview['rows'] if not r['errors'] and not r['duplicates']}
            self.accepted_duplicates.clear()
            self.page = 0
            self.render()
        except (ValueError, OSError) as exc:
            self.notice.configure(text=str(exc))

    def turn(self, delta):
        self.page = max(0, self.page+delta)
        self.render()

    def render(self):
        if not self.preview:
            return
        rows = self.preview['rows']
        self.page = min(self.page, max(0, (len(rows)-1)//100))
        selected = self.tree.selection()
        page_rows = rows[self.page*100:self.page*100+100]
        self.tree.configure(height=max(2, min(6, len(page_rows))))
        self.tree.delete(*self.tree.get_children())
        for row in page_rows:
            self.tree.insert('', 'end', iid=str(row['number']), values=('Sí' if row['number'] in self.selected else 'No', row['number'],
                row['patient']['name'], 'Errores' if row['errors'] else 'Posible duplicado' if row['duplicates'] else 'Válida'))
        self.tree.selection_set([identifier for identifier in selected if self.tree.exists(identifier)])
        self.notice.configure(text=f"{len(self.selected)} a importar · {sum(bool(r['errors']) for r in rows)} con errores · {sum(bool(r['duplicates']) for r in rows)} posibles duplicados · página {self.page+1}")
        self.commit.state(['!disabled'] if self.selected and not self.busy else ['disabled'])

    def current(self):
        selection = self.tree.selection()
        return next((r for r in self.preview['rows'] if selection and str(r['number']) == selection[0]), None) if self.preview else None

    def details(self, event=None):
        row = self.current()
        if row:
            names = {'name': 'Nombre', 'birth_date': 'Nacimiento', 'phone': 'Teléfono', 'email': 'Correo', 'fila': 'Fila'}
            self.detail.configure(text='\n'.join([*(names.get(k, k)+': '+(v or 'No registrado') for k, v in row['patient'].items()), *(names.get(k, k)+': '+v for k, v in row['errors'].items()), *row['duplicates']]))

    def toggle(self):
        row = self.current()
        if not row or self.busy or row['errors']:
            return
        if row['number'] in self.selected:
            self.selected.remove(row['number'])
        else:
            if row['duplicates']:
                if not messagebox.askyesno('Persona distinta', '\n'.join(row['duplicates'])+'\n¿Crear un expediente separado para esta persona?', parent=self):
                    return
                self.accepted_duplicates.add(row['number'])
            self.selected.add(row['number'])
        self.render()

    def import_selected(self):
        if not self.preview or self.busy or not self.selected:
            return
        self.busy = True
        self.commit.state(['disabled'])
        preview, selected, duplicates = self.preview, set(self.selected), set(self.accepted_duplicates)
        self.notice.configure(text=f'Guardando {len(selected)} pacientes en una transacción…')
        def work():
            try:
                return self.app.transfer.import_patients(preview, selected, duplicates)
            except (ValueError, OSError) as exc:
                return exc
        def done(result):
            if not self.winfo_exists():
                return
            self.busy = False
            if isinstance(result, Exception):
                self.notice.configure(text=str(result)+' · no se publicaron registros parciales.')
                self.commit.state(['!disabled'])
            else:
                self.notice.configure(text=f"{result['count']} pacientes importados. Puedes consultarlos en Pacientes.")
                self.preview = None
        self.app.background(work, done, settled=lambda future: setattr(self, 'busy', False))

    def close(self):
        if not self.busy:
            self.destroy()
