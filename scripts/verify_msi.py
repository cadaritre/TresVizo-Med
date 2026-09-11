"""Instalación y actualización reales en una familia MSI y registro de inicio aislados."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import Store
from app.care import migrate
from app.services import Auth, Clinic, now
from app.windows_startup import Registry, WindowsStartup, REGISTRY_KEY, RUN_NAME
from scripts.generate_msi import build_msi, UPGRADE_CODE, guid


def table(path, sql):
    api = ctypes.WinDLL('msi')
    api.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
    api.MsiDatabaseOpenViewW.argtypes = [wintypes.UINT, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
    api.MsiViewExecute.argtypes = [wintypes.UINT, wintypes.UINT]
    api.MsiViewFetch.argtypes = [wintypes.UINT, ctypes.POINTER(wintypes.UINT)]
    api.MsiRecordGetStringW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    database, view = wintypes.UINT(), wintypes.UINT()
    def check(code):
        if code:
            raise OSError(code, 'No se pudo inspeccionar la base MSI.')
    check(api.MsiOpenDatabaseW(str(path), None, ctypes.byref(database)))
    try:
        check(api.MsiDatabaseOpenViewW(database, sql, ctypes.byref(view)))
        try:
            check(api.MsiViewExecute(view, 0))
            result = []
            while True:
                record = wintypes.UINT()
                code = api.MsiViewFetch(view, ctypes.byref(record))
                if code == 259:
                    return result
                check(code)
                try:
                    row = []
                    for column in range(1, api.MsiRecordGetFieldCount(record)+1):
                        size = wintypes.DWORD(32768)
                        buffer = ctypes.create_unicode_buffer(size.value)
                        check(api.MsiRecordGetStringW(record, column, buffer, ctypes.byref(size)))
                        row.append(buffer.value)
                    result.append(row)
                finally:
                    api.MsiCloseHandle(record)
        finally:
            api.MsiCloseHandle(view)
    finally:
        api.MsiCloseHandle(database)


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file() and p.name != '.instance.lock'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--arch', choices=['x64', 'x86'], default='x64')
    args = parser.parse_args()
    name = uuid.uuid4().hex[:10]
    folder = ROOT/'artifacts'/('msi-validation-'+name)
    folder.mkdir(parents=True)
    report = {'family': name, 'checks': [], 'ok': False}
    current_product = None
    family = uuid.uuid5(UPGRADE_CODE, 'test/'+name)
    def record(label):
        report['checks'].append(label)
        print(label, flush=True)
    def invoke(mode, package, label, *extra, expected=(0,)):
        log = folder/(label+'.log')
        # msiexec exige comillas en el valor, no alrededor de PROPIEDAD=valor.
        command = f'msiexec.exe {mode} "{package}" /qn /norestart /L*V "{log}"'
        for setting in extra:
            key, value = setting.split('=', 1)
            if not key.isidentifier() or '"' in value:
                raise ValueError('Propiedad de prueba inválida.')
            command += f' {key}="{value}"'
        completed = subprocess.run(command, timeout=180)
        if completed.returncode not in expected:
            raise RuntimeError(f'{label}: Windows Installer devolvió {completed.returncode}. Log: {log}')
        record(label+': '+str(completed.returncode))
    install_dir = folder/'Programa con espacios'
    data_dir = folder/'Documentos'/'RegistroClinico'
    store = Store(data_dir)
    migrate(store)
    auth = Auth(store)
    actor = auth.create_user('Doctor sintético MSI', 'msi-test', 'Sintetica-MSI-12345')
    auth.login(actor, 'Sintetica-MSI-12345')
    clinic = Clinic(store, auth)
    patient = clinic.save('patients', {'name': 'Paciente sintético MSI', 'birth_date': '1980-01-01'})
    clinic.save('encounters', {'patient_id': patient['id'], 'attended_at': now(), 'status': 'Borrador', 'subjective': 'Texto pendiente de prueba'})
    store.write('config/identity.json', {'clinic_name': 'Clínica sintética MSI'})
    store.write('config/preferencia-sintetica.json', {'theme': 'TresVizo', 'doctor': actor})
    (data_dir/'attachments').mkdir(exist_ok=True)
    (data_dir/'attachments'/'original-prueba.bin').write_bytes(b'ORIGINAL SINTETICO\x00\x01')
    before = hashes(data_dir)
    old_payload = folder/'old-payload'
    shutil.copytree(args.payload, old_payload)
    from PyInstaller.utils.win32 import versioninfo
    old_exe = old_payload/'TresVizo-Med.exe'
    resource = versioninfo.read_version_info_from_executable(str(old_exe))
    resource.ffi.fileVersionMS = resource.ffi.productVersionMS = 9
    resource.ffi.fileVersionLS = resource.ffi.productVersionLS = 0
    for item in resource.kids[0].kids[0].kids:
        if item.name in ('FileVersion', 'ProductVersion'):
            item.val = '0.9.0'
    versioninfo.write_version_info_to_executable(str(old_exe), resource)
    old_info = json.loads((old_payload/'build-info.json').read_text(encoding='utf-8'))
    old_info['version'] = '0.9.0'
    (old_payload/'build-info.json').write_text(json.dumps(old_info), encoding='utf-8')
    (old_payload/'_internal'/'archivo-retirado.txt').write_text('Componente anterior de prueba')
    registry_key = REGISTRY_KEY+'Test\\'+name
    registry = Registry(registry_key, registry_key+r'\TestRun', RUN_NAME)
    startup = WindowsStartup(registry, install_dir/'TresVizo-Med.exe', True)
    try:
        packages = {}
        for version, payload in [('0.9.0', old_payload), ('1.0.0', args.payload), ('1.0.1', args.payload), ('1.0.2', args.payload)]:
            packages[version] = folder/(version+'.msi')
            build_msi(payload, packages[version], args.arch, version, name)
        sequence = {row[0]: int(row[2]) for row in table(packages['1.0.0'], 'SELECT * FROM `InstallExecuteSequence`')}
        assert sequence['RequireClosedApp'] < sequence['InstallValidate'] < sequence['InstallInitialize'] < sequence['InstallFiles']
        assert sequence['InstallExecute'] < sequence['RemoveExistingProducts'] < sequence['InstallFinalize']
        properties = dict(table(packages['1.0.0'], 'SELECT `Property`, `Value` FROM `Property`'))
        assert properties.get('ALLUSERS', '') == ''
        assert not properties.get('ARPNOREMOVE')
        assert properties['MSIRESTARTMANAGERCONTROL'] == 'DisableShutdown'
        uninstall = table(packages['1.0.0'], "SELECT `Target`, `Arguments` FROM `Shortcut` WHERE `Shortcut` = 'UninstallShortcut'")
        assert uninstall == [['[SystemFolder]msiexec.exe', '/x [ProductCode]']]
        shortcuts = Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs'/properties['ProductName']
        uninstall_link = shortcuts/('Desinstalar '+properties['ProductName']+'.lnk')
        record('MSI por usuario; bloqueo antes de modificar; actualización dentro de transacción')
        invoke('/i', packages['0.9.0'], '01-install', 'INSTALLFOLDER='+str(install_dir))
        current_product = '{'+guid(family, args.arch+'/product/0.9.0')+'}'
        assert startup.enabled()
        assert (install_dir/'_internal'/'archivo-retirado.txt').exists()
        assert hashes(data_dir) == before
        registry.write(registry_key, 'Architecture', 'x86' if args.arch == 'x64' else 'x64')
        try:
            invoke('/i', packages['1.0.0'], '01a-architecture-guard', expected=(1603,))
            assert registry.read(registry_key, 'Version') == '0.9.0'
        finally:
            registry.write(registry_key, 'Architecture', args.arch)
        # Proceso sintético con el nombre que inspecciona WiX. No contiene interfaz
        # ni datos clínicos; solamente permite verificar que el MSI no lo termina.
        guard_dir = folder/'guard-process'
        guard_dir.mkdir()
        code = guard_dir/'Guard.cs'
        code.write_text('class Guard { static void Main() { System.Threading.Thread.Sleep(60000); } }')
        compiler = Path(os.environ['WINDIR'])/'Microsoft.NET'/'Framework64'/'v4.0.30319'/'csc.exe'
        guard_exe = guard_dir/'TresVizo-Med.exe'
        subprocess.run([str(compiler), '/nologo', '/target:winexe', '/out:'+str(guard_exe), str(code)], check=True)
        running = subprocess.Popen([str(guard_exe)])
        try:
            invoke('/i', packages['1.0.0'], '01b-running-guard', expected=(1603,))
            assert running.poll() is None
            assert registry.read(registry_key, 'Version') == '0.9.0'
            assert 'RequireClosedApp' in (folder/'01b-running-guard.log').read_text(encoding='utf-16', errors='replace')
        finally:
            running.terminate()
            running.wait(timeout=10)
        record('Proceso de prueba abierto: MSI cancela antes de actualizar y el proceso sigue vivo')
        startup.set_enabled(False)
        invoke('/i', packages['1.0.0'], '02-upgrade-off')
        current_product = '{'+guid(family, args.arch+'/product/1.0.0')+'}'
        assert registry.read(registry_key, 'Version') == '1.0.0'
        assert not startup.enabled() and registry.read(registry_key, 'AutoStart') == '0'
        assert not (install_dir/'_internal'/'archivo-retirado.txt').exists()
        assert (install_dir/'TresVizo-Med.exe').read_bytes() == (args.payload/'TresVizo-Med.exe').read_bytes()
        assert (install_dir/'build-info.json').read_bytes() == (args.payload/'build-info.json').read_bytes()
        assert hashes(data_dir) == before
        record('Actualización conserva expedientes, adjuntos, credenciales, configuración e inicio desactivado')
        invoke('/famus', packages['1.0.0'], '03-repair-off')
        assert not startup.enabled() and registry.read(registry.run_key, RUN_NAME) in (None, '')
        startup.set_enabled(True)
        invoke('/i', packages['1.0.1'], '04-upgrade-on')
        current_product = '{'+guid(family, args.arch+'/product/1.0.1')+'}'
        assert startup.enabled() and registry.read(registry_key, 'Version') == '1.0.1'
        assert uninstall_link.exists()
        import winreg
        uninstall_key = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'+current_product
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uninstall_key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            assert winreg.QueryValueEx(key, 'DisplayName')[0] == properties['ProductName']
            assert current_product.lower() in winreg.QueryValueEx(key, 'UninstallString')[0].lower()
        record('Desinstalador registrado en Aplicaciones de Windows y acceso explícito en Inicio')
        invoke('/i', packages['1.0.0'], '05-downgrade', expected=(1603,))
        assert registry.read(registry_key, 'Version') == '1.0.1'
        assert startup.enabled() and hashes(data_dir) == before
        installed_before_failure = hashes(install_dir)
        invoke('/i', packages['1.0.2'], '05b-rollback', 'TRESVIZO_TEST_FAILURE=1', expected=(1603,))
        assert registry.read(registry_key, 'Version') == '1.0.1'
        assert startup.enabled() and hashes(data_dir) == before
        assert hashes(install_dir) == installed_before_failure
        api = ctypes.WinDLL('msi')
        api.MsiQueryProductStateW.argtypes = [wintypes.LPCWSTR]
        assert api.MsiQueryProductStateW(current_product) == 5
        assert api.MsiQueryProductStateW('{'+guid(family, args.arch+'/product/1.0.2')+'}') == -1
        record('Fallo de actualización simulado: rollback restaura programa anterior e inicio automático')
        result_path = folder/'installed-package-check.json'
        completed = subprocess.run([str(install_dir/'TresVizo-Med.exe'), '--self-test', str(result_path)], timeout=45)
        assert completed.returncode == 0 and json.loads(result_path.read_text(encoding='utf-8'))['ok']
        record('Ejecutable instalado: ventana, icono, arrastrar archivos y PDF verificados')
        invoke('/x', current_product, '06-uninstall')
        assert api.MsiQueryProductStateW(current_product) == -1
        current_product = None
        assert not uninstall_link.exists()
        assert not (install_dir/'TresVizo-Med.exe').exists()
        assert registry.read(registry.run_key, RUN_NAME) is None
        assert hashes(data_dir) == before
        reopened = Store(data_dir)
        migrate(reopened)
        assert hashes(data_dir) == before
        Auth(reopened).login(actor, 'Sintetica-MSI-12345')
        assert reopened.records('patients')[0]['id'] == patient['id']
        assert reopened.records('encounters')[0]['subjective'] == 'Texto pendiente de prueba'
        record('Desinstalar conserva datos; reapertura y autenticación de prueba correctas')
        report['protected_files'] = len(before)
        report['ok'] = True
    finally:
        report['remaining_product'] = current_product
        (folder/'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Informe: '+str(folder/'result.json'), flush=True)


if __name__ == '__main__':
    main()
