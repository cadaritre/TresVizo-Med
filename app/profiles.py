"""Preferencias e imágenes locales de perfiles autenticados."""
from pathlib import Path
from io import BytesIO
import uuid
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageDraw, ImageFont, ImageTk
from app.branding import ASSETS
from app.storage import DataError
from app.components import ScrollFrame, Tooltip
from app.widgets import Form

AVATARS = ['zorro', 'gato', 'oso', 'buho', 'conejo', 'panda', 'koala', 'tortuga', 'montana', 'sol', 'luna', 'arbol', 'flor', 'hoja', 'cometa', 'pez']

class Profiles:
    def __init__(self, store, auth, master=None):
        self.store, self.auth = store, auth
        self.master = master
        self.cache = {}
        self.bindings = []
    def get(self, uid):
        return self.store.read(f'config/profiles/{uuid.UUID(uid)}.json', {'avatar': AVATARS[uuid.UUID(uid).int % len(AVATARS)], 'reduce_motion': False})
    def save(self, uid, values, photo=None):
        actor = self.auth.require()
        if uid != actor['id']:
            self.auth.require('admin')
        data = {**self.get(uid), **values}
        if photo is not None:
            relative = f'avatars/{uuid.uuid4()}.png'
            target = self.store.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            photo.resize((256,256), Image.Resampling.LANCZOS).convert('RGB').save(target)
            data.update(avatar='photo', photo=relative)
        if data['avatar'] not in (*AVATARS, 'photo', 'initials'):
            raise DataError('Avatar desconocido.')
        self.store.write(f'config/profiles/{uid}.json', data)
        self.cache = {key: image for key, image in self.cache.items() if key[0] != uid}
        self.bindings = [(widget, user, size) for widget, user, size in self.bindings if widget.winfo_exists()]
        for widget, user, size in self.bindings:
            if user['id'] == uid:
                widget.profile_photo = self.image(user, size)
                widget.configure(image=widget.profile_photo)
        self.auth.audit('actualizar_perfil', uid)

    def bind(self, widget, user, size=64):
        self.bindings = [(w, u, s) for w, u, s in self.bindings if w.winfo_exists() and w is not widget]
        self.bindings.append((widget, dict(user), size))
        # Tk conserva el nombre de la imagen, pero no la referencia Python.
        widget.profile_photo = self.image(user, size)
        widget.configure(image=widget.profile_photo)
    def image(self, user, size=64):
        pref = self.get(user['id'])
        key = (user['id'], size, pref.get('avatar'), pref.get('photo'))
        if key in self.cache:
            return self.cache[key]
        try:
            avatar = pref.get('avatar')
            path = self.store.path(pref['photo']) if avatar == 'photo' else ASSETS/'avatars'/(avatar+'.png')
            with Image.open(path) as source:
                result = source.convert('RGB').resize((size,size), Image.Resampling.LANCZOS)
        except (KeyError, OSError, TypeError, ValueError):
            result = Image.new('RGB', (size,size), '#E8F1FC')
            draw = ImageDraw.Draw(result)
            try:
                font = ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf', int(size*.35))
            except OSError:
                font = ImageFont.load_default()
            initials = ''.join(n[0] for n in user['name'].split()[:2]).upper()
            draw.text((size/2,size/2), initials, anchor='mm', font=font, fill='#244361')
        mask = Image.new('L', (size,size))
        ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1), fill=255)
        result.putalpha(mask)
        self.cache[key] = ImageTk.PhotoImage(result, master=self.master)
        return self.cache[key]

