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
        s.configure('.', font=('Segoe UI', 11), foreground=t['text'], background=t['background'],
                    bordercolor=t['border'], lightcolor=t['border'], darkcolor=t['border'], troughcolor=t['secondary'],
                    focuscolor=t['focus'], selectbackground=t['selection'], selectforeground=t['on_selection'])
        for prefix, bg, fg in [('', 'background', 'text'), ('Card.', 'surface', 'text'),
                                ('Header.', 'header', 'on_header'), ('Nav.', 'sidebar', 'on_sidebar')]:
            s.configure(prefix+'TFrame', background=t[bg])
            s.configure(prefix+'TLabel', background=t[bg], foreground=t[fg])
        s.configure('Title.TLabel', font=('Segoe UI Semibold', 23), foreground=t['text'])
        s.configure('Section.TLabel', font=('Segoe UI Semibold', 15), foreground=t['text'])
        s.configure('TSeparator', background=t['separator'])
        s.configure('Subtitle.TLabel', foreground=t['muted'])
        s.configure('Consultation.Field.TLabel', font=('Segoe UI Semibold', 12), foreground=t['text'])
        s.configure('Consultation.Alert.TLabel', background=t['warning_bg'], foreground=t['warning_fg'], padding=(10, 5))
        s.configure('Login.Brand.TLabel', font=('Segoe UI Semibold', 22))
        s.configure('Login.Eyebrow.TLabel', font=('Segoe UI Semibold', 10), foreground=t['muted'])
        s.configure('Login.Panel.TFrame', background=t['surface'], bordercolor=t['border'], relief='solid', borderwidth=1)
        s.configure('Login.CardTitle.TLabel', background=t['surface'], foreground=readable(t['text'], t['surface']), font=('Segoe UI Semibold', 17))
        s.configure('Login.CardMuted.TLabel', background=t['surface'], foreground=readable(t['muted'], t['surface']))
        s.configure('Login.CardEyebrow.TLabel', background=t['surface'], foreground=readable(t['primary'], t['surface']), font=('Segoe UI Semibold', 10))
        for style, selected in [('Login.Profile.TButton', False), ('Selected.Login.Profile.TButton', True)]:
            s.configure(style, background=t['selection'] if selected else t['surface'],
                        foreground=t['on_selection'] if selected else readable(t['text'], t['surface']),
                        bordercolor=t['focus'] if selected else t['border'], borderwidth=2, relief='solid',
                        padding=(16, 18), font=('Segoe UI Semibold', 11), anchor='w',
                        focuscolor=t['focus'], focusthickness=2)
            s.map(style, background=[('disabled', t['secondary_disabled']), ('pressed', t['selection_pressed']), ('active', t['selection_hover'])],
                  foreground=[('disabled', t['on_secondary_disabled']), ('pressed', t['on_selection_pressed']), ('active', t['on_selection_hover'])],
                  bordercolor=[('focus', t['focus']), ('active', t['focus'])])
        s.configure('Metric.TLabel', font=('Segoe UI Semibold', 22), background=t['surface'], foreground=t['text'])
        s.configure('TLabelframe', background=t['background'], bordercolor=t['border'], padding=12)
        s.configure('TLabelframe.Label', foreground=t['text'], background=t['background'])
        for style, key in [('TButton', 'secondary'), ('Primary.TButton', 'button'), ('Nav.TButton', 'sidebar')]:
            s.configure(style, background=t[key], foreground=t['on_'+key], padding=(12, 8), borderwidth=0,
                        focuscolor=t['focus'], focusthickness=2, anchor='center')
            s.map(style, background=[('disabled', t[key+'_disabled']), ('pressed', t[key+'_pressed']), ('active', t[key+'_hover'])],
                  foreground=[('disabled', t['on_'+key+'_disabled']), ('pressed', t['on_'+key+'_pressed']), ('active', t['on_'+key+'_hover'])],
                  bordercolor=[('focus', t['focus'])])
        s.configure('Active.Nav.TButton', background=t['selection'], foreground=t['on_selection'], font=('Segoe UI Semibold', 11), anchor='center', padding=(12, 8), borderwidth=0)
        s.map('Active.Nav.TButton', background=[('disabled', t['selection_disabled']), ('pressed', t['selection_pressed']), ('active', t['selection_hover'])],
              foreground=[('disabled', t['on_selection_disabled']), ('pressed', t['on_selection_pressed']), ('active', t['on_selection_hover'])])
        s.configure('Disclosure.Link.TButton', anchor='w', font=('Segoe UI Semibold', 12), padding=(8, 6))
        s.configure('Link.TButton', background=t['background'], foreground=readable(t['primary'], t['background']), borderwidth=0, padding=(4, 6))
        s.map('Link.TButton', background=[('disabled', t['background']), ('pressed', t['selection_pressed']), ('active', t['selection_hover'])],
              foreground=[('disabled', readable(t['muted'], t['background'])), ('pressed', t['on_selection_pressed']), ('active', t['on_selection_hover'])])
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
                    rowheight=int(38*getattr(self.root, 'ui_scale', 1)), bordercolor=t['separator'], borderwidth=0)
        s.map('Treeview', background=[('selected', t['selection'])], foreground=[('selected', t['on_selection'])])
        s.configure('Treeview.Heading', background=t['surface'], foreground=t['muted'], padding=8, borderwidth=0, font=('Segoe UI Semibold', 10))
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
        s.configure('Login.TCheckbutton', background=t['surface'], foreground=readable(t['text'], t['surface']))
        s.map('Login.TCheckbutton', background=[('active', t['surface'])])
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
        if isinstance(widget, ttk.Button) and hasattr(self.root, 'icons') and not hasattr(widget, 'icon'):
            from app.icons import ACTION_ICONS
            name = ACTION_ICONS.get(str(widget.cget('text')))
            if name:
                self.root.icons.bind(widget, name, token='on_button' if widget.cget('style') == 'Primary.TButton' else 'text', show_text=True)
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            widget.configure(background=t['background'])
            if not getattr(widget, 'brand_icon_set', False):
                from app.branding import set_window_icon
                set_window_icon(widget)
        elif isinstance(widget, tk.Text):
            widget.configure(background=t['surface'], foreground=t['text'], insertbackground=t['text'],
                             selectbackground=t['selection'], selectforeground=t['on_selection'],
                             highlightbackground=t['border'], highlightcolor=t['focus'])
        elif isinstance(widget, tk.Canvas) and not getattr(widget, 'own_palette', False):
            widget.configure(background=t['background' if getattr(widget, 'scroll_surface', False) else 'surface'], highlightbackground=t['border'])
        elif isinstance(widget, tk.Menu):
            widget.configure(background=t['surface'], foreground=t['text'], activebackground=t['selection'],
                             activeforeground=t['on_selection'], disabledforeground=readable(t['muted'], t['surface']))
        for child in widget.winfo_children():
            self._walk(child)
