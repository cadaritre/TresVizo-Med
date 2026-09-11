"""Actualización de estilos en el mismo árbol de widgets, sin destruir ni enfocar."""
import tkinter as tk
from tkinter import ttk
from app.themes import derived, readable


class ThemeManager:
    def __init__(self, root):
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use('clam')
        self.tokens = None
        self.callbacks = []

    def subscribe(self, widget, callback):
        self.callbacks.append((widget, callback))
        if self.tokens:
            callback(self.tokens)

    def apply(self, palette):
        t = self.tokens = derived(palette)
        s = self.style
        s.configure('.', font=('Segoe UI', 10), foreground=t['text'], background=t['background'],
                    bordercolor=t['border'], lightcolor=t['border'], darkcolor=t['border'], troughcolor=t['secondary'],
                    focuscolor=t['focus'], selectbackground=t['selection'], selectforeground=t['on_selection'])
        for prefix, bg, fg in [('', 'background', 'text'), ('Card.', 'surface', 'text'),
                                ('Header.', 'header', 'on_header'), ('Nav.', 'sidebar', 'on_sidebar')]:
            s.configure(prefix+'TFrame', background=t[bg])
            s.configure(prefix+'TLabel', background=t[bg], foreground=t[fg])
        s.configure('Title.TLabel', font=('Segoe UI Semibold', 23), foreground=t['primary'])
        s.configure('Subtitle.TLabel', foreground=t['muted'])
        s.configure('Metric.TLabel', font=('Segoe UI Semibold', 28), background=t['surface'], foreground=t['primary'])
        s.configure('TLabelframe', background=t['background'], bordercolor=t['border'], padding=12)
        s.configure('TLabelframe.Label', foreground=t['text'], background=t['background'])
        for style, key in [('TButton', 'secondary'), ('Primary.TButton', 'button'), ('Nav.TButton', 'sidebar')]:
            s.configure(style, background=t[key], foreground=t['on_'+key], padding=(14, 9), borderwidth=1,
                        focuscolor=t['focus'], focusthickness=2, anchor='w' if key == 'sidebar' else 'center')
            s.map(style, background=[('disabled', t[key+'_disabled']), ('pressed', t[key+'_pressed']), ('active', t[key+'_hover'])],
                  foreground=[('disabled', t['on_'+key+'_disabled']), ('pressed', t['on_'+key+'_pressed']), ('active', t['on_'+key+'_hover'])],
                  bordercolor=[('focus', t['focus'])])
        for style in ('TEntry', 'TCombobox', 'TSpinbox'):
            s.configure(style, fieldbackground=t['surface'], foreground=t['text'], insertcolor=t['text'], padding=7,
                        selectbackground=t['selection'], selectforeground=t['on_selection'], bordercolor=t['border'], arrowsize=16)
            s.map(style, fieldbackground=[('disabled', t['secondary_disabled']), ('readonly', t['surface'])],
                  foreground=[('disabled', t['on_secondary_disabled']), ('readonly', t['text'])],
                  bordercolor=[('invalid', t['error_fg']), ('focus', t['focus'])],
                  lightcolor=[('focus', t['focus'])], darkcolor=[('focus', t['focus'])])
        s.map('TCombobox', selectbackground=[('!focus', t['surface']), ('focus', t['selection'])],
              selectforeground=[('!focus', t['text']), ('focus', t['on_selection'])])
        s.configure('Treeview', background=t['surface'], fieldbackground=t['surface'], foreground=t['text'],
                    rowheight=32, bordercolor=t['border'])
        s.map('Treeview', background=[('selected', t['selection'])], foreground=[('selected', t['on_selection'])])
        s.configure('Treeview.Heading', background=t['secondary'], foreground=t['on_secondary'], padding=8)
        s.map('Treeview.Heading', background=[('active', t['secondary_hover'])], foreground=[('active', t['on_secondary_hover'])])
        s.configure('TNotebook', background=t['background'])
        s.configure('TNotebook.Tab', background=t['secondary'], foreground=t['on_secondary'], padding=(14, 8))
        s.map('TNotebook.Tab', background=[('selected', t['button']), ('active', t['secondary_hover'])],
              foreground=[('selected', t['on_button']), ('active', t['on_secondary_hover'])])
        for style in ('TCheckbutton', 'TRadiobutton'):
            s.configure(style, background=t['background'], foreground=t['text'], indicatorbackground=t['surface'],
                        indicatorforeground=t['text'], focuscolor=t['focus'])
            s.map(style, background=[('active', t['background'])], foreground=[('disabled', readable(t['muted'], t['background']))],
                  indicatorbackground=[('selected', t['selection'])])
        for kind in ('error', 'warning', 'success'):
            s.configure(kind+'.TLabel', background=t[kind+'_bg'], foreground=t[kind+'_fg'], padding=10)
        self.root.option_add('*TCombobox*Listbox.background', t['surface'])
        self.root.option_add('*TCombobox*Listbox.foreground', t['text'])
        self.root.option_add('*TCombobox*Listbox.selectBackground', t['selection'])
        self.root.option_add('*TCombobox*Listbox.selectForeground', t['on_selection'])
        self._walk(self.root)
        self.callbacks = [(w, fn) for w, fn in self.callbacks if w.winfo_exists()]
        for _, callback in self.callbacks:
            callback(t)

    def _walk(self, widget):
        t = self.tokens
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            widget.configure(background=t['background'])
        elif isinstance(widget, tk.Text):
            widget.configure(background=t['surface'], foreground=t['text'], insertbackground=t['text'],
                             selectbackground=t['selection'], selectforeground=t['on_selection'],
                             highlightbackground=t['border'], highlightcolor=t['focus'])
        elif isinstance(widget, tk.Canvas) and not getattr(widget, 'own_palette', False):
            widget.configure(background=t['surface'], highlightbackground=t['border'])
        elif isinstance(widget, tk.Menu):
            widget.configure(background=t['surface'], foreground=t['text'], activebackground=t['selection'],
                             activeforeground=t['on_selection'], disabledforeground=readable(t['muted'], t['surface']))
        for child in widget.winfo_children():
            self._walk(child)