class ProfileEditor(ScrollFrame):
    def __init__(self, parent, app, uid=None):
        super().__init__(parent)
        self.app = app
        self.user = next(u for u in app.auth.users() if u['id'] == (uid or app.auth.current['id']))
        self.pref = app.profiles.get(self.user['id'])
        self.selected = self.pref.get('avatar', 'initials')
        self.photo = None
        ttk.Label(self.body, text=('Mi perfil · ' if self.user['id'] == app.auth.current['id'] else 'Perfil del doctor · ')+self.user['name'], style='Section.TLabel').pack(anchor='w', pady=10)
        self.preview = ttk.Label(self.body, image=app.profiles.image(self.user, 96))
        app.profiles.bind(self.preview, self.user, 96)
        self.preview.pack(anchor='w', pady=8)
        self.photos = []
        self.avatar_buttons = {}
        gallery = ttk.Frame(self.body)
        gallery.pack(fill='x')
        for i, name in enumerate(AVATARS):
            with Image.open(ASSETS/'avatars'/(name+'.png')) as source:
                image = ImageTk.PhotoImage(source.resize((64,64), Image.Resampling.LANCZOS),master=self)
            self.photos.append(image)
            button = ttk.Button(gallery, text=name.capitalize(), image=image, compound='none', width=0,
                                command=lambda n=name, p=image: self.select(n,p))
            button.grid(row=i//4, column=i%4, padx=6, pady=6, sticky='ew')
            button.tooltip = Tooltip(button, name.capitalize(), app.theme)
            self.avatar_buttons[name] = button
        self.mark_selected()
        for i in range(4):
            gallery.columnconfigure(i, weight=1)
        actions = ttk.Frame(self.body)
        actions.pack(fill='x', pady=10)
        ttk.Button(actions, text='Elegir foto…', command=self.choose).pack(side='left')
        ttk.Button(actions, text='Usar iniciales', command=lambda: self.select('initials', None)).pack(side='left', padx=8)
        self.notice = ttk.Label(self.body, style='Subtitle.TLabel', wraplength=620)
        self.notice.pack(fill='x', pady=8)
        self.reduce = tk.BooleanVar(value=self.pref.get('reduce_motion', False))
        ttk.Checkbutton(self.body, text='Reducir movimiento', variable=self.reduce).pack(anchor='w', pady=8)
        self.professional = Form(self.body, [('specialty', 'Especialidad', None), ('license', 'Registro profesional', None),
                                           ('professional_phone', 'Teléfono profesional', None)], self.pref, theme=app.theme)
        self.professional.pack(fill='x', pady=8)
        footer = ttk.Frame(self.body)
        footer.pack(fill='x', pady=10)
        ttk.Button(footer, text='Guardar perfil', style='Primary.TButton', command=lambda: app.guard(self.save)).pack(side='left')
        ttk.Button(footer, text='Cancelar cambios', command=self.reset).pack(side='left', padx=8)

    def reset(self):
        self.pref = self.app.profiles.get(self.user['id'])
        self.selected, self.photo = self.pref.get('avatar', 'initials'), None
        self.app.profiles.bind(self.preview, self.user, 96)
        self.preview.configure(text='')
        self.notice.configure(text='')
        self.reduce.set(self.pref.get('reduce_motion', False))
        self.professional.load(self.pref)
        self.mark_selected()


    def mark_selected(self):
        for name, button in self.avatar_buttons.items():
            button.configure(style='Active.Nav.TButton' if name == self.selected else 'TButton')

    def select(self, name, image):
        self.selected, self.photo = name, None
        self.preview.configure(image=image or '', text='Iniciales' if name == 'initials' else '')
        self.mark_selected()
        self.notice.configure(text='Vista previa · pulsa Guardar perfil para aplicar este avatar.')

    def choose(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('Foto PNG o JPEG', '*.png *.jpg *.jpeg')])
        if not path:
            return
        def action():
            if Path(path).stat().st_size > 10*1024*1024:
                raise DataError('La foto debe ser menor de 10 MiB.')
            with Image.open(path) as source:
                if source.format not in ('PNG', 'JPEG') or source.width*source.height > 12_000_000:
                    raise DataError('Elige PNG o JPEG de hasta 12 megapíxeles.')
                from PIL import ImageOps
                original = ImageOps.exif_transpose(source).convert('RGB')
            PhotoCrop(self.app, original, self.use_photo)
        self.app.guard(action)

    def use_photo(self, image):
        try:
            self.app.profiles.save(self.user['id'], {'avatar': 'photo'}, image)
        except (ValueError, OSError) as exc:
            self.notice.configure(text=str(exc), style='error.TLabel')
            return False
        self.photo, self.selected = None, 'photo'
        self.pref = self.app.profiles.get(self.user['id'])
        self.app.profiles.bind(self.preview, self.user, 96)
        self.preview.configure(text='')
        self.notice.configure(text='Foto guardada y aplicada a tu perfil.', style='Subtitle.TLabel')
        self.app.status.set('Foto de perfil actualizada.')
        self.mark_selected()
        return True

    def save(self):
        self.app.profiles.save(self.user['id'], {'avatar': self.selected, 'reduce_motion': self.reduce.get(), **self.professional.values()}, self.photo)
        self.app.status.set('Perfil guardado.')
        self.app.profiles.bind(self.preview, self.user, 96)
        self.preview.configure(text='')
        self.notice.configure(text='Perfil guardado.', style='Subtitle.TLabel')
        self.pref = self.app.profiles.get(self.user['id'])
        self.photo = None

