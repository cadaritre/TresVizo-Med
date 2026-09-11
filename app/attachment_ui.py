"""Cola de documentos, galería y visores locales."""
from pathlib import Path
import os
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from PIL import Image, ImageTk
from app.attachments import CATEGORIES
from app.widgets import Form, Collapsible
from app.clinical_models import display_date

class AttachmentPanel(ttk.Frame):
    def __init__(self, parent, app, patient_id=None, encounter_id=None, draft_id=None, on_photo=None, changed=lambda: None, on_preview=None, on_details=None):
        super().__init__(parent)
        self.app = app
        self.on_preview, self.on_details = on_preview, on_details
        self.target = dict(patient_id=patient_id, encounter_id=encounter_id, draft_id=draft_id)
        self.queue, self.busy, self.results = [], False, []
        self.photos = []
        self.thumb_ticket = 0
        self.page = 0
        self.on_photo = on_photo
        self.changed = changed
        ttk.Label(self, text='Documentos e imágenes', style='Section.TLabel').pack(anchor='w', pady=8)
        self.destination = ttk.Label(self, text='Pendientes del alta · expediente general' if draft_id else 'Adjuntos de esta consulta' if encounter_id else 'Documentos del expediente y sus consultas', style='Subtitle.TLabel')
        self.destination.pack(anchor='w')
        self.drop = ttk.Label(self, text='Arrastra archivos aquí · JPEG, PNG, PDF y DOCX · hasta 50 MiB', padding=14, style='Card.TLabel')
        self.drop.pack(fill='x', pady=10)
        if hasattr(self.drop, 'drop_target_register'):
            self.drop.drop_target_register('DND_Files')
            self.drop.dnd_bind('<<Drop>>', self.on_drop)
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        ttk.Button(bar, text='+ Agregar archivos', command=self.choose).pack(side='left')
        self.category = tk.StringVar(value='Otro documento')
        self.categories = app.store.read('config/attachment_categories.json', CATEGORIES)
        self.category_controls = ttk.Frame(bar)
        ttk.Combobox(self.category_controls, textvariable=self.category, values=self.categories, width=20).pack(side='left', padx=8)
        ttk.Button(self.category_controls, text='Aplicar categoría a la cola', command=self.categorize).pack(side='left')
        self.queue_tree = ttk.Treeview(self, columns=('name', 'type', 'category', 'status'), show='headings', height=3)
        for key, title in [('name', 'Archivo seleccionado'), ('type', 'Tipo'), ('category', 'Categoría'), ('status', 'Estado')]:
            self.queue_tree.heading(key, text=title)
            self.queue_tree.column(key, width=70 if key == 'type' else 220 if key == 'status' else 170, minwidth=60)
        self.queue_tree.pack(fill='x', pady=8)
        qbar = self.queue_actions = ttk.Frame(self)
        qbar.pack(fill='x')
        ttk.Button(qbar, text='Incorporar / reintentar fallidos', command=self.start, style='Primary.TButton').pack(side='left')
        ttk.Button(qbar, text='Quitar pendiente', command=self.remove).pack(side='left', padx=8)
        ttk.Button(qbar, text='Detalles del pendiente', command=self.queue_details).pack(side='left')
        ttk.Button(qbar, text='Volver a elegir archivo', command=self.reselect).pack(side='left', padx=8)
        def layout_queue_actions(event=None):
            buttons = qbar.winfo_children()
            columns = 4 if sum(button.winfo_reqwidth()+12 for button in buttons) <= qbar.winfo_width() else 2
            if getattr(qbar, 'columns', None) == columns:
                return
            qbar.columns = columns
            for button in buttons:
                button.pack_forget()
            for index, button in enumerate(buttons):
                button.grid(row=index//columns, column=index%columns, sticky='w', padx=(0, 8), pady=3)
            for index in range(4):
                qbar.columnconfigure(index, weight=1 if index < columns else 0)
        qbar.bind('<Configure>', layout_queue_actions)
        self.progress = ttk.Progressbar(self, maximum=1)
        self.progress.pack(fill='x', pady=8)
        self.notice = ttk.Label(self, text='', style='Subtitle.TLabel', wraplength=650)
        self.notice.pack(fill='x')
        self.empty_library = ttk.Label(self, text='Todavía no hay documentos incorporados. Agrega archivos cuando los necesites.', style='Subtitle.TLabel', wraplength=650)
        self.library = library = ttk.Frame(self)
        library.pack(fill='x')
        filters = ttk.Frame(library)
        filters.pack(fill='x', pady=(15, 5))
        self.search = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search).pack(side='left', fill='x', expand=True)
        self.archived = tk.BooleanVar()
        ttk.Checkbutton(filters, text='Incluir archivados', variable=self.archived, command=self.refresh).pack(side='left', padx=8)
        self.gallery_mode = tk.BooleanVar()
        ttk.Checkbutton(filters, text='Galería', variable=self.gallery_mode, command=self.refresh).pack(side='left')
        filter_box = Collapsible(library,'Filtrar documentos por categoría, fecha y doctor')
        filter_box.pack(fill='x')
        self.doctors = {u['name']+' · '+u['username']:u['id'] for u in app.auth.users()}
        self.filter_form = Form(filter_box.body,[('category','Categoría',['Todas',*self.categories]),('doctor','Incorporado por',['Todos',*self.doctors]),
                                                ('from','Desde','date'),('to','Hasta','date'),('origin','Origen',['Todos','Expediente general','Consulta']),
                                                ('sort','Orden de fecha',['Incorporación','Fecha del documento'])],{'category':'Todas','doctor':'Todos','origin':'Todos','sort':'Incorporación'},theme=app.theme)
        self.filter_form.pack(fill='x')
        ttk.Button(filter_box.body,text='Aplicar filtros',command=self.refresh).pack(anchor='w',pady=6)
        self.tree = ttk.Treeview(library, columns=('title', 'category', 'date', 'origin'), show='headings', height=5)
        for key, title in [('title', 'Documento'), ('category', 'Categoría'), ('date', 'Incorporado'), ('origin', 'Origen')]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=150, minwidth=70)
        self.tree.pack(fill='x', pady=8)
        self.tree.configure(selectmode='extended')
        self.tree.bind('<Double-1>', lambda e: self.open())
        pager = ttk.Frame(library)
        pager.pack(fill='x')
        self.page_label = ttk.Label(pager, style='Subtitle.TLabel')
        self.page_label.pack(side='left')
        ttk.Button(pager, text='Anterior', command=lambda: self.turn(-1), style='Link.TButton').pack(side='right')
        ttk.Button(pager, text='Siguiente', command=lambda: self.turn(1), style='Link.TButton').pack(side='right')
        self.gallery = ttk.Frame(library)
        actions = ttk.Frame(library)
        actions.pack(fill='x')
        self.document_actions = {}
        for label, command in [('Ver', self.open), ('Editar detalles', self.details), ('Archivar / restaurar', self.archive), ('Exportar', self.export), ('Nueva versión', self.replace)]:
            button = ttk.Button(actions, text=label, command=command, style='Link.TButton')
            button.pack(side='left', padx=(0, 6))
            self.document_actions[label] = button
        self.tree.bind('<<TreeviewSelect>>', self.selection_changed)
        if not draft_id:
            ttk.Button(library, text='Exportar expediente con documentos seleccionados…', style='Link.TButton', command=self.package).pack(anchor='w',pady=5)
        if on_photo:
            ttk.Button(library,text='Usar imagen seleccionada como foto del paciente',style='Link.TButton',command=self.use_photo).pack(anchor='w',pady=4)
        self.search_timer = None
        self.search.trace_add('write', self.search_changed)
        self.restore_queue([])
        self.refresh()

    def search_changed(self, *args):
        if self.search_timer: self.after_cancel(self.search_timer)
        self.page = 0
        self.search_timer = self.after(250, self.refresh)

    def turn(self, delta):
        self.page = max(0, self.page+delta)
        self.refresh()

    def selected(self):
        return self.app.attachments.get(self.tree.selection()[0]) if self.tree.selection() else None

    def selection_changed(self, event=None):
        row = self.selected()
        for button in self.document_actions.values():
            button.state(['!disabled'] if row else ['disabled'])
        self.document_actions['Archivar / restaurar'].configure(text='Restaurar documento' if row and row.get('archived') else 'Archivar documento')

    def on_drop(self, event):
        if self.busy:
            return 'refuse_drop'
        self.add_paths(self.tk.splitlist(event.data))
        return 'copy'

    def choose(self):
        self.add_paths(filedialog.askopenfilenames(parent=self, filetypes=[('Documentos admitidos', '*.jpg *.jpeg *.png *.pdf *.docx')]))

    def add_paths(self, paths):
        if self.busy:
            return
        for path in paths:
            self.queue.append({'path': path, 'category': self.category.get(), 'notes': '', 'status': 'Pendiente'})
        self.render_queue()

    def render_queue(self):
        if self.queue:
            self.category_controls.pack(side='left')
        else:
            self.category_controls.pack_forget()
        selected = self.queue_tree.selection()
        self.queue_tree.delete(*self.queue_tree.get_children())
        for row in self.queue:
            row.setdefault('id', str(uuid.uuid4()))
            self.queue_tree.insert('', 'end', iid=row['id'], values=(Path(row['path']).name, Path(row['path']).suffix.lstrip('.').upper(), row['category'], row['status']))
        self.queue_tree.selection_set([key for key in selected if self.queue_tree.exists(key)])
        if self.queue:
            self.queue_actions.pack(fill='x', before=self.notice)
            self.queue_tree.pack(fill='x', pady=8, before=self.queue_actions)
            self.queue_tree.configure(height=min(5, len(self.queue)))
        else:
            self.queue_tree.pack_forget()
            self.queue_actions.pack_forget()
        if not self.busy:
            self.progress.pack_forget()
        try:
            self.app.attachments.save_queue(self.queue, **self.target)
        except (ValueError, OSError):
            self.notice.configure(text='La selección sigue en memoria y todavía no está protegida en disco. Reintenta antes de salir.')
        self.changed()

    def restore_queue(self, queue):
        saved = self.app.attachments.load_queue(**self.target)
        self.queue = self.app.attachments.recover_queue(queue, **self.target) if saved is None else saved
        self.render_queue()

    def selected_pending(self):
        selected = self.queue_tree.selection()
        return next((r for r in self.queue if selected and r['id'] == selected[0]), None)

    def reselect(self):
        row = self.selected_pending()
        if self.busy or not row or row['status'] == 'Guardado':
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[('Documentos admitidos', '*.jpg *.jpeg *.png *.pdf *.docx')])
        if path:
            row.update(path=path, status='Pendiente')
            self.render_queue()

    def categorize(self):
        if self.busy:
            return
        for row in self.queue:
            if row['status'] != 'Guardado':
                row['category'] = self.category.get()
        self.render_queue()

    def remove(self):
        if self.queue_tree.selection() and not self.busy:
            self.queue.remove(self.selected_pending())
            self.render_queue()

    def queue_details(self):
        if not self.queue_tree.selection() or self.busy:
            return
        row = self.selected_pending()
        notes = simpledialog.askstring('Detalles del archivo', 'Descripción u observaciones:', initialvalue=row['notes'], parent=self)
        if notes is not None:
            row['notes'] = notes
        if 'idéntico' in row['status']:
            row['duplicate'] = messagebox.askyesno('Archivo ya incorporado','¿Incorporar otra copia y conservar ambas asociaciones?',parent=self)
        self.changed()

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
        self.queue_persistence_error = False
        actor_id = self.app.auth.require()['id']
        target = dict(self.target)
        reported = False
        self.notice.configure(text='Copiando y verificando archivos…')
        self.progress.pack(fill='x', pady=8, before=self.notice)
        progress = [0.0]
        def work():
            for i, row in enumerate(pending):
                try:
                    row['status'] = 'Copiando'
                    item = self.app.attachments.add(row['path'], **target, category=row['category'], notes=row['notes'], reason=reason,
                                             operation_id=row['id'], actor_id=actor_id,
                                             replaces=row.get('replaces'), allow_duplicate=row.get('duplicate', False),
                                             progress=lambda v: progress.__setitem__(0, (i+v)/len(pending)))
                    row['attachment_id'] = item['id']
                    row['status'] = 'Guardado'
                except FileNotFoundError:
                    row['status'] = 'Original no disponible · vuelve a elegir el archivo'
                except PermissionError:
                    row['status'] = 'Acceso denegado · revisa permisos y reintenta'
                except OSError as exc:
                    import errno
                    row['status'] = 'Sin espacio para guardar · libera espacio o conserva el pendiente' if exc.errno == errno.ENOSPC else 'No se pudo copiar · revisa el archivo y reintenta'
                except ValueError as exc:
                    row['status'] = str(exc)
                except Exception:
                    row['status'] = 'No se pudo validar el archivo · conserva el pendiente y revisa su formato'
                try:
                    self.app.attachments.save_queue(self.queue, **target)
                except (ValueError, OSError):
                    self.queue_persistence_error = True
                progress[0] = (i+1)/len(pending)
            return True
        def done(result):
            nonlocal reported
            if reported:
                return
            reported = True
            if not self.winfo_exists():return
            self.render_queue()
            self.refresh()
            self.notice.configure(text='Proceso terminado. Revisa el resultado de cada archivo.'+(' La cola no se pudo actualizar en disco; las copias marcadas Guardado sí están incorporadas.' if self.queue_persistence_error else ''))
        self.job = self.app.background(work, done, settled=lambda future: setattr(self, 'busy', False))
        def tick():
            if self.winfo_exists() and (self.app.auth.current or {}).get('id') == actor_id:
                if self.app.locked:
                    self.after(100, tick)
                    return
                self.progress['value'] = progress[0]
                for row in self.queue:
                    if self.queue_tree.exists(row['id']):
                        self.queue_tree.set(row['id'],'status',row['status'])
                if self.job.done():
                    self.busy = False
                    done(self.job.result())
                else:
                    self.after(80, tick)
        tick()

    def refresh(self):
        try:
            all_rows = self.app.attachments.list(**self.target, archived=True)
            rows = all_rows if self.archived.get() else [row for row in all_rows if not row.get('archived')]
        except ValueError as exc:
            self.notice.configure(text=str(exc))
            return
        if all_rows:
            self.empty_library.pack_forget()
            self.library.pack(fill='x')
        else:
            self.library.pack_forget()
            self.empty_library.pack(fill='x', pady=12)
        query = self.search.get().casefold()
        try:
            filters = self.filter_form.values()
        except ValueError as exc:
            self.notice.configure(text=str(exc))
            return
        reverse_doctors = {uid:name for name,uid in self.doctors.items()}
        rows = [r for r in rows if query in (' '.join(str(r.get(k,'')) for k in ('title','original_name','notes','category','document_date'))+' '+reverse_doctors.get(r['doctor_id'],'')).casefold()]
        if filters['category'] != 'Todas':rows = [r for r in rows if r['category'] == filters['category']]
        if filters['doctor'] != 'Todos':rows = [r for r in rows if r['doctor_id'] == self.doctors.get(filters['doctor'])]
        if filters['origin'] != 'Todos':rows = [r for r in rows if bool(r.get('encounter_id')) == (filters['origin'] == 'Consulta')]
        date_key = 'document_date' if filters['sort'] == 'Fecha del documento' else 'created_at'
        if filters['from']:rows = [r for r in rows if r.get(date_key,'')[:10] >= filters['from']]
        if filters['to']:rows = [r for r in rows if r.get(date_key,'') and r[date_key][:10] <= filters['to']]
        rows.sort(key=lambda r:r.get(date_key,'') or '',reverse=True)
        page_size = 12 if self.gallery_mode.get() else 50
        self.page = min(self.page, max(0, (len(rows)-1)//page_size))
        self.page_label.configure(text=f'{len(rows)} documentos · página {self.page+1}')
        rows = rows[self.page*page_size:(self.page+1)*page_size]
        self.tree.configure(height=max(2, min(6, len(rows))))
        selected = self.tree.selection()
        self.tree.heading('date',text='Fecha del documento' if date_key == 'document_date' else 'Incorporado')
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert('', 'end', iid=row['id'], values=(('Archivado · ' if row['archived'] else '')+row['title'], row['category'], display_date(row.get(date_key,'')), 'Consulta' if row.get('encounter_id') else 'Expediente'))
        self.tree.selection_set([i for i in selected if self.tree.exists(i)])
        self.selection_changed()
        for child in self.gallery.winfo_children():
            child.destroy()
        self.photos.clear()
        self.gallery.pack_forget()
        if self.gallery_mode.get():
            self.gallery.pack(fill='x', pady=8)
            self.thumb_ticket += 1
            ticket = self.thumb_ticket
            buttons = {}
            for i, row in enumerate(rows[:12]):
                button = ttk.Button(self.gallery, text=row['title'][:20], compound='top', command=lambda r=row: self.preview(r))
                button.grid(row=i//4, column=i%4, padx=5, pady=5, sticky='ew')
                buttons[row['id']] = button
            def work():
                result = []
                for row in rows[:12]:
                    try:
                        result.append((row['id'],self.app.attachments.thumbnail(row['id'])))
                    except (ValueError, OSError):
                        result.append((row['id'],None))
                return result
            def done(result):
                if not self.winfo_exists() or ticket != self.thumb_ticket or not self.gallery_mode.get():return
                for identifier,path in result:
                    button = buttons[identifier]
                    if path and button.winfo_exists():
                        with Image.open(path) as source:
                            source.thumbnail((90,70))
                            photo = ImageTk.PhotoImage(source.copy(),master=self)
                        self.photos.append(photo)
                        button.configure(image=photo)
            self.app.background(work,done)

    def use_photo(self):
        row = self.selected()
        if row and row['mime'].startswith('image/'):
            self.on_photo(row['id'])
            self.notice.configure(text='Imagen elegida para el paciente. Se aplicará al guardar el registro.')

    def open(self):
        row = self.selected()
        if row:
            self.preview(row)

    def preview(self, row):
        if self.on_preview:
            return self.on_preview(row)
        def action():
            path = self.app.attachments.path(row['id'])
            if row['mime'].endswith('wordprocessingml.document'):
                if messagebox.askyesno('Abrir documento', 'DOCX sin vista previa interna. ¿Abrir con la aplicación predeterminada?', parent=self):
                    os.startfile(path)
                return
            DocumentViewer(self.app, path, row['title'])
        self.app.guard(action)

    def details(self):
        if self.on_details:
            return self.on_details()
        row = self.selected()
        if not row:
            return
        from app.document_edit_ui import edit_document
        return edit_document(self, row)

    def archive(self):
        row = self.selected()
        if row:
            reason = simpledialog.askstring('Restaurar documento' if row['archived'] else 'Archivar documento', 'Motivo (el archivo original se conserva):', parent=self)
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

    def package(self):
        selected = list(self.tree.selection())
        target = filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile='expediente.zip',filetypes=[('Expediente y documentos','*.zip')])
        if target:
            self.app.background(lambda:self.app.transfer.export_package(target,self.target['patient_id'],selected,self.target['encounter_id']),
                                lambda _:self.notice.configure(text='Expediente y documentos seleccionados exportados.'))

class DocumentViewer(tk.Toplevel):
    def __init__(self, app, path, title='Documento'):
        super().__init__(app)
        self.app, self.path, self.page, self.zoom = app, Path(path), 0, 1.0
        self.request_id = 0
        self.title(title)
        self.geometry('920x700')
        self.transient(app)
        bar = self.toolbar = ttk.Frame(self, padding=8)
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
                    pdfpage = document[min(page, count-1)]
                    try:
                        factor = min(3, 800*zoom/pdfpage.get_width())
                        bitmap = pdfpage.render(scale=factor)
                        try:
                            image = bitmap.to_pil().copy()
                        finally:
                            bitmap.close()
                    finally:
                        pdfpage.close()
                return image, count
            with Image.open(self.path) as source:
                source.thumbnail((int(800*zoom), int(1200*zoom)))
                return source.copy(), 1
        def done(result):
            if not self.winfo_exists() or request != self.request_id:
                return
            im, self.pages = result
            self.photo = ImageTk.PhotoImage(im,master=self)
            self.canvas.delete('all')
            self.canvas.create_image(10, 10, image=self.photo, anchor='nw')
            self.canvas.configure(scrollregion=(0, 0, im.width+20, im.height+20))
            self.info.configure(text=f'Página {self.page+1} de {self.pages}')
        self.app.background(work, done)
