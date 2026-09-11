"""Iconos vectoriales Lucide incluidos localmente y adaptados a los tokens."""
from PIL import Image, ImageTk
from app.branding import ASSETS
from app.components import Tooltip
from app.themes import readable

ACTION_ICONS = {'Guardar borrador': 'save', 'Guardar paciente': 'save', 'Guardar y atender': 'stethoscope',
                'Atender paciente': 'stethoscope', 'Atender': 'stethoscope', 'Registrar paciente': 'plus',
                '+ Nuevo paciente': 'plus', '+ Añadir': 'plus', 'Editar': 'pencil',
                'Abrir expediente': 'folder-open', '+ Agregar archivos': 'file-up',
                'Ver': 'folder-open', 'Guardar perfil': 'save', 'Confirmar medición': 'activity'}

class Icons:
    def __init__(self,theme):
        self.theme,self.cache = theme,{}
    def photo(self,name,size=18,color=None):
        color = color or self.theme.tokens['text']
        key = (name,size,color)
        if key not in self.cache:
            with Image.open(ASSETS/'icons'/(name+'.png')) as source:
                alpha = source.convert('RGBA').getchannel('A').resize((size,size),Image.Resampling.LANCZOS)
            result = Image.new('RGBA',(size,size),color)
            result.putalpha(alpha)
            self.cache[key] = ImageTk.PhotoImage(result, master=self.theme.root)
        return self.cache[key]
    def bind(self,widget,name,size=18,token='text',show_text=False):
        widget.action_label = str(widget.cget('text'))
        widget.tooltip = Tooltip(widget, widget.action_label, self.theme)
        def update(tokens):
            style = str(widget.cget('style'))
            key = 'selection' if style == 'Active.Nav.TButton' else 'sidebar' if style == 'Nav.TButton' else 'button' if style == 'Primary.TButton' else 'secondary'
            pixels = int(size*getattr(self.theme.root, 'ui_scale', 1))
            is_link = style == 'Link.TButton'
            foreground = readable(tokens['primary'], tokens['background']) if is_link else tokens['on_'+key]
            widget.icon = self.photo(name,pixels,foreground)
            states = [widget.icon]
            for state, variant in [('disabled', 'disabled'), ('pressed', 'pressed'), ('active', 'hover')]:
                shade = (readable(tokens['muted'], tokens['background']) if state == 'disabled' else tokens[f'on_selection_{variant}']) if is_link else tokens[f'on_{key}_{variant}']
                states.extend((state, self.photo(name,pixels,shade)))
            # Las acciones principales muestran texto; los controles compactos conservan ayuda y etiqueta.
            widget.configure(image=tuple(states),compound='left' if show_text else 'none',width=0)
        widget.refresh_icon = lambda: update(self.theme.tokens)
        self.theme.subscribe(widget,update)
