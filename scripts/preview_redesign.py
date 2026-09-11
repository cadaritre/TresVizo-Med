"""Recorrido visual con datos exclusivamente sintéticos y carpeta temporal."""
import argparse
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.main_window import Application

parser = argparse.ArgumentParser()
parser.add_argument('--page',default='home')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='tresvizo-redesign-qa-') as directory:
    app = Application(directory)
    uid = app.auth.create_user('Dra. Elena Martínez','elena','Prueba-local-12345')
    app.auth.login(uid,'Prueba-local-12345')
    app.profiles.save(uid,{'avatar':'zorro'})
    for name,user,avatar in [('Dr. Gabriel Méndez','gabriel','buho'),('Dra. Sofía Castillo','sofia','flor')]:
        other = app.auth.create_user(name,user,'Prueba-local-12345')
        app.profiles.save(other,{'avatar':avatar})
    app.identity.save({'clinic_name':'Clínica de prueba · datos sintéticos'})
    patients = []
    for i,name in enumerate(['Ana Lucía Ramírez de León','Carlos Andrés Fuentes','María Fernanda López','José Ricardo Morales','Valentina Pérez Castillo']):
        patients.append(app.clinic.save('patients',{'name':name,'sex':'No especificado','birth_date':f'{1980+i*4}-06-15','phone':'+502 5555 010'+str(i),
                                                    'allergy_status':'No interrogado','clinical_notes':'Información ficticia para revisar la interfaz.'}))
    patient = patients[0]
    for i in range(5):
        stamp = (date.today()-timedelta(days=60-i*12)).isoformat()+'T09:00:00'
        app.clinic.save('encounters',{'patient_id':patient['id'],'status':'Finalizada','attended_at':stamp,'reason':'Seguimiento de prueba','assessment':'Diagnóstico sintético','plan':'Indicaciones ficticias para prueba visual.',
                                    'vitals':[{'at':stamp,'values':{'weight':{'value':str(70+i),'unit':'kg'},'height':{'value':'175','unit':'cm'},'systolic':{'value':str(120+i),'unit':'mmHg'},'diastolic':{'value':str(80+i),'unit':'mmHg'}}}]})
    for i,p in enumerate(patients[:3]):
        app.clinic.save('appointments',{'patient_id':p['id'],'due_at':date.today().isoformat()+f'T{10+i}:00:00','status':'Confirmada','reason':'Cita de demostración'})
    app.clinic.save('followups',{'patient_id':patient['id'],'due_at':date.today().isoformat()+'T15:00:00','status':'Pendiente','reason':'Revisión de resultados ficticios'})
    draft = app.clinic.save('encounters',{'patient_id':patient['id'],'status':'Borrador','attended_at':date.today().isoformat()+'T10:00:00','reason':'Consulta de ejemplo','subjective':'Narración clínica sintética.','objective':'Exploración de ejemplo.','plan':'Plan pendiente de revisión.'})
    app.shell()
    app.title('TresVizo Med · revisión visual sintética')
    app.geometry('1366x768')
    def page(name):
        if name == 'home': app.show('Inicio')
        elif name == 'patient': app.patient_editor()
        elif name == 'record': app.patient_record(patient['id'])
        elif name in ('vitals','medications','consultation'):
            editor = app.encounter_editor(patient,draft)
            editor.tabs.select(1 if name == 'vitals' else 2 if name == 'medications' else 0)
            if name == 'medications': editor.medications.new()
        elif name == 'settings': app.show('Configuración')
        elif name == 'login': app.logout()
        elif name == 'stats': app.show('Mis estadísticas')
    for key,name in [('1','home'),('2','patient'),('3','vitals'),('4','medications'),('5','settings'),('6','record'),('7','stats')]:
        app.bind('<Control-Alt-'+key+'>',lambda e,n=name:page(n))
    page(args.page)
    app.mainloop()
