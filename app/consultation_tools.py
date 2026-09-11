"""Capturas contextuales: copia temporal, validación y publicación explícita."""
from copy import deepcopy
from datetime import date, datetime
import calendar
import tkinter as tk
from tkinter import ttk

from app.components import ScrollFrame
from app.widgets import Form, Collapsible
from app.clinical_models import (VITALS, display_date, local_date, normalize_measurement,
                                 validate_vitals, validate_medications, medication_text)
from app.consultation_state import attention_time
from app.storage import DataError


def action(parent, app, text, command, icon=None, primary=False):
    button = ttk.Button(parent, text=text, command=command, style='Primary.TButton' if primary else 'TButton')
    if icon:
        app.icons.bind(button, icon, show_text=True)
    else:
        button.icon = None  # Esta acción clínica conserva su etiqueta.
    return button


def fit_window(window, app, width=700, height=700):
    """Centrar en el área de trabajo del monitor, con margen para Windows."""
    left, top, right, bottom = 0, 0, app.winfo_screenwidth(), app.winfo_screenheight()-60
    try:
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        user32 = ctypes.WinDLL('user32')
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        if user32.GetMonitorInfoW(user32.MonitorFromWindow(int(app.frame(), 16), 2), ctypes.byref(info)):
            left, top, right, bottom = info.work.left, info.work.top, info.work.right, info.work.bottom
    except (AttributeError, OSError):
        pass
    scale = getattr(app, 'ui_scale', 1)
    width, height = min(int(width*scale), right-left-24), min(int(height*scale), bottom-top-24)
    x = max(left+12, min(right-width-12, app.winfo_rootx()+(app.winfo_width()-width)//2))
    y = max(top+12, min(bottom-height-12, app.winfo_rooty()+(app.winfo_height()-height)//2))
    window.geometry(f'{width}x{height}{x:+d}{y:+d}')
    window.minsize(min(int(430*scale), width), min(int(350*scale), height))


class InlineDateField(ttk.Frame):
    """Calendario dentro de la captura, sin abrir otro diálogo modal."""
    def __init__(self, parent, theme, value=''):
        super().__init__(parent)
        self.theme = theme
        self.var = tk.StringVar(value=display_date(value) if value else '')
        row = ttk.Frame(self)
        row.pack(fill='x')
        self.entry = ttk.Entry(row, textvariable=self.var, width=12)
        self.entry.pack(side='left', fill='x', expand=True)
        self.button = ttk.Button(row, text='Calendario', command=self.open, width=10)
        self.button.pack(side='left', padx=(4, 0))
        self.panel = None

    def get(self):
        return local_date(self.var.get())

    def open(self):
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
            return
        try:
            selected = date.fromisoformat(self.get())
        except ValueError:
            selected = date.today()
        self.panel = ttk.Frame(self, padding=(0, 6))
        self.panel.pack(fill='x')
        controls = ttk.Frame(self.panel)
        controls.pack(fill='x')
        month, year = tk.StringVar(value=str(selected.month)), tk.StringVar(value=str(selected.year))
        months = ttk.Combobox(controls, textvariable=month, values=list(range(1, 13)), state='readonly', width=3)
        months.pack(side='left')
        years = ttk.Spinbox(controls, textvariable=year, from_=1800, to=2200, width=6)
        years.pack(side='left', padx=4)
        grid = ttk.Frame(self.panel)
        grid.pack(fill='x')
        def render(event=None):
            try:
                y, m = int(year.get()), int(month.get())
                days = calendar.monthcalendar(y, m)
                if not 1800 <= y <= 2200:
                    return
            except (ValueError, calendar.IllegalMonthError):
                return
            for child in grid.winfo_children():
                child.destroy()
            for c, label in enumerate(('L', 'M', 'M', 'J', 'V', 'S', 'D')):
                ttk.Label(grid, text=label).grid(row=0, column=c)
            for r, week in enumerate(days, 1):
                for c, day in enumerate(week):
                    if day:
                        def choose(d=day):
                            self.var.set(date(y, m, d).strftime('%d/%m/%Y'))
                            self.open()
                            self.entry.focus_set()
                        ttk.Button(grid, text=str(day), width=2, style='Link.TButton', command=choose).grid(row=r, column=c)
        months.bind('<<ComboboxSelected>>', render)
        years.bind('<Return>', lambda e: (render(), 'break')[1])
        ttk.Button(controls, text='Ir', width=3, command=render).pack(side='left')
        render()
        self.theme._walk(self.panel)


class FieldError(DataError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


class CaptureForm(Form):
    def __init__(self, parent, specs, data, changed, theme):
        super().__init__(parent, specs, data, changed, theme, date_type=InlineDateField)
        self.field_errors = {}

    def error(self, key, message):
        if key not in self.inputs:
            return
        widget = self.inputs[key]
        field = widget.entry if isinstance(widget, InlineDateField) else widget
        if hasattr(field, 'state'):
            field.state(['invalid'])
        label = self.field_errors.get(key)
        if label is None:
            label = self.field_errors[key] = ttk.Label(widget.master, style='error.TLabel', wraplength=290)
        label.configure(text=message)
        label.pack(fill='x', pady=(4, 0))
        field.focus_set()

    def clear_errors(self):
        for label in self.field_errors.values():
            label.pack_forget()
        for widget in self.inputs.values():
            widget = widget.entry if isinstance(widget, InlineDateField) else widget
            if hasattr(widget, 'state'):
                widget.state(['!invalid'])


class CaptureWindow(tk.Toplevel):
    def __init__(self, owner, kind, title, identifier=None, width=700, height=690):
        super().__init__(owner.app)
        self.withdraw()
        self.owner, self.app, self.kind = owner, owner.app, kind
        self.request_identifier = identifier
        self.identifier, self.initial, self.recovered = (kind, {}, False) if kind in ('documents', 'history', 'review', 'reuse') else owner.model.initial(kind, identifier)
        self.loading = True
        self.close_requested = False
        self.edit_focus = None
        self.title(title)
        self.transient(self.app)
        current_focus = owner.focus_get()
        last_text = getattr(owner, 'last_text', None)
        self.return_focus = (current_focus if isinstance(current_focus, tk.Text) and str(current_focus).startswith(str(owner)+'.')
                             else last_text if last_text and last_text.winfo_exists() and last_text.winfo_ismapped()
                             else current_focus)
        self.return_scroll = owner.scroll.canvas.canvasy(0) if hasattr(owner, 'scroll') else None
        self.return_anchor = (self.return_focus.winfo_rooty()-owner.scroll.body.winfo_rooty()) if self.return_scroll is not None and self.return_focus else None
        self.app.active_capture = self
        header = ttk.Frame(self, padding=(16, 10))
        header.pack(fill='x')
        ttk.Label(header, text=title, style='Section.TLabel').pack(anchor='w')
        patient = ttk.Label(header, text=owner.patient['name']+' · '+owner.patient['file_number'], style='Subtitle.TLabel', wraplength=620)
        patient.pack(fill='x', pady=(3, 0))
        header.bind('<Configure>', lambda e: patient.configure(wraplength=max(200, e.width-32)))
        footer = self.footer = ttk.Frame(self, padding=12)
        footer.pack(side='bottom', fill='x')
        self.cancel_button = action(footer, self.app, 'Cancelar', self.cancel)
        self.cancel_button.pack(side='left')
        self.apply_button = action(footer, self.app, 'Aplicar a la consulta', self.apply, primary=True)
        self.apply_button.pack(side='right')
        self.error = ttk.Label(self, style='error.TLabel', wraplength=600)
        self.resolution = ttk.Frame(self, padding=10)
        self.resolution_label = ttk.Label(self.resolution, text='Para cerrar, conserva la captura pendiente o descártala. También puedes seguir editando.', wraplength=560)
        self.resolution_label.pack(fill='x')
        choices = ttk.Frame(self.resolution)
        choices.pack(fill='x', pady=6)
        self.discard_button = action(choices, self.app, 'Descartar captura', self.discard)
        self.continue_button = action(choices, self.app, 'Seguir editando', self.continue_editing)
        self.defer_button = action(choices, self.app, 'Conservar pendiente y volver', self.defer, primary=True)
        def layout_choices(event=None):
            buttons = (self.defer_button, self.continue_button, self.discard_button)
            columns = 3 if sum(button.winfo_reqwidth()+12 for button in buttons) <= choices.winfo_width() else 1
            self.resolution_label.configure(wraplength=max(180, self.winfo_width()-32))
            for index in range(3):
                choices.columnconfigure(index, weight=1 if index < columns else 0)
            for index, button in enumerate(buttons):
                button.grid(row=index//columns, column=index%columns, sticky='ew', padx=3, pady=3)
        choices.bind('<Configure>', layout_choices)
        layout_choices()
        self.scroll = ScrollFrame(self)
        self.scroll.canvas.own_palette = True
        self.app.theme.subscribe(self.scroll.canvas, lambda tokens: self.scroll.canvas.configure(background=tokens['background']))
        self.scroll.pack(fill='both', expand=True, padx=16)
        self.body = self.scroll.body
        self.forms = []
        self.build()
        self.baseline = deepcopy(self.raw())
        self.loading = False
        self.protocol('WM_DELETE_WINDOW', self.request_close)
        self.bind('<Escape>', lambda e: (self.cancel(), 'break')[1])
        self.bind('<Control-s>', lambda e: (self.save_local(), 'break')[1])
        self.bind('<Destroy>', self.destroyed, add='+')
        self.app.theme._walk(self)
        fit_window(self, self.app, width, height)
        self.deiconify()
        self.grab_set()
        if self.forms:
            field = next(iter(self.forms[0].inputs.values()))
            (field.entry if isinstance(field, InlineDateField) else field).focus_set()

    def build(self):
        raise NotImplementedError

    def save_local(self):
        if hasattr(self, 'persist_pending'):
            self.persist_pending()
        if hasattr(self.owner, 'save_feedback'):
            return self.owner.save_feedback()
        return True

    def add_form(self, specs, initial=None, parent=None):
        form = CaptureForm(parent or self.body, specs, self.initial if initial is None else initial, self.changed, self.app.theme)
        form.pack(fill='x', pady=(4, 0))
        self.forms.append(form)
        return form

    def raw(self):
        values = deepcopy(self.initial)
        for form in self.forms:
            values.update(form.values(raw=True))
        return values

    def changed(self):
        if self.loading:
            return
        raw = self.raw()
        if self.recovered or raw != self.baseline:
            self.owner.model.remember(self.kind, self.identifier, raw)
        else:
            self.owner.model.discard(self.kind, self.identifier)
        self.owner.touch()

    def validate(self):
        return self.raw()

    def apply(self):
        for form in self.forms:
            form.clear_errors()
        try:
            values = self.validate()
            self.owner.model.apply(self.kind, self.identifier, values)
        except ValueError as exc:
            self.error.configure(text=str(exc))
            self.error.pack(side='bottom', fill='x', padx=12, pady=4, before=self.footer)
            if isinstance(exc, FieldError):
                for form in self.forms:
                    if exc.field in form.inputs:
                        if form is getattr(self, 'extra', None) and not self.more.opened:
                            self.more.toggle()
                        form.error(exc.field, str(exc))
                        self.update_idletasks()
                        self.scroll.canvas.yview_moveto(max(0, (form.inputs[exc.field].winfo_rooty()-self.body.winfo_rooty())/max(1, self.body.winfo_height())-.08))
            return False
        self.owner.applied()
        self.close()
        return True

    def dismiss_dropdowns(self):
        """Las listas de ttk se crean en Tcl y no aparecen en children de Python."""
        focused = None
        pending = list(self.children.values())
        while pending:
            widget = pending.pop()
            pending.extend(widget.children.values())
            if isinstance(widget, ttk.Combobox):
                popdown = widget._w+'.popdown'
                if self.tk.call('winfo', 'exists', popdown) and self.tk.call('winfo', 'ismapped', popdown):
                    self.tk.call('ttk::combobox::Unpost', widget._w)
                    focused = widget
        return focused

    def request_close(self):
        self.close_requested = True
        self.cancel()

    def show_resolution(self):
        dropdown = self.dismiss_dropdowns()
        if not self.resolution.winfo_manager():
            try:
                self.edit_focus = dropdown or self.focus_get()
            except KeyError:
                self.edit_focus = None
        self.resolution.pack(side='bottom', fill='x', before=self.footer)
        self.update_idletasks()
        if not self.app.locked:
            self.grab_set()
            self.defer_button.focus_set()

    def continue_editing(self):
        self.close_requested = False
        self.resolution.pack_forget()
        if self.edit_focus and self.edit_focus.winfo_exists() and not self.app.locked:
            self.edit_focus.focus_set()

    def cancel(self):
        if self.recovered or self.raw() != self.baseline:
            self.changed()
            self.show_resolution()
        else:
            self.close()

    def discard(self):
        self.owner.model.discard(self.kind, self.identifier)
        self.owner.applied()
        self.close()

    def defer(self):
        self.changed()
        self.owner.refresh_pending()
        self.close()

    def close(self):
        if not self.winfo_exists():
            return
        self.dismiss_dropdowns()
        # No convertir el grab de una lista Tcl en un widget Python (KeyError: popdown).
        grabbed = str(self.tk.call('grab', 'current', self._w))
        if grabbed == self._w or grabbed.startswith(self._w+'.'):
            self.tk.call('grab', 'release', grabbed)
        self.destroy()
        if self.return_scroll is not None and self.owner.winfo_exists():
            self.owner.update_idletasks()
            offset = self.return_scroll
            if self.return_anchor is not None and self.return_focus.winfo_exists():
                offset += self.return_focus.winfo_rooty()-self.owner.scroll.body.winfo_rooty()-self.return_anchor
            self.owner.scroll.canvas.yview_moveto(max(0, offset/max(1, self.owner.scroll.body.winfo_height())))
        if self.return_focus and self.return_focus.winfo_exists() and not self.app.locked:
            self.return_focus.focus_set()

    def destroyed(self, event):
        if event.widget is self:
            if getattr(self, 'persist_timer', None):
                self.after_cancel(self.persist_timer)
                self.persist_timer = None
            if getattr(self.app, 'active_capture', None) is self:
                self.app.active_capture = None


class DetailCapture(CaptureWindow):
    def build(self):
        specs = {
            'header': [('date', 'Fecha de atención', 'date'), ('time', 'Hora · HH:MM', None),
                       ('type', 'Tipo de consulta', ['General', 'Control', 'Urgencia', 'Primera vez'])],
            'followup': [('date', 'Fecha del seguimiento', 'date'), ('reason', 'Motivo', 'text')],
            'study': [('name', 'Estudio', None), ('status', 'Estado', ['Solicitado', 'Pendiente', 'Recibido']),
                      ('notes', 'Indicaciones / resultado recibido', 'text')],
            'diagnosis': [('name', 'Diagnóstico', None)],
        }[self.kind]
        if self.kind == 'study' and not self.initial:
            self.initial = {'status': 'Solicitado'}
        self.form = self.add_form(specs)
        if self.kind == 'followup':
            ttk.Label(self.body, text='Captura recuperada de una versión anterior. Se conserva en la nota, sin programar tareas.\nDeja fecha y motivo vacíos para retirarla explícitamente del borrador.', style='Subtitle.TLabel', wraplength=590).pack(fill='x', pady=10)

    def validate(self):
        raw = self.raw()
        if self.kind in ('header', 'followup'):
            try:
                local_date(raw.get('date', ''))
            except ValueError as exc:
                raise FieldError('date', str(exc)) from exc
        if self.kind == 'header':
            try:
                attention_time(raw, self.owner.model.data['attended_at'])
            except ValueError as exc:
                raise FieldError('time' if raw.get('date') else 'date', str(exc)) from exc
        if self.kind in ('diagnosis', 'study') and not raw.get('name', '').strip():
            raise FieldError('name', 'Escribe el nombre antes de aplicar.')
        if self.kind == 'followup' and bool(raw.get('date')) != bool(raw.get('reason', '').strip()):
            raise FieldError('reason' if raw.get('date') else 'date', 'Completa fecha y motivo, o deja ambos vacíos.')
        return raw


class VitalsCapture(CaptureWindow):
    def build(self):
        initial = self.initial
        self.original = deepcopy(initial)
        stamp = initial.get('at', datetime.now().astimezone().isoformat())
        self.stamp = self.add_form([('date', 'Fecha de la toma', 'date'), ('time', 'Hora · HH:MM', None)],
                                  {'date': initial.get('date', stamp[:10]), 'time': initial.get('time', stamp[11:16])})
        self.values, self.units, self.previous_units, self.entries, self.unit_boxes, self.origins = {}, {}, {}, {}, {}, {}
        grid = ttk.Frame(self.body)
        grid.pack(fill='x')
        self.more = Collapsible(self.body, 'Más mediciones · glucosa y dolor', opened=any(initial.get('values', {}).get(k) for k in ('glucose', 'pain')))
        self.more.pack(fill='x')
        for i, (key, (label, units)) in enumerate(VITALS.items()):
            parent = grid if i < 8 else self.more.body
            cell = ttk.Frame(parent, padding=(0, 3, 12, 7))
            cell.grid(row=(i if i < 8 else i-8)//2, column=i%2, sticky='nsew')
            parent.columnconfigure(i%2, weight=1)
            ttk.Label(cell, text=label, style='Subtitle.TLabel').pack(anchor='w', pady=(0, 3))
            line = ttk.Frame(cell)
            line.pack(fill='x')
            item = initial.get('values', {}).get(key, {})
            raw = item.get('value', '') if isinstance(item, dict) else item
            unit = item.get('unit', units[0]) if isinstance(item, dict) else initial.get('units', {}).get(key, units[0])
            self.values[key] = tk.StringVar(value=str(raw))
            self.units[key] = tk.StringVar(value=unit)
            self.previous_units[key] = unit
            self.origins[key] = deepcopy(item) if isinstance(item, dict) else deepcopy(initial.get('origins', {}).get(key, {}))
            entry = ttk.Combobox(line, textvariable=self.values[key], values=['', *map(str, range(11))], state='readonly', width=9) if key == 'pain' else ttk.Entry(line, textvariable=self.values[key], width=9)
            entry.pack(side='left', fill='x', expand=True)
            self.entries[key] = entry
            if len(units) == 1:
                ttk.Label(line, text=units[0], width=6).pack(side='left', padx=6)
            else:
                box = ttk.Combobox(line, textvariable=self.units[key], values=units, state='readonly', width=6)
                box.pack(side='left', padx=6)
                box.bind('<<ComboboxSelected>>', lambda e, k=key: self.convert(k))
                self.unit_boxes[key] = box
            self.values[key].trace_add('write', lambda *a: self.changed())
        context_cell = ttk.Frame(self.more.body)
        context_cell.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Label(context_cell, text='Contexto de glucosa', style='Subtitle.TLabel').pack(anchor='w')
        self.context = tk.StringVar(value=initial.get('context', 'No especificado'))
        ttk.Combobox(context_cell, textvariable=self.context, values=['No especificado', 'Ayuno', 'Posprandial', 'Aleatoria'], state='readonly').pack(anchor='w')
        self.context.trace_add('write', lambda *a: self.changed())
        self.bmi = ttk.Label(self.body, text='IMC: requiere peso y estatura de esta toma.', style='Subtitle.TLabel')
        self.bmi.pack(fill='x', pady=6)
        ttk.Label(self.body, text='Solo se aplican los valores capturados. La evolución se consulta por separado.', style='Subtitle.TLabel', wraplength=610).pack(fill='x', pady=(0, 8))
        self.update_bmi()
        action(self.body, self.app, 'Ver evolución · conservar esta captura pendiente', self.history).pack(anchor='w', pady=4)

    def history(self):
        if self.raw() != self.baseline or self.recovered:
            self.changed()
        self.close()
        self.owner.open_history()

    def raw(self):
        return {**self.original, **self.stamp.values(raw=True), 'id': self.identifier,
                'values': {k: v.get() for k, v in self.values.items()}, 'units': {k: v.get() for k, v in self.units.items()},
                'context': self.context.get(), 'origins': deepcopy(self.origins)}

    def changed(self):
        if not self.loading:
            super().changed()
            self.update_bmi()

    def update_bmi(self):
        if not hasattr(self, 'bmi'):
            return
        try:
            weight = normalize_measurement('weight', self.values['weight'].get(), self.units['weight'].get())[0]
            height = normalize_measurement('height', self.values['height'].get(), self.units['height'].get())[0]
            self.bmi.configure(text=f'IMC de esta toma: {weight/(height/100)**2:.2f} kg/m²')
        except ValueError:
            self.bmi.configure(text='IMC: requiere peso y estatura válidos de esta toma.')

    def convert(self, key):
        unit, previous = self.units[key].get(), self.previous_units[key]
        raw = self.values[key].get()
        if raw.strip():
            try:
                canonical, _ = normalize_measurement(key, raw, previous)
                value = canonical*9/5+32 if unit == '°F' else canonical*{'lb': 1/0.45359237, 'm': .01, 'in': 1/2.54, 'mmol/L': 1/18.0182}.get(unit, 1)
                self.origins[key].setdefault('original_value', raw)
                self.origins[key].setdefault('original_unit', previous)
                self.values[key].set(f'{value:.8g}')
            except ValueError:
                self.units[key].set(previous)
                self.entries[key].state(['invalid'])
                self.error.configure(text='Revisa '+VITALS[key][0].lower()+' antes de convertir la unidad.')
                self.error.pack(side='bottom', fill='x', before=self.footer)
                return
        self.previous_units[key] = unit
        self.changed()

    def validate(self):
        try:
            stamp = attention_time(self.stamp.values(raw=True), self.original.get('at', ''))
        except ValueError as exc:
            raise FieldError('time', str(exc)) from exc
        values = {}
        for key, variable in self.values.items():
            self.entries[key].state(['!invalid'])
            if variable.get().strip():
                try:
                    normalize_measurement(key, variable.get(), self.units[key].get())
                except ValueError as exc:
                    self.entries[key].state(['invalid'])
                    if key in ('glucose', 'pain') and not self.more.opened:
                        self.more.toggle()
                    self.entries[key].focus_set()
                    raise DataError(VITALS[key][0]+': '+str(exc)) from exc
                values[key] = {**self.origins[key], 'value': variable.get().strip(), 'unit': self.units[key].get()}
        return {'id': self.identifier, 'at': stamp, 'context': self.context.get(), 'values': values}


class MedicationCapture(CaptureWindow):
    def build(self):
        from app.consultation_ui import medication_specs
        self.initial = {**({'frequency_kind': 'Cada N horas', 'duration_unit': 'días', 'status': 'Activo'} if not self.initial else {}), **self.initial}
        specs = medication_specs(self.app, self.owner.catalog_items())
        main_keys = ('name', 'presentation', 'strength', 'dose', 'dose_unit', 'route', 'frequency_kind', 'frequency', 'duration', 'duration_unit')
        main = [next(s for s in specs if s[0] == k) for k in main_keys]
        self.form = self.add_form(main)
        self.frequency_hint = ttk.Label(self.body, style='Subtitle.TLabel', wraplength=600)
        self.frequency_hint.pack(fill='x', pady=4)
        additional = [s for s in specs if s[0] not in main_keys]
        self.more = Collapsible(self.body, 'Más detalles · fechas, cantidad e indicaciones', opened=any(self.initial.get(k) for k, _, _ in additional if k != 'status'))
        self.more.pack(fill='x')
        self.extra = self.add_form(additional, parent=self.more.body)
        self.reviewed = tk.BooleanVar(value=not self.initial.get('needs_review', False))
        if self.initial.get('needs_review'):
            ttk.Label(self.body, text='⚠ Tratamiento reutilizado: su pauta está pendiente de revisión.', style='warning.TLabel', wraplength=600).pack(fill='x', pady=6)
            ttk.Checkbutton(self.body, text='He revisado y confirmado la pauta para esta consulta', variable=self.reviewed, command=self.changed).pack(anchor='w')
        self.preview = ttk.Label(self.body, style='Card.TLabel', padding=10, wraplength=610)
        self.preview.pack(fill='x', pady=8)
        catalog = self.catalog_section = Collapsible(self.body, 'Catálogo local y favoritos')
        catalog.pack(fill='x')
        self.products = self.owner.catalog_items()
        self.product = tk.StringVar()
        self.favorites = tk.BooleanVar()
        self.product_box = ttk.Combobox(catalog.body, textvariable=self.product, state='readonly')
        self.product_box.pack(fill='x')
        def refresh():
            self.choices = {r['name']+' · '+r.get('strength', ''): r for r in self.products if not self.favorites.get() or self.app.auth.current['id'] in r.get('favorites', [])}
            self.product_box.configure(values=list(self.choices))
        ttk.Checkbutton(catalog.body, text='Solo mis favoritos', variable=self.favorites, command=refresh).pack(anchor='w')
        def choose():
            product = self.choices.get(self.product.get())
            if product:
                for key in ('name', 'presentation', 'strength'):
                    self.form.vars[key].set(product.get(key, ''))
                self.extra.vars['ingredient'].set(product.get('ingredient', ''))
        action(catalog.body, self.app, 'Usar producto · conservar y revisar pauta', choose).pack(anchor='w', pady=4)
        self.catalog_notice = ttk.Label(catalog.body, style='Subtitle.TLabel', wraplength=560)
        self.catalog_notice.pack(fill='x')
        def favorite():
            try:
                self.app.care.save_catalog(self.raw(), favorite=True)
                self.owner._catalog = None
                self.catalog_notice.configure(text='Producto guardado en favoritos. La pauta se revisa en cada consulta.')
            except ValueError as exc:
                self.catalog_notice.configure(text=str(exc))
        action(catalog.body, self.app, 'Guardar producto en favoritos', favorite).pack(anchor='w')
        refresh()
        self.update_preview()

    def raw(self):
        raw = super().raw()
        raw['needs_review'] = not self.reviewed.get()
        return raw


    def changed(self):
        if not self.loading:
            super().changed()
            self.update_preview()

    def update_preview(self):
        if not hasattr(self, 'preview'):
            return
        kind = self.form.vars['frequency_kind'].get()
        labels = {'Cada N horas': ('Intervalo en horas', 'Escribe el intervalo indicado, mayor que cero.'),
                  'Veces al día': ('Número de veces al día', 'Escribe la frecuencia indicada, mayor que cero.'),
                  'Horarios': ('Horarios de administración', 'Escribe los horarios acordados.'),
                  'Según necesidad': ('Condición y límite indicados', 'Especifica cuándo se utiliza y los límites de la pauta.'),
                  'Pauta personalizada': ('Pauta libre', 'Describe la pauta completa.')}
        label, hint = labels.get(kind, ('Frecuencia', 'Revisa que el valor corresponda al tipo de frecuencia.'))
        index = next(i for i, s in enumerate(self.form.specs) if s[0] == 'frequency')
        self.form.cells[index].winfo_children()[0].configure(text=label)
        self.frequency_hint.configure(text=hint)
        summary = medication_text(self.raw())
        self.preview.configure(text=summary)
        if summary:
            self.preview.pack(fill='x', pady=8, before=self.catalog_section)
        else:
            self.preview.pack_forget()

    def validate(self):
        raw = self.raw()
        if not raw.get('name', '').strip():
            raise FieldError('name', 'Escribe el medicamento.')
        from app.clinical_models import numeric
        for key in ('dose', 'duration', 'quantity'):
            if raw.get(key):
                try:
                    numeric(raw[key], dict((k, label) for k, label, _ in self.form.specs+self.extra.specs)[key], minimum=0)
                except ValueError as exc:
                    raise FieldError(key, str(exc)) from exc
        for key in ('start', 'end'):
            try:
                raw[key] = local_date(raw.get(key, ''))
            except ValueError as exc:
                raise FieldError(key, str(exc)) from exc
        try:
            validate_medications([raw])
        except ValueError as exc:
            raise FieldError('end' if 'fin' in str(exc).lower() else 'frequency', str(exc)) from exc
        if self.initial.get('needs_review') and self.reviewed.get():
            try:
                validate_medications([raw], final=True)
            except ValueError as exc:
                missing = next((k for k in ('dose', 'dose_unit', 'route', 'frequency') if not raw.get(k)), 'frequency')
                raise FieldError(missing, str(exc)) from exc
        return raw


class HistoryCapture(CaptureWindow):
    def build(self):
        from app.consultation_ui import TrendPanel
        self.cancel_button.pack_forget()
        self.apply_button.configure(text='Volver a la consulta', command=self.close)
        ttk.Label(self.body, text='Histórico de consultas finalizadas. Las tomas de este borrador se distinguen como provisionales.', style='Subtitle.TLabel', wraplength=640).pack(fill='x', pady=8)
        self.trend = TrendPanel(self.body, self.app, self.owner.patient['id'], provisional=lambda: self.owner.model.data.get('vitals', []))
        self.trend.pack(fill='both', expand=True)
        def open_source(event=None):
            selected = self.trend.table.selection()
            if selected:
                record = self.trend.points[int(selected[0])].get('encounter_id')
                if record:
                    self.close()
                    self.app.open_encounter(record)
        self.trend.table.bind('<Double-1>', open_source)


class DocumentsCapture(CaptureWindow):
    def build(self):
        from app.attachment_ui import AttachmentPanel
        self.cancel_button.pack_forget()
        self.apply_button.configure(text='Conservar cola y volver', command=self.cancel)
        ttk.Label(self.body, text='Documentos de esta consulta. La acción Incorporar guarda cada archivo; cerrar conserva la cola pendiente.', style='Subtitle.TLabel', wraplength=780).pack(fill='x', pady=6)
        self.details_form = None
        self.panel = AttachmentPanel(self.body, self.app, self.owner.patient['id'], self.owner.record['id'], changed=self.changed,
                                     on_preview=self.preview_document, on_details=self.edit_details)
        self.panel.restore_queue(self.owner.model.queue)
        self.owner.model.queue = deepcopy(self.panel.queue)
        saved_edits = self.app.attachments.load_metadata_edits(**self.panel.target)
        if saved_edits is not None:
            self.owner.model.pending = {**{k: v for k, v in self.owner.model.pending.items() if v['kind'] != 'document_metadata'}, **saved_edits}
        self.panel.destination.configure(text='Consulta del '+display_date(self.owner.record['attended_at'])+' · '+self.owner.patient['name'])
        self.panel.pack(fill='both', expand=True)
        pending = next((p for p in self.owner.model.pending.values() if p['kind'] == 'document_metadata' and
                        (not self.request_identifier or p['id'] == self.request_identifier)), None)
        if pending:
            self.edit_details(pending['id'])

    def raw(self):
        return {}

    def changed(self):
        if not self.loading and hasattr(self, 'panel'):
            self.sync_pending()
            self.owner.touch()
            if getattr(self, 'persist_timer', None):
                self.after_cancel(self.persist_timer)
            self.persist_timer = self.after(800, self.persist_feedback)
            if not self.details_form:
                self.owner.refresh_documents()

    def persist_pending(self):
        self.sync_pending()
        self.app.attachments.save_metadata_edits(self.owner.model.pending, **self.panel.target)
        return True

    def persist_feedback(self):
        self.persist_timer = None
        try:
            self.persist_pending()
        except (ValueError, OSError):
            self.error.configure(text='La captura documental sigue en memoria; no se pudo guardar para recuperación.')
            self.error.pack(side='bottom', fill='x', before=self.footer)

    def close(self):
        if getattr(self, 'persist_timer', None):
            self.after_cancel(self.persist_timer)
            self.persist_timer = None
        self.persist_pending()
        return super().close()

    def sync_pending(self):
        self.owner.model.queue = deepcopy(self.panel.queue)
        if self.details_form:
            value = self.details_form.values(raw=True)
            if value != self.metadata_baseline or self.metadata_recovered:
                self.owner.model.remember('document_metadata', self.metadata_row['id'], value)
                pending = self.owner.model.pending[self.owner.model.key('document_metadata', self.metadata_row['id'])]
                pending.update(revision=self.metadata_row['revision'], base=deepcopy(self.metadata_row))

    def preview_document(self, row):
        if self.panel.busy:
            return
        self.changed()
        self.close()
        self.owner.open_document(row['id'])

    def edit_details(self, identifier=None):
        row = self.app.attachments.get(identifier) if identifier else self.panel.selected()
        if not row or self.panel.busy:
            return
        self.metadata_row = row
        key = self.owner.model.key('document_metadata', row['id'])
        pending = self.owner.model.pending.get(key)
        if pending and pending.get('base'):
            self.metadata_row = deepcopy(pending['base'])
        if pending and pending.get('revision'):
            self.metadata_row['revision'] = pending['revision']
        self.metadata_recovered = bool(pending)
        self.panel.pack_forget()
        self.details_form = CaptureForm(self.body, [('title', 'Título del documento', None), ('category', 'Categoría', self.panel.categories),
            ('document_date', 'Fecha del documento', 'date'), ('notes', 'Descripción', 'text'), ('reason', 'Motivo del cambio', None)],
            pending['values'] if pending else row, self.changed, self.app.theme)
        self.details_form.pack(fill='x', pady=8)
        self.metadata_baseline = deepcopy(self.details_form.values(raw=True))
        self.cancel_button.configure(text='Volver a documentos')
        self.cancel_button.pack(side='left')
        self.apply_button.configure(text='Aplicar detalles', command=self.apply_details)
        self.app.theme._walk(self.details_form)

    def apply_details(self):
        try:
            values = self.details_form.values()
            self.app.attachments.update(self.metadata_row['id'], values, self.metadata_row['revision'], values.get('reason', ''))
        except (ValueError, OSError) as exc:
            from app.editing_state import VersionConflict
            if isinstance(exc, VersionConflict):
                self.apply_button.configure(text='Revisar diferencias', command=self.review_metadata_conflict)
            self.error.configure(text=str(exc))
            self.error.pack(side='bottom', fill='x', before=self.footer)
            return
        self.owner.model.discard('document_metadata', self.metadata_row['id'])
        self.back_to_documents()
        self.changed()

    def review_metadata_conflict(self):
        from app.document_edit_ui import edit_document
        self.persist_pending()
        panel, identifier, owner = self.panel, self.metadata_row['id'], self.owner
        self.close()
        def applied():
            owner.model.discard('document_metadata', identifier)
            owner.touch()
        return edit_document(panel, self.app.attachments.get(identifier), on_apply=applied)

    def back_to_documents(self):
        self.details_form.destroy()
        self.details_form = None
        self.resolution.pack_forget()
        self.error.pack_forget()
        self.cancel_button.pack_forget()
        self.apply_button.configure(text='Conservar cola y volver', command=self.cancel)
        self.panel.pack(fill='both', expand=True)
        self.panel.refresh()

    def discard(self):
        if self.details_form:
            self.owner.model.discard('document_metadata', self.metadata_row['id'])
            self.back_to_documents()
            self.changed()
            if self.close_requested:
                self.close()
        else:
            self.cancel()

    def defer(self):
        self.changed()
        if hasattr(self.owner, 'refresh_pending'):
            self.owner.refresh_pending()
        self.close()

    def cancel(self):
        if self.details_form:
            if self.metadata_recovered or self.details_form.values(raw=True) != self.metadata_baseline:
                self.changed()
                self.show_resolution()
            elif self.close_requested:
                self.close()
            else:
                self.dismiss_dropdowns()
                self.back_to_documents()
            return
        if self.panel.busy:
            self.error.configure(text='La incorporación sigue en curso. Espera al resultado de cada archivo antes de volver.')
            self.error.pack(side='bottom', fill='x', before=self.footer)
            return
        self.changed()
        self.close()


class ReuseCapture(CaptureWindow):
    def build(self):
        self.apply_button.configure(text='Añadir pendiente de revisión')
        self.selected = tk.StringVar()
        self.known = []
        ttk.Label(self.body, text='Elige un tratamiento. Se añadirá como pendiente de revisar para esta consulta.', style='warning.TLabel', wraplength=620).pack(fill='x', pady=6)
        self.list_body = ttk.Frame(self.body)
        self.list_body.pack(fill='x')
        def gather():
            known = [(r, 'Medicación habitual') for r in self.owner.patient.get('medication_records', [])]
            history = sorted([r for r in self.app.clinic.list('encounters') if r['patient_id'] == self.owner.patient['id'] and r['status'] == 'Finalizada'], key=lambda r: r['attended_at'], reverse=True)
            for visit in history[:5]:
                known.extend((r, 'Consulta del '+display_date(visit['attended_at'])) for r in visit.get('prescriptions', []))
            return known
        def ready(rows):
            if not self.winfo_exists():
                return
            self.known = rows
            for i, (row, source) in enumerate(rows):
                ttk.Label(self.list_body, text=source, style='Subtitle.TLabel').pack(anchor='w', pady=(8, 2))
                ttk.Radiobutton(self.list_body, text=medication_text(row), variable=self.selected, value=str(i)).pack(anchor='w', pady=3)
            if not rows:
                ttk.Label(self.list_body, text='No hay tratamientos estructurados previos.').pack(anchor='w', pady=10)
        self.app.background(gather, ready)

    def apply(self):
        if self.selected.get():
            import uuid
            original = deepcopy(self.known[int(self.selected.get())][0])
            original.update(id=str(uuid.uuid4()), needs_review=True)
            try:
                self.owner.model.apply('medication', original['id'], original)
            except ValueError:
                self.owner.model.remember('medication', original['id'], original)
            self.owner.applied()
            self.close()


class ReviewCapture(CaptureWindow):
    def build(self):
        from app.clinical_models import encounter_sections
        self.cancel_button.configure(text='Volver a editar')
        self.apply_button.configure(text='Confirmar finalización', command=self.finalize)
        ttk.Label(self.body, text='Responsable: '+self.app.auth.current['name']+'\n'+display_date(self.owner.model.data['attended_at']), wraplength=650).pack(fill='x', pady=6)
        issues = self.owner.model.problems()
        if issues:
            ttk.Label(self.body, text='Resuelve lo siguiente antes de finalizar:', style='warning.TLabel').pack(fill='x', pady=6)
            for target, message in issues:
                def go(key=target):
                    self.close()
                    self.owner.goto_issue(key)
                row = ttk.Frame(self.body)
                row.pack(fill='x', pady=3)
                action(row, self.app, 'Revisar', go).pack(side='right', padx=4)
                ttk.Label(row, text=message, wraplength=530).pack(side='left', fill='x', expand=True)
            self.apply_button.state(['disabled'])
        for label, text in encounter_sections(self.owner.model.snapshot()):
            if text:
                ttk.Label(self.body, text=label, style='Section.TLabel').pack(anchor='w', pady=(12, 4))
                ttk.Label(self.body, text=text, wraplength=640, justify='left').pack(fill='x')
        docs = self.app.attachments.list(self.owner.patient['id'], self.owner.record['id'])
        ttk.Label(self.body, text='Documentos de esta consulta', style='Section.TLabel').pack(anchor='w', pady=(12, 4))
        ttk.Label(self.body, text='\n'.join(r['title']+' · '+r['mime'] for r in docs) or 'Sin documentos incorporados.', wraplength=640).pack(fill='x')
        ttk.Label(self.body, text='Al confirmar, la consulta quedará finalizada. Las correcciones posteriores se registrarán como adendas.', style='Subtitle.TLabel', wraplength=630).pack(fill='x', pady=12)

    def finalize(self):
        try:
            self.owner.save(final=True)
        except (ValueError, OSError) as exc:
            self.error.configure(text='No se finalizó: '+str(exc))
            self.error.pack(side='bottom', fill='x', before=self.footer)
            return
        owner, identifier = self.owner, self.owner.record['id']
        self.close()
        self.app.pages.pop('consulta:'+identifier, None)
        owner.destroy()
        self.app.open_encounter(identifier)
