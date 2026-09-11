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
        self.frequent.bind('<Double-1>',lambda e:app.patient_record(self.frequent.selection()[0]) if self.frequent.selection() else None)
        ttk.Button(frequent,text='Abrir expediente',command=lambda:app.patient_record(self.frequent.selection()[0]) if self.frequent.selection() else None).pack(anchor='w',pady=6)
        distributions = ttk.Frame(tabs)
        tabs.add(distributions,text='Distribuciones')
        self.views = {'Tipos de consulta':'types','Edad en la atención':'ages','Sexo registrado':'sexes','Estados de citas':'appointments','Motivos frecuentes':'reasons'}
        self.view = tk.StringVar(value='Tipos de consulta')
        select = ttk.Combobox(distributions,textvariable=self.view,values=list(self.views),state='readonly')
        select.pack(anchor='w',pady=8)
        self.chart = Chart(distributions,app.theme)
        self.chart.pack(fill='x')
        select.bind('<<ComboboxSelected>>',lambda e:self.chart.set(self.latest.get(self.views[self.view.get()],{})))
        ttk.Label(body,text='Una consulta puede tener varios diagnósticos; sus porcentajes pueden sumar más de 100 %.',style='Subtitle.TLabel',wraplength=850).pack(anchor='w',pady=8)
        actions = ttk.Frame(body)
        actions.pack(fill='x',pady=8)
        ttk.Button(actions,text='Seguimientos pendientes',command=lambda:app.show('Seguimientos')).pack(side='left')
        ttk.Button(actions,text='Exportar CSV',command=self.csv).pack(side='left',padx=8)
        ttk.Button(actions,text='Vista previa PDF',command=self.pdf).pack(side='left')
        self.period_changed()

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
        start,end = self.start.get(),self.end.get()
        if not start or not end or start>end:
            raise DataError('Revisa las fechas del periodo.')
        fields = self.filters.values()
        doctor = self.doctors.get(fields.get('doctor'),self.app.auth.current['id'])
        self.ticket += 1
        ticket = self.ticket
        self.summary.set('Actualizando datos…')
        def done(data):
            if not self.winfo_exists() or ticket != self.ticket:return
            self.latest = data
            for key,label in self.numbers.items():label.configure(text=str(data[key]))
            variation = f"{data['variation']:+.1f}%" if data['variation'] is not None else 'Sin base de comparación'
            self.summary.set(f"{display_date(start)} — {display_date(end)} · {data['recurrent']} recurrentes · {data['average']:.1f} consultas por día activo\n{data['pending']} seguimientos pendientes ({data['overdue']} vencidos) · {data['drafts']} borradores propios · Cambio: {variation}")
            self.activity.set(data['activity'])
            self.diagnoses.delete(*self.diagnoses.get_children())
            for name,count in data['diagnoses'].items():
                self.diagnoses.insert('','end',values=(name,count,f"{count*100/data['consultations']:.1f}%"))
            patients = {p['id']:p for p in self.app.clinic.list('patients',True)}
            self.frequent.delete(*self.frequent.get_children())
            for pid,count in data['frequency'].items():
                p = patients.get(pid,{})
                self.frequent.insert('','end',iid=pid,values=(p.get('name','Paciente'),p.get('file_number',''),count))
            self.chart.set(data.get(self.views[self.view.get()],{}))
        self.app.background(lambda:self.app.clinic.statistics(start,end,doctor,fields['type'],fields['diagnosis'],fields['group']),done)

    def csv(self):
        if not self.latest:return
        path = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('Estadísticas CSV','*.csv')])
        if not path:return
        data = self.latest
        with open(path,'w',newline='',encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Indicador','Valor'])
            for key,label in [('consultations','Consultas'),('patients','Pacientes únicos'),('new','Nuevos'),('recurrent','Recurrentes'),('pending','Seguimientos pendientes'),('overdue','Seguimientos vencidos')]:
                writer.writerow([label,data[key]])
            for label,values in [('Día',data['activity']),('Diagnóstico',data['diagnoses'])]:
                for key,value in values.items():writer.writerow([safe_csv(label+' · '+key),value])
        self.app.auth.audit('exportar_estadisticas',data['doctor'])
        self.app.status.set('Resumen CSV exportado.')
    def pdf(self):
        if self.latest:
            self.app.pdf_preview('Resumen de actividad',[('Periodo e indicadores',self.summary.get()),('Diagnósticos','\n'.join(f'{k}: {v}' for k,v in self.latest['diagnoses'].items()))],doctor=self.app.auth.current['name'])

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
