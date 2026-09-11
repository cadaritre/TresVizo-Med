"""Recorrido de pacientes y SOAP con datos sintéticos, aislado de la clínica."""
import argparse
from datetime import date
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app.main_window import Application

parser = argparse.ArgumentParser()
parser.add_argument('--view', choices=['patients', 'registration', 'soap', 'options', 'legacy', 'complete'], default='soap')
parser.add_argument('--width', type=int, default=1366)
parser.add_argument('--height', type=int, default=768)
parser.add_argument('--scale', type=float, default=1)
parser.add_argument('--theme', default='Clínico')
parser.add_argument('--seconds', type=int, default=0)
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix='tresvizo-simple-') as directory:
    app = Application(directory)
    uid = app.auth.create_user('Dra. Elena Martínez', 'elena', 'Sintetica-local-12345')
    app.auth.login(uid, 'Sintetica-local-12345')
    app.profiles.save(uid, {'avatar': 'zorro'})
    app.identity.save({'clinic_name': 'Clínica de demostración · datos ficticios'})
    patient = app.clinic.save('patients', {'name': 'Ana Lucía Ramírez', 'birth_date': '1980-06-15', 'sex': 'Femenino',
        'allergy_status': 'Alergias registradas', 'allergy_records': [{'substance': 'Alergia sintética de demostración'}]})
    app.clinic.save('patients', {'name': 'Ana Lucía Ramírez', 'birth_date': '1994-11-20', 'allergy_status': 'No interrogado'})
    today = date.today().isoformat()+'T10:00:00'
    empty = app.clinic.save('encounters', {'patient_id': patient['id'], 'status': 'Borrador', 'attended_at': today})
    complete = app.clinic.save('encounters', {'patient_id': patient['id'], 'status': 'Borrador', 'attended_at': today,
        'reason': 'Consulta de demostración', 'subjective': 'Relato ficticio del paciente para revisar la captura.',
        'objective': 'Exploración de ejemplo escrita por el médico.', 'diagnoses': [{'name': 'Impresión de demostración'}],
        'assessment_notes': 'Valoración narrativa de prueba.', 'plan': 'Indicaciones ficticias para comprobar el guardado.',
        'vitals': [{'at': today, 'values': {'temperature': {'value': '36.7', 'unit': '°C'}, 'weight': {'value': '70', 'unit': 'kg'}}}],
        'prescriptions': [{'name': 'Producto de demostración', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency_kind': 'Cada N horas', 'frequency': '12'}]})
    image = Path(directory)/'Documento de prueba.png'
    Image.new('RGB', (160, 100), 'white').save(image)
    app.attachments.add(image, patient['id'], complete['id'])
    legacy = app.clinic.save('encounters', {'patient_id': patient['id'], 'status': 'Finalizada', 'attended_at': '2026-08-20T09:00:00',
        'reason': 'Atención anterior de demostración', 'subjective': 'Nota antigua íntegra, conservada sin redistribuir su contenido.',
        'assessment': 'Valoración narrativa anterior', 'plan': 'Indicaciones originales de ejemplo',
        'medications': 'Texto de tratamiento heredado, sin interpretar dosis.'})
    app.ui_scale = args.scale
    app.tk.call('tk', 'scaling', args.scale*96/72)
    app.shell()
    app.geometry(f'{args.width}x{args.height}')
    registration = [None]
    def show(view):
        if view == 'patients': app.show('Pacientes')
        elif view == 'options': app.show('Más opciones')
        elif view == 'registration':
            if registration[0] and registration[0].winfo_exists():
                app.show('alta:'+registration[0].draft_id)
            else:
                registration[0] = app.patient_editor(attend=True)
        elif view == 'legacy': app.open_encounter(legacy['id'])
        else: app.open_encounter(complete['id'] if view == 'complete' else empty['id'])
        app.title('TresVizo Med · revisión simple sintética · '+view)
        app.status.set('Demostración · F1 Pacientes · F2 Alta · F3 SOAP · F4 Opciones · F5 Historial · F6 Consulta completa')
    for key, view in enumerate(['patients', 'registration', 'soap', 'options', 'legacy', 'complete'], 1):
        app.bind('<F'+str(key)+'>', lambda e, view=view: show(view))
    show(args.view)
    app.theme.apply(app.appearance.list()[args.theme]['tokens'])
    if args.seconds:
        app.after(args.seconds*1000, app.close)
    app.mainloop()
