"""Iconos vectoriales Lucide incluidos localmente y adaptados a los tokens."""
from PIL import Image, ImageTk
from app.branding import ASSETS

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
            self.cache[key] = ImageTk.PhotoImage(result)
        return self.cache[key]
    def bind(self,widget,name,size=18,token='text'):
        def update(tokens):
            widget.icon = self.photo(name,size,tokens[token])
            widget.configure(image=widget.icon,compound='left')
        self.theme.subscribe(widget,update)