class PhotoCrop(tk.Toplevel):
    def __init__(self, app, original, callback):
        super().__init__(app)
        self.title('Ajustar foto')
        self.original, self.callback = original, callback
        self.geometry('430x490')
        self.transient(app)
        from app.branding import set_window_icon
        set_window_icon(self)
        self.bind('<Escape>', lambda event: (self.destroy(), 'break')[1])
        self.offset, self.drag = [0,0], None
        self.zoom = tk.DoubleVar(value=1)
        ttk.Label(self, text='Arrastra para encuadrar · ajusta el zoom', padding=12).pack()
        self.canvas = tk.Canvas(self, width=300, height=300, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>', lambda e: setattr(self, 'drag', (e.x,e.y)))
        self.canvas.bind('<B1-Motion>', self.pan)
        ttk.Scale(self, from_=1, to=3, variable=self.zoom, command=lambda v: self.render()).pack(fill='x', padx=30, pady=12)
        actions = ttk.Frame(self)
        actions.pack()
        ttk.Button(actions, text='Guardar foto de perfil', command=self.accept).pack(side='left')
        ttk.Button(actions, text='Restablecer', command=self.reset).pack(side='left', padx=5)
        ttk.Button(actions, text='Cancelar', command=self.destroy).pack(side='left')
        app.theme._walk(self)
        self.render()
    def pan(self, event):
        self.offset[0] += event.x-self.drag[0]
        self.offset[1] += event.y-self.drag[1]
        self.drag = (event.x,event.y)
        self.render()
    def reset(self):
        self.offset = [0,0]
        self.zoom.set(1)
        self.render()
    def crop(self):
        factor = 300/min(self.original.size)*self.zoom.get()
        w,h = self.original.size
        sx, sy = min((w*factor-300)/2, max(-(w*factor-300)/2, self.offset[0])), min((h*factor-300)/2, max(-(h*factor-300)/2, self.offset[1]))
        x,y = (w-300/factor)/2-sx/factor, (h-300/factor)/2-sy/factor
        return self.original.crop((x,y,x+300/factor,y+300/factor)).resize((300,300), Image.Resampling.LANCZOS)
    def render(self):
        im = self.crop().convert('RGBA')
        mask = Image.new('L', (300,300))
        ImageDraw.Draw(mask).ellipse((0,0,299,299), fill=255)
        im.putalpha(mask)
        self.image = ImageTk.PhotoImage(im,master=self)
        self.canvas.delete('all')
        self.canvas.create_image(0,0, image=self.image, anchor='nw')
    def accept(self):
        if self.callback(self.crop()) is not False:
            self.destroy()
