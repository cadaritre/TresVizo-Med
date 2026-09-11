"""Indicadores, actividad y acceso a pacientes frecuentes."""
import csv
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, filedialog
from app.components import ScrollFrame, Chart
from app.widgets import DateField
from app.clinical_models import display_date
from app.transfer import safe_csv

class StatisticsPage(ScrollFrame):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app,self.latest,self.ticket = app,{},0
        body = self.body
        app.heading(body,'Mis estadísticas','Actividad por fecha de atención · consultas finalizadas')
        bar = ttk.Frame(body)
        bar.pack(fill='x',pady=8)
        self.period = tk.StringVar(value='Mes')
        for title in ('Hoy','Semana','Mes','Personalizado'):
            ttk.Radiobutton(bar,text=title,variable=self.period,value=title,command=self.period_changed).pack(side='left',padx=(0,12))
        ttk.Button(bar,text='Actualizar',command=lambda:app.guard(self.refresh)).pack(side='right')
        self.range = ttk.Frame(body)
        self.start = DateField(self.range,app.theme,date.today().replace(day=1).isoformat())
        self.start.pack(side='left',fill='x',expand=True)
        self.end = DateField(self.range,app.theme,date.today().isoformat())
        self.end.pack(side='left',fill='x',expand=True,padx=8)
        from app.widgets import Collapsible,Form
        filters = Collapsible(body,'Filtros de actividad')
        filters.pack(fill='x')
        self.doctors = {u['name']+' · '+u['username']:u['id'] for u in app.auth.users()}
        self.doctors['Toda la clínica'] = '*'
        selected = next(n for n,uid in self.doctors.items() if uid == app.auth.current['id'])
        specs = [('type','Tipo de consulta',None),('diagnosis','Diagnóstico',None),('group','Pacientes',['Todos','Nuevos','Recurrentes'])]
        if app.auth.current['role'] == 'admin': specs.append(('doctor','Doctor',list(self.doctors)))
        self.filters = Form(filters.body,specs,{'doctor':selected,'group':'Todos'},theme=app.theme)
        self.filters.pack(fill='x')
        cards = ttk.Frame(body)
        cards.pack(fill='x',pady=12)
        self.numbers = {}
        for key,label in [('consultations','Consultas'),('patients','Pacientes únicos'),('new','Nuevos para este doctor')]:
            card = ttk.Frame(cards,style='Card.TFrame',padding=16)
            card.pack(side='left',fill='both',expand=True,padx=(0,8))
            number = ttk.Label(card,text='—',style='Metric.TLabel')
            number.pack(anchor='w')
            ttk.Label(card,text=label,style='Card.TLabel').pack(anchor='w')
            self.numbers[key] = number
        self.summary = tk.StringVar(value='Preparando estadísticas…')
        ttk.Label(body,textvariable=self.summary,style='Subtitle.TLabel',wraplength=850).pack(fill='x',pady=8)
        self.activity = ActivityPlot(body,app)
        self.activity.pack(fill='x',pady=8)
        tabs = ttk.Notebook(body)
        tabs.pack(fill='x',pady=12)
        diagnoses = ttk.Frame(tabs)
        tabs.add(diagnoses,text='Diagnósticos')
        self.diagnoses = self.table(diagnoses,{'name':'Diagnóstico','count':'Consultas','percent':'Porcentaje'})
        frequent = ttk.Frame(tabs)
        tabs.add(frequent,text='Pacientes con más consultas')
        self.frequent = self.table(frequent,{'name':'Paciente','file':'Expediente','count':'Consultas'})
        self.frequent_page = 0
        pager = ttk.Frame(frequent)
        pager.pack(fill='x')
        self.frequent_count = ttk.Label(pager, style='Subtitle.TLabel')
        self.frequent_count.pack(side='left')
        ttk.Button(pager, text='Anterior', command=lambda: self.turn(-1), style='Link.TButton').pack(side='right')
        ttk.Button(pager, text='Siguiente', command=lambda: self.turn(1), style='Link.TButton').pack(side='right')
        self.frequent.bind('<Double-1>',lambda e:app.patient_record(self.frequent.selection()[0]) if self.frequent.selection() else None)
        ttk.Button(frequent,text='Abrir expediente',command=lambda:app.patient_record(self.frequent.selection()[0]) if self.frequent.selection() else None).pack(anchor='w',pady=6)
        distributions = ttk.Frame(tabs)
        tabs.add(distributions,text='Distribuciones')
        self.views = {'Tipos de consulta':'types','Edad en la atención':'ages','Sexo registrado':'sexes','Motivos frecuentes':'reasons'}
        self.view = tk.StringVar(value='Tipos de consulta')
        select = ttk.Combobox(distributions,textvariable=self.view,values=list(self.views),state='readonly')
        select.pack(anchor='w',pady=8)
        self.chart = Chart(distributions,app.theme)
        self.chart.pack(fill='x')
        select.bind('<<ComboboxSelected>>',lambda e:self.chart.set(self.latest.get(self.views[self.view.get()],{})))
        ttk.Label(body,text='Una consulta puede tener varios diagnósticos; sus porcentajes pueden sumar más de 100 %.',style='Subtitle.TLabel',wraplength=850).pack(anchor='w',pady=8)
        actions = ttk.Frame(body)
        actions.pack(fill='x',pady=8)
        self.export_buttons = [ttk.Button(actions,text='Exportar CSV',command=self.csv), ttk.Button(actions,text='Vista previa PDF',command=self.pdf)]
        for button in self.export_buttons:
            button.pack(side='left', padx=8)
        self.ready = False
        for variable in [self.start.var, self.end.var, *self.filters.vars.values()]:
            variable.trace_add('write', self.invalidate)
        self.period_changed()

    def invalidate(self, *args):
        self.ticket += 1
        self.ready = False
        for button in self.export_buttons:
            button.state(['disabled'])
        self.summary.set('Filtros modificados · pulsa Actualizar. Las cifras anteriores todavía no corresponden a estos filtros.')

    def table(self,parent,columns):
        tree = ttk.Treeview(parent,columns=list(columns),show='headings',height=6)
        for key,title in columns.items():
            tree.heading(key,text=title)
            tree.column(key,width=380 if key=='name' else 130,minwidth=80)
        tree.pack(fill='x')
        return tree

    def period_changed(self):
        today = date.today()
        if self.period.get() == 'Personalizado':
            self.range.pack(fill='x',after=self.range.master.winfo_children()[2],pady=8)
        else:
            self.range.pack_forget()
            start = today if self.period.get() == 'Hoy' else today-timedelta(days=today.weekday()) if self.period.get() == 'Semana' else today.replace(day=1)
            self.start.var.set(display_date(start.isoformat()))
            self.end.var.set(display_date(today.isoformat()))
        self.app.guard(self.refresh)

    def refresh(self):
        from app.storage import DataError
        if self.period.get() != 'Personalizado':
            today = date.today()
            start = today if self.period.get() == 'Hoy' else today-timedelta(days=today.weekday()) if self.period.get() == 'Semana' else today.replace(day=1)
            self.start.var.set(display_date(start.isoformat()))
            self.end.var.set(display_date(today.isoformat()))
        self.invalidate()
        start,end = self.start.get(),self.end.get()
        if not start or not end or start>end:
            raise DataError('Revisa las fechas del periodo.')
        fields = self.filters.values()
        doctor = self.doctors.get(fields.get('doctor'),self.app.auth.current['id'])
        doctor_label = next((name for name, uid in self.doctors.items() if uid == doctor), 'Doctor')
        self.ticket += 1
        ticket = self.ticket
        self.summary.set('Actualizando datos…')
        def done(data):
            if not self.winfo_exists() or ticket != self.ticket:return
            if isinstance(data, Exception):
                self.summary.set('No se pudieron actualizar las estadísticas. Revisa los filtros y pulsa Actualizar.')
                return
            self.latest = data
            self.ready = True
            self.latest['_scope'] = {'doctor': doctor_label, 'start': start, 'end': end, **fields}
            for button in self.export_buttons:
                button.state(['!disabled'])
            for key,label in self.numbers.items():label.configure(text=str(data[key]))
            variation = f"{data['variation']:+.1f}%" if data['variation'] is not None else 'Sin base de comparación'
            self.summary.set(f"{doctor_label} · {display_date(start)} — {display_date(end)} · {data['recurrent']} recurrentes · {data['average']:.1f} consultas por día activo\n{data['drafts']} borradores propios · Cambio: {variation}")
            self.latest['_summary'] = self.summary.get()
            self.activity.set(data['activity'])
            self.diagnoses.delete(*self.diagnoses.get_children())
            for name,count in data['diagnoses'].items():
                self.diagnoses.insert('','end',values=(name,count,f"{count*100/data['consultations']:.1f}%"))
            self.render_frequent()
            self.chart.set(data.get(self.views[self.view.get()],{}))
        def work():
            try:
                data = self.app.clinic.statistics(start,end,doctor,fields['type'],fields['diagnosis'],fields['group'])
                data['_patients'] = {p['id']:p for p in self.app.clinic.list('patients',True)}
                return data
            except (ValueError, OSError) as exc:
                return exc
        self.app.background(work,done)

    def turn(self, delta):
        self.frequent_page = max(0, self.frequent_page+delta)
        self.render_frequent()

    def render_frequent(self):
        rows = list(self.latest.get('frequency', {}).items())
        self.frequent_page = min(self.frequent_page, max(0, (len(rows)-1)//100))
        self.frequent.delete(*self.frequent.get_children())
        for pid, count in rows[self.frequent_page*100:(self.frequent_page+1)*100]:
            patient = self.latest.get('_patients', {}).get(pid, {})
            self.frequent.insert('', 'end', iid=pid, values=(patient.get('name', 'Paciente'), patient.get('file_number', ''), count))
        self.frequent_count.configure(text=f'{len(rows)} pacientes · página {self.frequent_page+1}')

    def csv(self):
        if not self.latest or not self.ready:return
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('Estadísticas CSV','*.csv')])
        if not path:return
        data = self.latest
        with open(path,'w',newline='',encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Indicador','Valor'])
            for label, value in self.latest['_scope'].items():
                writer.writerow([label, safe_csv(value)])
            for key,label in [('consultations','Consultas'),('patients','Pacientes únicos'),('new','Nuevos'),('recurrent','Recurrentes')]:
                writer.writerow([label,data[key]])
            for label,values in [('Día',data['activity']),('Diagnóstico',data['diagnoses'])]:
                for key,value in values.items():writer.writerow([safe_csv(label+' · '+key),value])
        self.app.auth.audit('exportar_estadisticas',data['doctor'])
        self.app.status.set('Resumen CSV exportado: '+path)
    def pdf(self):
        if self.latest and self.ready:
            self.app.pdf_preview('Resumen de actividad',[('Periodo e indicadores',self.latest['_summary']),('Filtros',str(self.latest['_scope'])),('Diagnósticos','\n'.join(f'{k}: {v}' for k,v in self.latest['diagnoses'].items()))],doctor=self.latest['_scope']['doctor'])

class ActivityPlot(tk.Canvas):
    def __init__(self,parent,app):
        super().__init__(parent,height=190,highlightthickness=0)
        self.app,self.data = app,{}
        self.bind('<Configure>',lambda e:self.draw())
        app.theme.subscribe(self,lambda t:self.draw())
    def set(self,data):self.data=data; self.draw()
    def draw(self):
        t = self.app.theme.tokens
        self.configure(background=t['surface'])
        self.delete('all')
        w = max(self.winfo_width(),280)
        if not self.data:
            self.create_text(w/2,90,text='No hay consultas finalizadas en este periodo.',fill=t['muted'])
            return
        rows = list(self.data.items())
        maximum = max(self.data.values())
        dates = [date.fromisoformat(k).toordinal() for k,v in rows]
        span = max(1,max(dates)-min(dates))
        self.create_text(18,18,text='Actividad · consultas por día',fill=t['text'],anchor='w',font=('Segoe UI Semibold',12))
        self.create_line(42,40,42,155,w-20,155,fill=t['separator'])
        previous = None
        for (day,value),ordinal in zip(rows,dates):
            x,y = 50+(w-85)*(ordinal-min(dates))/span,150-95*value/maximum
            if previous:self.create_line(previous[0],previous[1],x,y,fill=t['chart1'],width=2)
            item = self.create_oval(x-4,y-4,x+4,y+4,fill=t['chart1'],outline='')
            self.tag_bind(item,'<Enter>',lambda e,d=day,v=value:self.app.status.set(display_date(d)+f' · {v} consultas'))
            previous = (x,y)
        self.create_text(50,175,text=display_date(rows[0][0]),fill=t['muted'],anchor='w')
        self.create_text(w-20,175,text=display_date(rows[-1][0]),fill=t['muted'],anchor='e')
