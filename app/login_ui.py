"""Selección de perfiles y acceso, sin modificar las preferencias del doctor."""
import tkinter as tk
from tkinter import ttk, font as tkfont

from app.components import ScrollFrame
from app.services import normalized
from app.storage import DataError
from app.version import VERSION


class LoginPage(ScrollFrame):
    PAGE_SIZE = 6

    def __init__(self, parent, app, users):
        super().__init__(parent)
        self.app, self.users = app, users
        self.scale = app.ui_scale
        self.page = 0
        self.cards = {}
        self.selected = None
        self.query = tk.StringVar()
        self.password = tk.StringVar()
        self.visible = tk.BooleanVar()
        self.name = tk.StringVar()
        self.detail = tk.StringVar()
        self.count = tk.StringVar()
        self.error = tk.StringVar()
        self.body.columnconfigure(0, weight=1)
        self.outer = ttk.Frame(self.body, padding=(32, 24))
        self.outer.grid(row=0, column=0, sticky='n')
        self.outer.columnconfigure(0, weight=1)
        header = ttk.Frame(self.outer)
        header.grid(row=0, column=0, sticky='ew')
        app.brand(header, size=56).pack(side='left', padx=(0, 16))
        identity = ttk.Frame(header)
        identity.pack(side='left', fill='x', expand=True)
        ttk.Label(identity, text='TresVizo Med', style='Login.Brand.TLabel').pack(anchor='w')
        self.clinic_label = ttk.Label(identity, text=app.identity.values['clinic_name'], style='Subtitle.TLabel')
        self.clinic_label.pack(anchor='w', pady=(2, 0))
        ttk.Separator(self.outer).grid(row=1, column=0, sticky='ew', pady=(22, 26))
        self.content = ttk.Frame(self.outer)
        self.content.grid(row=2, column=0, sticky='ew')
        self.content.columnconfigure(0, weight=1)
        self.profiles = ttk.Frame(self.content)
        ttk.Label(self.profiles, text='Bienvenido a tu consultorio', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self.profiles, text='Elige tu perfil para continuar con tus pacientes.',
                  style='Subtitle.TLabel').pack(anchor='w', pady=(6, 20))
        self.search_row = ttk.Frame(self.profiles)
        if len(users) > 4:
            self.search_row.pack(fill='x', pady=(0, 16))
        ttk.Label(self.search_row, text='Buscar médico', style='Login.Eyebrow.TLabel').pack(anchor='w', pady=(0, 6))
        self.search = ttk.Entry(self.search_row, textvariable=self.query, width=1)
        self.search.pack(side='left', fill='x', expand=True)
        ttk.Button(self.search_row, text='Limpiar', style='Link.TButton',
                   command=lambda: self.query.set('')).pack(side='left', padx=(8, 0))
        self.search.bind('<Down>', self.focus_result)
        self.search.bind('<Return>', self.choose_result)
        self.gallery = ttk.Frame(self.profiles)
        self.gallery.pack(fill='x')
        self.gallery.bind('<Configure>', self.layout_cards)
        self.empty = ttk.Frame(self.gallery, style='Card.TFrame', padding=24)
        ttk.Label(self.empty, text='No encontramos ese perfil', style='Login.CardTitle.TLabel').pack(anchor='w')
        ttk.Label(self.empty, text='Prueba con el nombre, usuario o especialidad.',
                  style='Login.CardMuted.TLabel').pack(anchor='w', pady=(6, 0))
        controls = ttk.Frame(self.profiles)
        controls.pack(fill='x', pady=(12, 0))
        ttk.Label(controls, textvariable=self.count, style='Subtitle.TLabel').pack(side='left')
        self.next_button = ttk.Button(controls, text='Siguiente →', style='Link.TButton', command=lambda: self.turn(1))
        self.next_button.pack(side='right')
        self.previous_button = ttk.Button(controls, text='← Anterior', style='Link.TButton', command=lambda: self.turn(-1))
        self.previous_button.pack(side='right', padx=(0, 8))

        self.access = ttk.Frame(self.content, style='Login.Panel.TFrame', padding=26)
        ttk.Label(self.access, text='INICIAR SESIÓN', style='Login.CardEyebrow.TLabel').pack(anchor='w')
        self.avatar = ttk.Label(self.access, style='Card.TLabel')
        self.avatar.pack(anchor='w', pady=(22, 12))
        self.name_label = ttk.Label(self.access, textvariable=self.name, style='Login.CardTitle.TLabel')
        self.name_label.pack(fill='x')
        self.detail_label = ttk.Label(self.access, textvariable=self.detail, style='Login.CardMuted.TLabel')
        self.detail_label.pack(fill='x', pady=(5, 22))
        ttk.Label(self.access, text='Contraseña', style='Card.TLabel').pack(anchor='w', pady=(0, 6))
        self.entry = ttk.Entry(self.access, textvariable=self.password, show='•', width=1)
        self.entry.pack(fill='x')
        self.entry.bind('<Return>', lambda e: self.login())
        ttk.Checkbutton(self.access, text='Mostrar contraseña', variable=self.visible,
                        style='Login.TCheckbutton', command=self.toggle_password).pack(anchor='w', pady=(12, 8))
        self.error_label = ttk.Label(self.access, textvariable=self.error, style='error.TLabel')
        self.submit = ttk.Button(self.access, text='Entrar al consultorio', style='Primary.TButton', command=self.login)
        self.submit.pack(fill='x', pady=(12, 0))
        ttk.Label(self.access, text='Usa la contraseña de tu perfil.', style='Login.CardMuted.TLabel').pack(anchor='w', pady=(14, 0))
        self.access.bind('<Configure>', self.wrap_access)
        footer = ttk.Frame(self.outer)
        footer.grid(row=3, column=0, sticky='ew', pady=(26, 0))
        ttk.Label(footer, text='TresVizo Med · '+VERSION, style='Subtitle.TLabel').pack(side='left')
        ttk.Button(footer, text=app.identity.values['website_text']+' ↗', style='Link.TButton',
                   command=lambda: app.guard(app.identity.open_website)).pack(side='right')
        self.body.bind('<Configure>', self.layout, add='+')
        self.query.trace_add('write', self.filter_changed)
        self.filtered = list(users)
        self.render()
        self.select(users[0], focus=False)
        app.login_cards = self.cards

    def profile_details(self, user):
        pref = self.app.profiles.get(user['id'])
        return pref.get('specialty', '').strip() or ('Administración' if user['role'] == 'admin' else 'Médico')

    def layout(self, event):
        if event.widget is not self.body:
            return
        if event.width == getattr(self, '_layout_width', None):
            return
        self._layout_width = event.width
        width = min(event.width, int(1280*self.scale))
        self.outer.grid(sticky='ew', padx=max(0, (event.width-width)//2))
        available = max(240, width-64)
        wide = available >= int(1000*self.scale)
        self.content.columnconfigure(1, weight=0, minsize=int(340*self.scale) if wide else 0)
        self.profiles.grid(row=0, column=0, sticky='new', padx=(0, 28 if wide else 0))
        self.access.grid(row=0 if wide else 1, column=1 if wide else 0, sticky='new', pady=(0 if wide else 24, 0))
        self.clinic_label.configure(wraplength=max(200, available-120))

    def wrap_access(self, event):
        width = max(160, event.width-56)
        for label in (self.name_label, self.detail_label, self.error_label):
            label.configure(wraplength=width)

    def wrap_text(self, text, width):
        font = tkfont.Font(self, font=('Segoe UI Semibold', 11))
        lines, line = [], ''
        for char in text:
            if line and font.measure(line+char) > width:
                split = line.rfind(' ')
                if split > 0:
                    lines.append(line[:split])
                    line = line[split+1:]+char
                else:
                    lines.append(line)
                    line = char
            else:
                line += char
        return '\n'.join([*lines, line])

    def layout_cards(self, event=None):
        width = self.gallery.winfo_width()
        if event is not None and width == getattr(self, '_gallery_width', None):
            return
        self._gallery_width = width
        columns = 2 if width >= int(620*self.scale) else 1
        for column in range(2):
            self.gallery.columnconfigure(column, weight=1 if column < columns else 0, uniform='profiles' if column < columns else '')
        text_width = max(120, width//columns-int(112*self.scale))
        for index, (uid, button) in enumerate(self.cards.items()):
            button.grid(row=index//columns, column=index%columns, sticky='nsew', padx=(0, 12 if columns == 2 and index%2 == 0 else 0), pady=(0, 12))
            user = button.user
            title = self.wrap_text(user['name'], text_width)
            subtitle = self.wrap_text(self.profile_details(user)+' · @'+user['username'], text_width)
            marker = '✓ Seleccionado' if self.selected and self.selected['id'] == uid else 'Elegir perfil'
            text = title+'\n'+subtitle+'\n'+marker
            if button.cget('text') != text:
                button.configure(text=text)

    def render(self):
        for button in self.cards.values():
            button.destroy()
        self.cards.clear()
        self.empty.grid_remove()
        total = len(self.filtered)
        self.page = min(self.page, max(0, (total-1)//self.PAGE_SIZE))
        for user in self.filtered[self.page*self.PAGE_SIZE:(self.page+1)*self.PAGE_SIZE]:
            photo = self.app.profiles.image(user, int(56*self.scale))
            button = ttk.Button(self.gallery, image=photo, compound='left', width=1,
                                style='Login.Profile.TButton', command=lambda u=user: self.select(u))
            button.photo, button.user = photo, user
            self.cards[user['id']] = button
        if not total:
            self.empty.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.count.set(f'{total} perfil'+('es' if total != 1 else '')+(f' · Página {self.page+1} de {(total-1)//self.PAGE_SIZE+1}' if total > self.PAGE_SIZE else ''))
        for button, enabled in ((self.previous_button, self.page > 0), (self.next_button, (self.page+1)*self.PAGE_SIZE < total)):
            button.state(['!disabled'] if enabled else ['disabled'])
            if total > self.PAGE_SIZE:
                if not button.winfo_manager():
                    button.pack(side='right')
            else:
                button.pack_forget()
        self.mark_selected()
        self.layout_cards()

    def mark_selected(self):
        for uid, button in self.cards.items():
            button.configure(style='Selected.Login.Profile.TButton' if self.selected and self.selected['id'] == uid else 'Login.Profile.TButton')

    def select(self, user, focus=True):
        self.selected = user
        self.password.set('')
        self.visible.set(False)
        self.toggle_password()
        self.error.set('')
        self.error_label.pack_forget()
        self.entry.state(['!invalid', '!disabled'] if user else ['disabled'])
        self.submit.state(['!disabled'] if user else ['disabled'])
        self.name.set(user['name'] if user else 'Selecciona un perfil')
        self.detail.set(self.profile_details(user)+'\n@'+user['username'] if user else 'Elige al médico que iniciará sesión.')
        self.avatar.photo = self.app.profiles.image(user, int(64*self.scale)) if user else None
        self.avatar.configure(image=self.avatar.photo or '')
        self.mark_selected()
        self.layout_cards()
        if focus and user:
            self.reveal_access()

    def reveal_access(self):
        self.update_idletasks()
        height = max(1, self.body.winfo_height())
        bottom = self.submit.winfo_rooty()+self.submit.winfo_height()-self.canvas.winfo_rooty()
        if bottom > self.canvas.winfo_height() or self.entry.winfo_rooty() < self.canvas.winfo_rooty():
            y = self.access.winfo_rooty()-self.body.winfo_rooty()-16
            self.canvas.yview_moveto(max(0, y)/height)
        self.entry.focus_set()

    def toggle_password(self):
        self.entry.configure(show='' if self.visible.get() else '•')

    def filter_changed(self, *args):
        terms = normalized(self.query.get()).split()
        self.filtered = [u for u in self.users if all(term in normalized(u['name']+' '+u['username']+' '+self.profile_details(u)) for term in terms)]
        self.page = 0
        if self.selected and self.selected['id'] not in {u['id'] for u in self.filtered}:
            self.select(None, focus=False)
        self.render()

    def turn(self, delta):
        self.page = max(0, min((len(self.filtered)-1)//self.PAGE_SIZE, self.page+delta))
        self.render()

    def focus_result(self, event=None):
        if self.cards:
            next(iter(self.cards.values())).focus_set()
        return 'break'

    def choose_result(self, event=None):
        if len(self.filtered) == 1:
            self.select(self.filtered[0])
        else:
            self.focus_result()
        return 'break'

    def login(self):
        if not self.selected:
            return
        try:
            if not self.password.get():
                raise DataError('Escribe la contraseña de este perfil.')
            self.app.auth.login(self.selected['id'], self.password.get())
        except DataError as exc:
            self.error.set('⚠ '+str(exc))
            self.error_label.pack(fill='x', before=self.submit, pady=(6, 0))
            self.entry.state(['invalid'])
            self.reveal_access()
            return
        self.password.set('')
        self.app.shell()
