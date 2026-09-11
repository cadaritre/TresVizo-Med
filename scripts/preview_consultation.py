"""Consulta contextual con datos ficticios para revisión visual local."""
import argparse
from datetime import date
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app.main_window import Application

parser = argparse.ArgumentParser()
parser.add_argument('--view', choices=['filled', 'empty', 'long', 'vitals', 'medication', 'review', 'final'], default='filled')
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix='tresvizo-consulta-contextual-') as directory:
    app = Application(directory)
    uid = app.auth.create_user('Dra. Elena Martínez', 'elena', 'Sintetica-local-12345')
    app.auth.login(uid, 'Sintetica-local-12345')
    app.identity.save({'clinic_name': 'Clínica de demostración · datos ficticios'})
    app.profiles.save(uid, {'avatar': 'zorro'})
    name = 'Ana Lucía Ramírez de León'
    if args.view == 'long':
        name += ' · nombre extenso para comprobar la distribución en la ventana'
    patient = app.clinic.save('patients', {'name': name, 'birth_date': '1980-06-15', 'sex': 'No especificado',
                                         'allergy_status': 'No interrogado'})
    today = date.today().isoformat()
    values = {'patient_id': patient['id'], 'status': 'Borrador', 'attended_at': today+'T10:00:00', 'type': 'Control'}
    if args.view != 'empty':
        values.update(reason='Consulta de demostración para comprobar la captura contextual.',
                      subjective='Evolución documentada por el profesional. Información ficticia para revisar la interfaz.',
                      objective='Exploración registrada para la prueba visual.',
                      assessment_notes='Valoración narrativa de ejemplo, independiente de las mediciones.',
                      plan='Indicaciones de demostración. Revisar los documentos y continuar el seguimiento acordado.',
                      diagnoses=[{'name': 'Diagnóstico de ejemplo'}],
                      vitals=[{'id': str(uuid.uuid4()), 'at': today+'T10:05:00', 'values': {
                          'systolic': {'value': '120', 'unit': 'mmHg'}, 'diastolic': {'value': '80', 'unit': 'mmHg'},
                          'heart_rate': {'value': '78', 'unit': 'lpm'}, 'weight': {'value': '70', 'unit': 'kg'}, 'height': {'value': '175', 'unit': 'cm'}}},
                          {'id': str(uuid.uuid4()), 'at': today+'T10:20:00', 'values': {'temperature': {'value': '36.7', 'unit': '°C'}}}],
                      prescriptions=[{'name': 'Producto A de demostración', 'presentation': 'Tabletas', 'dose': '1', 'dose_unit': 'tableta',
                          'route': 'Oral', 'frequency_kind': 'Cada N horas', 'frequency': '12', 'duration': '3', 'duration_unit': 'días',
                          'instructions': 'Pauta ficticia para comprobar el resumen; no es una indicación médica.'},
                          {'name': 'Producto B de demostración', 'dose': '2', 'dose_unit': 'mL', 'route': 'Oral',
                           'frequency_kind': 'Horarios', 'frequency': '08:00 y 20:00', 'duration': '5', 'duration_unit': 'días'}],
                      study_orders=[{'name': 'Estudio de demostración', 'status': 'Solicitado', 'notes': 'Indicaciones documentadas por el profesional.'}],
                      followup={'date': today, 'reason': 'Revisión de los resultados de prueba.'})
        if args.view == 'long':
            values['subjective'] = '\n'.join(f'{i+1}. Párrafo ficticio de evolución clínica para revisar texto extenso, selección, desplazamiento y reapertura.' for i in range(30))
    visit = app.clinic.save('encounters', values)
    if args.view != 'empty':
        for i in range(12 if args.view == 'long' else 2):
            path = Path(directory)/f'Documento de demostración {i+1}.png'
            Image.new('RGB', (120+i, 80), (245-i, 245-i, 250-i)).save(path)
            app.attachments.add(path, patient['id'], visit['id'], category='Otro documento')
    app.shell()
    app.title('TresVizo Med · consulta contextual sintética · '+args.view)
    app.geometry('1366x768')
    editor = app.encounter_editor(patient, visit)
    if args.view in ('vitals', 'medication'):
        editor.open_tool(args.view, editor.model.data['vitals'][0]['id'] if args.view == 'vitals' else editor.model.data['prescriptions'][0]['id'])
    elif args.view == 'review':
        editor.finish()
    elif args.view == 'final':
        editor.save(final=True)
        app.pages.pop('consulta:'+visit['id'])
        editor.destroy()
        app.open_encounter(visit['id'])
    app.mainloop()
