"""Compila, verifica y publica artefactos locales de una versión de TresVizo Med."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version as dependency_version
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.version import VERSION, version_tuple
from scripts.generate_msi import build_msi


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def write_version_resource():
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo,
                                                    StringTable, StringStruct, VarFileInfo, VarStruct)
    numbers = (*version_tuple(), 0)
    info = VSVersionInfo(ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3f,
        flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), kids=[
        StringFileInfo([StringTable('0c0a04b0', [StringStruct(k, v) for k, v in {
            'CompanyName': 'TresVizo', 'FileDescription': 'TresVizo Med', 'FileVersion': VERSION,
            'InternalName': 'TresVizo-Med', 'OriginalFilename': 'TresVizo-Med.exe',
            'ProductName': 'TresVizo Med', 'ProductVersion': VERSION}.items()])]),
        VarFileInfo([VarStruct('Translation', [3082, 1200])])])
    (ROOT/'build').mkdir(exist_ok=True)
    (ROOT/'build/windows-version.txt').write_text(str(info), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true', help='Solo tras verificar la misma revisión de código.')
    parser.add_argument('--replace-unpublished', action='store_true', help='Reemplazar artefactos locales que todavía no se han distribuido.')
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 13):
        parser.error('Compila en Windows usando Python 3.13 de la arquitectura de destino.')
    wix_version = subprocess.check_output(['wix', '--version'], text=True).strip()
    if not wix_version.startswith('4.0.6+') and wix_version != '4.0.6':
        parser.error('Usa WiX 4.0.6 para reproducir esta línea de instaladores.')
    arch = 'x64' if struct.calcsize('P') == 8 else 'x86'
    output = ROOT/'dist'/'installer'/f'TresVizo-Med-{VERSION}-{arch}.msi'
    if output.exists() and not args.replace_unpublished:
        parser.error('Ya existe este MSI. Incrementa app/version.py; no reemplaces una versión distribuida.')
    if not args.skip_tests:
        run(sys.executable, '-m', 'pytest', '-q')
    write_version_resource()
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', ROOT/'dist'/arch,
        '--workpath', ROOT/'build'/arch, ROOT/'TresVizo-Med.spec')
    payload = ROOT/'dist'/arch/'TresVizo-Med'
    run(sys.executable, ROOT/'scripts/licencias.py', payload)
    dependencies = {name: dependency_version(name) for name in
        ('Pillow', 'tkinterdnd2', 'reportlab', 'pypdfium2', 'pyinstaller', 'pyinstaller-hooks-contrib', 'charset-normalizer')}
    sources = sorted([ROOT/'main.py', ROOT/'TresVizo-Med.spec', ROOT/'requirements.txt',
                      * (ROOT/'app').rglob('*.py'), * (ROOT/'scripts').rglob('*.py'),
                      * (ROOT/'scripts/installer').glob('*.wxs'), * (ROOT/'assets').rglob('*')])
    source_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.is_file()}
    build_info = {'version': VERSION, 'architecture': arch, 'python': platform.python_version(),
        'wix': wix_version, 'built_at': datetime.now(timezone.utc).isoformat(), 'dependencies': dependencies, 'sources': source_hashes}
    (payload/'build-info.json').write_text(json.dumps(build_info, indent=2), encoding='utf-8')
    report = ROOT/'artifacts'/f'package-check-{arch}.json'
    report.parent.mkdir(exist_ok=True)
    run(payload/'TresVizo-Med.exe', '--self-test', report)
    checked = json.loads(report.read_text(encoding='utf-8'))
    if not checked['ok'] or checked['version'] != VERSION or checked['bits'] != struct.calcsize('P')*8:
        raise RuntimeError('La verificación del ejecutable no corresponde con esta versión.')
    manifest = build_msi(payload, output, arch)
    manifest.update(build_info=build_info, package_check=checked, signed=False)
    output.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    output.with_suffix('.sha256').write_text(manifest['sha256']+'  '+output.name+'\n', encoding='ascii')
    print('Instalador verificado: '+str(output))


if __name__ == '__main__':
    main()
