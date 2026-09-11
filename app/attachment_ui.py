"""Cola de documentos, galería y visores locales."""
from pathlib import Path
import os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from PIL import Image, ImageTk
from app.attachments import CATEGORIES
from app.widgets import Form
from app.clinical_models import display_date

class AttachmentPanel(ttk.Frame):
    def __init__(self, parent, app, patient_id=None, encounter_id=None, draft_id=None):
        super().__init__(parent)
        self.app = app
        self.target = dict(patient_id=patient_id, encounter_id=encounter_id, draft_id=draft_id)
        self.queue, self.busy, self.results = [], False, []
        self.photos = []
        ttk.Label(self, text='Documentos e imágenes', style='Section.TLabel').pack(anchor='w', pady=8)
        self.destination = ttk.Label(self, text='Pendientes del alta · expediente general' if draft_id else 'Adjuntos de esta consulta' if encounter_id else 'Documentos del expediente y sus consultas', style='Subtitle.TLabel')
        self.destination.pack(anchor='w')
        self.drop = ttk.Label(self, text='Arrastra archivos aquí · JPEG, PNG, PDF y DOCX · hasta 50 MiB', padding=14, style='Card.TLabel')
        self.drop.pack(fill='x', pady=10)
        if hasattr(self.drop, 'drop_target_register'):
            self.drop.drop_target_register('DND_Files')
            self.drop.dnd_bind('<<Drop>>', lambda e: self.add_paths(self.tk.splitlist(e.data)))
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        ttk.Button(bar, text='+ Agregar archivos', command=self.choose).pack(side='left')
        self.category = tk.StringVar(value='Otro documento')
        self.categories = app.store.read('config/attachment_categories.json', CATEGORIES)
        ttk.Combobox(bar, textvariable=self.category, values=self.categories, width=20).pack(side='left', padx=8)
        ttk.Button(bar, text='Aplicar categoría a la cola', command=self.categorize).pack(side='left')
        self.queue_tree = ttk.Treeview(self, columns=('name', 'category', 'status'), show='headings', height=3)
        for key, title in [('name', 'Archivo pendiente'), ('category', 'Categoría'), ('status', 'Estado')]:
            self.queue_tree.heading(key, text=title)
            self.queue_tree.column(key, width=170, minwidth=80)
        self.queue_tree.pack(fill='x', pady=8)
        qbar = ttk.Frame(self)
        qbar.pack(fill='x')
        ttk.Button(qbar, text='Incorporar / reintentar fallidos', command=self.start, style='Primary.TButton').pack(side='left')
        ttk.Button(qbar, text='Quitar pendiente', command=self.remove).pack(side='left', padx=8)
        ttk.Button(qbar, text='Detalles del pendiente', command=self.queue_details).pack(side='left')
        self.progress = ttk.Progressbar(self, maximum=1)
        self.progress.pack(fill='x', pady=8)
        self.notice = ttk.Label(self, text='', style='Subtitle.TLabel', wraplength=650)
        self.notice.pack(fill='x')
        filters = ttk.Frame(self)
        filters.pack(fill='x', pady=(15, 5))
        self.search = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search).pack(side='left', fill='x', expand=True)
        self.archived = tk.BooleanVar()
        ttk.Checkbutton(filters, text='Incluir archivados', variable=self.archived, command=self.refresh).pack(side='left', padx=8)
        self.gallery_mode = tk.BooleanVar()
        ttk.Checkbutton(filters, text='Galería', variable=self.gallery_mode, command=self.refresh).pack(side='left')
        self.tree = ttk.Treeview(self, columns=('title', 'category', 'date', 'origin'), show='headings', height=5)
        for key, title in [('title', 'Documento'), ('category', 'Categoría'), ('date', 'Incorporado'), ('origin', 'Origen')]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=150, minwidth=70)
        self.tree.pack(fill='both', expand=True, pady=8)
        self.tree.bind('<Double-1>', lambda e: self.open())
        self.gallery = ttk.Frame(self)
        actions = ttk.Frame(self)
        actions.pack(fill='x')
        for label, command in [('Ver', self.open), ('Editar detalles', self.details), ('Archivar / restaurar', self.archive), ('Exportar', self.export), ('Nueva versión', self.replace)]:
            ttk.Button(actions, text=label, command=command, style='Link.TButton').pack(side='left', padx=(0, 6))
        self.search.trace_add('write', lambda *a: self.refresh())
        self.refresh()

    def selected(self):
        return self.app.attachments.get(self.tree.selection()[0]) if self.tree.selection() else None

    def choose(self):
        self.add_paths(filedialog.askopenfilenames(parent=self, filetypes=[('Documentos admitidos', '*.jpg *.jpeg *.png *.pdf *.docx')]))

    def add_paths(self, paths):
        if self.busy:
            return
        for path in paths:
            self.queue.append({'path': path, 'category': self.category.get(), 'notes': '', 'status': 'Pendiente'})
        self.render_queue()

    def render_queue(self):
        self.queue_tree.delete(*self.queue_tree.get_children())
        for i, row in enumerate(self.queue):
            self.queue_tree.insert('', 'end', iid=str(i), values=(Path(row['path']).name, row['category'], row['status']))

    def categorize(self):
        if self.busy:
            return
        for row in self.queue:
            if row['status'] != 'Guardado':
                row['category'] = self.category.get()
        self.render_queue()

    def remove(self):
        if self.queue_tree.selection() and not self.busy:
            del self.queue[int(self.queue_tree.selection()[0])]
            self.render_queue()

    def queue_details(self):
        if not self.queue_tree.selection() or self.busy:
            return
        row = self.queue[int(self.queue_tree.selection()[0])]
        notes = simpledialog.askstring('Detalles del archivo', 'Descripción u observaciones:', initialvalue=row['notes'], parent=self)
        if notes is not None:
            row['notes'] = notes

    def start(self):
        if self.busy:
            return
        pending = [r for r in self.queue if r['status'] != 'Guardado']
        if not pending:
            return
        reason = ''
        if self.target['encounter_id']:
            encounter = self.app.store.read(f"data/encounters/{self.target['encounter_id']}.json")
            if encounter['status'] != 'Borrador':
                reason = simpledialog.askstring('Documento posterior', 'Motivo de incorporación a esta consulta:', parent=self)
                if not reason:
                    return
        self.busy = True
        self.notice.configure(text='Copiando y verificando archivos…')
        progress = [0.0]
        def work():
            for i, row in enumerate(pending):
                try:
                    row['status'] = 'Copiando'
                    self.app.attachments.add(row['path'], **self.target, category=row['category'], notes=row['notes'], reason=reason,
                                             replaces=row.get('replaces'), allow_duplicate=row.get('duplicate', False),
                                             progress=lambda v: progress.__setitem__(0, (i+v)/len(pending)))
                    row['status'] = 'Guardado'
                except Exception as exc:
                    row['status'] = str(exc)
                progress[0] = (i+1)/len(pending)
            return True
        def done(result):
            self.busy = False
            self.render_queue()
            self.refresh()
            self.notice.configure(text='Proceso terminado. Revisa el resultado de cada archivo.')
        self.app.background(work, done)
        def tick():
            if self.winfo_exists():
                self.progress['value'] = progress[0]
                if self.busy:
                    self.after(80, tick)
        tick()

    def refresh(self):
        try:
            rows = self.app.attachments.list(**self.target, archived=self.archived.get())
        except ValueError as exc:
            self.notice.configure(text=str(exc))
            return
        query = self.search.get().casefold()
        rows = [r for r in rows if query in ' '.join(str(r.get(k, '')) for k in ('title', 'original_name', 'notes', 'category', 'document_date', 'doctor_id')).casefold()]
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert('', 'end', iid=row['id'], values=(('Archivado · ' if row['archived'] else '')+row['title'], row['category'], display_date(row['created_at']), 'Consulta' if row.get('encounter_id') else 'Expediente'))
        for child in self.gallery.winfo_children():
            child.destroy()
        self.photos.clear()
        self.gallery.pack_forget()
        if self.gallery_mode.get():
            self.gallery.pack(fill='x', pady=8)
            for i, row in enumerate(rows[:12]):
                button = ttk.Button(self.gallery, text=row['title'][:20], compound='top', command=lambda r=row: self.preview(r))
                button.grid(row=i//4, column=i%4, padx=5, pady=5, sticky='ew')
                if row['mime'].startswith('image/'):
                    try:
                        with Image.open(self.app.attachments.path(row['id'])) as source:
                            source.thumbnail((90, 70))
                            photo = ImageTk.PhotoImage(source.copy())
                        self.photos.append(photo)
                        button.configure(image=photo)
                    except (ValueError, OSError):
                        button.configure(text='Archivo ausente\n'+row['title'][:20])

    def open(self):
        row = self.selected()
        if row:
            self.preview(row)

    def preview(self, row):
        def action():
            path = self.app.attachments.path(row['id'])
            if row['mime'].endswith('wordprocessingml.document'):
                if messagebox.askyesno('Abrir documento', 'DOCX sin vista previa interna. ¿Abrir con la aplicación predeterminada?', parent=self):
                    os.startfile(path)
                return
            DocumentViewer(self.app, path, row['title'])
        self.app.guard(action)

    def details(self):
        row = self.selected()
        if not row:
            return
        win = self.app.window('Detalles del documento', '660x600')
        form = Form(win, [('title', 'Título', None), ('category', 'Categoría', self.categories), ('document_date', 'Fecha del documento', 'date'), ('notes', 'Descripción', 'text')], row, theme=self.app.theme)
        form.pack(fill='both', expand=True, padx=20, pady=15)
        reason = tk.StringVar()
        ttk.Label(win, text='Motivo del cambio').pack(anchor='w', padx=20)
        ttk.Entry(win, textvariable=reason).pack(fill='x', padx=20)
        def save():
            self.app.attachments.update(row['id'], form.values(), row['revision'], reason.get())
            win.destroy()
            self.refresh()
        ttk.Button(win, text='Guardar', command=lambda: self.app.guard(save)).pack(pady=15)
        self.app.theme._walk(win)

    def archive(self):
        row = self.selected()
        if row:
            reason = simpledialog.askstring('Archivar / restaurar documento', 'Motivo (el archivo original se conserva):', parent=self)
            if reason:
                self.app.guard(lambda: self.app.attachments.update(row['id'], {'archived': not row['archived']}, row['revision'], reason))
                self.refresh()

    def replace(self):
        row = self.selected()
        if row:
            path = filedialog.askopenfilename(parent=self)
            if path:
                self.queue.append({'path': path, 'category': row['category'], 'notes': '', 'status': 'Pendiente', 'replaces': row['id']})
                self.render_queue()

    def export(self):
        row = self.selected()
        if row:
            target = filedialog.asksaveasfilename(parent=self, initialfile=row['original_name'])
            if target:
                def work():
                    import shutil
                    shutil.copy2(self.app.attachments.path(row['id']), target)
                    self.app.auth.audit('exportar_adjunto', row['id'])
                self.app.background(work, lambda _: self.notice.configure(text='Documento exportado.'))

class DocumentViewer(tk.Toplevel):
    def __init__(self, app, path, title='Documento'):
        super().__init__(app)
        self.app, self.path, self.page, self.zoom = app, Path(path), 0, 1.0
        self.request_id = 0
        self.title(title)
        self.geometry('920x700')
        self.transient(app)
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill='x')
        for label, command in [('Anterior', lambda: self.turn(-1)), ('Siguiente', lambda: self.turn(1)), ('−', lambda: self.scale(.8)), ('+', lambda: self.scale(1.25)), ('Ajustar', self.fit)]:
            ttk.Button(bar, text=label, command=command).pack(side='left', padx=3)
        self.info = ttk.Label(bar)
        self.info.pack(side='right')
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(frame, highlightthickness=0)
        vs = ttk.Scrollbar(frame, command=self.canvas.yview)
        hs = ttk.Scrollbar(frame, orient='horizontal', command=self.canvas.xview)
        vs.pack(side='right', fill='y')
        hs.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.canvas.bind('<ButtonPress-1>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B1-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.app.theme._walk(self)
        self.after(60, self.fit)

    def turn(self, delta):
        self.page = max(0, min(getattr(self, 'pages', 1)-1, self.page+delta))
        self.render()
    def scale(self, factor):
        self.zoom = max(.1, min(4, self.zoom*factor))
        self.render()
    def fit(self):
        self.zoom = max(.2, (self.canvas.winfo_width()-40)/800)
        self.render()
    def render(self):
        self.request_id += 1
        request, page, zoom = self.request_id, self.page, self.zoom
        self.info.configure(text='Cargando página…')
        def work():
            if self.path.suffix.lower() == '.pdf':
                import pypdfium2 as pdfium
                with pdfium.PdfDocument(self.path) as document:
                    count = len(document)
                    with document[min(page, count-1)] as pdfpage:
                        factor = min(3, 800*zoom/pdfpage.get_width())
                        bitmap = pdfpage.render(scale=factor)
                        image = bitmap.to_pil().copy()
                        bitmap.close()
                return image, count
            with Image.open(self.path) as source:
                source.thumbnail((int(800*zoom), int(1200*zoom)))
                return source.copy(), 1
        def done(result):
            if not self.winfo_exists() or request != self.request_id:
                return
            im, self.pages = result
            self.photo = ImageTk.PhotoImage(im)
            self.canvas.delete('all')
            self.canvas.create_image(10, 10, image=self.photo, anchor='nw')
            self.canvas.configure(scrollregion=(0, 0, im.width+20, im.height+20))
            self.info.configure(text=f'Página {self.page+1} de {self.pages}')
        self.app.background(work, done)
