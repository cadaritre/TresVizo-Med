"""Escenarios sintéticos aislados para revisar recorridos y estados de recuperación."""
import argparse
from datetime import date
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app.main_window import Application

parser = argparse.ArgumentParser()
parser.add_argument('--view', choices=['home', 'patients', 'options', 'consultation', 'import', 'settings', 'conflict', 'documents', 'login'], default='home')
parser.add_argument('--front', action='store_true', help='Mantener la demostración al frente para capturas sin otras ventanas superpuestas.')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='tresvizo-hardening-visual-') as folder:
    app = Application(folder)
    actor = app.auth.create_user('Dra. Elena Martínez', 'elena', 'Sintetica-local-12345')
    app.auth.login(actor, 'Sintetica-local-12345')
    app.auth.create_user('Dr. Daniel Pérez', 'daniel', 'Sintetica-local-67890')
    app.identity.save({'clinic_name': 'Clínica de demostración · datos ficticios'})
    app.profiles.save(actor, {'avatar': 'zorro'})
    today = date.today().isoformat()
    patient = app.clinic.save('patients', {'name': 'Ana Lucía Ramírez', 'birth_date': '1980-06-15', 'allergy_status': 'Alergias registradas',
        'allergy_records': [{'substance': 'Alergia sintética para revisar el aviso'}]})
    other = app.clinic.save('patients', {'name': 'Ana Lucía Ramírez', 'birth_date': '1994-11-20', 'allergy_status': 'No interrogado'})
    appointment = app.clinic.save('appointments', {'patient_id': patient['id'], 'due_at': today+'T10:15:23-06:00', 'reason': 'Control de demostración', 'status': 'Confirmada'})
    app.clinic.save('appointments', {'patient_id': other['id'], 'due_at': today+'T11:30:00-06:00', 'reason': 'Primera visita de prueba', 'status': 'Programada'})
    visit = app.clinic.attend(appointment['id'])
    visit = app.clinic.save('encounters', {**visit, 'subjective': 'Nota de demostración. El texto, el cursor y la selección se conservan al cambiar de vista.',
        'assessment': 'Diagnóstico de prueba', 'diagnoses': [{'name': 'Diagnóstico de prueba'}], 'plan': 'Plan ficticio para comprobar guardado y finalización.',
        'vitals': [{'id': 'toma-sintetica', 'at': today+'T10:20:23-06:00', 'values': {'temperature': {'value': '98.6', 'unit': '°F'}, 'weight': {'value': '70', 'unit': 'kg'}, 'height': {'value': '175', 'unit': 'cm'}}}],
        'followup': {'date': today, 'reason': 'Tarea sin hora confirmada'}}, visit['revision'])
    source = Path(folder)/'Documento de prueba.png'
    Image.new('RGB', (160, 110), 'white').save(source)
    app.attachments.add(source, patient['id'], visit['id'], category='Estudio')
    app.shell()
    app.geometry('1366x768')
    app.title('TresVizo Med · revisión sintética · '+args.view+(' · primer plano' if args.front else ''))
    app.update_idletasks()
    if args.view in ('patients', 'options', 'settings'):
        app.show({'patients': 'Pacientes', 'options': 'Más opciones', 'settings': 'Configuración'}[args.view])
    elif args.view in ('consultation', 'conflict', 'documents'):
        editor = app.encounter_editor(patient, visit)
        if args.view == 'conflict':
            app.clinic.save('encounters', {**visit, 'plan': 'Plan guardado desde otra edición sintética.'}, visit['revision'])
            editor.texts['plan'].insert('end', ' Cambio local aún sin guardar.')
            editor.save_feedback()
            editor.resolve_conflict()
        if args.view == 'documents':
            editor.open_tool('documents')
    elif args.view == 'import':
        from app.import_ui import ImportWindow
        source = Path(folder)/'pacientes.csv'
        source.write_text('name,birth_date,email\nPersona de prueba,1985-01-15,\nAna Lucía Ramírez,,\nRegistro incorrecto,fecha incompleta,correo\n', encoding='utf-8-sig')
        app.show('Exportar y respaldar')
        window = ImportWindow(app)
        with patch('app.import_ui.filedialog.askopenfilename', return_value=str(source)):
            window.choose()
        window.inspect()
        window.tree.selection_set('4')
        window.details()
    elif args.view == 'login':
        app.auth.logout()
        app.login_screen()
    if args.front:
        import tkinter as tk
        app.attributes('-topmost', True)
        for window in app.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.attributes('-topmost', True)
    app.mainloop()
