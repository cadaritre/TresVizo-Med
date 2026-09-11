"""MSI por usuario: identidad estable, archivos explícitos y datos externos intactos."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.version import VERSION, version_tuple
from app.windows_startup import REGISTRY_KEY, RUN_KEY, RUN_NAME

# Identidad permanente de esta línea de producto. NO cambiar entre versiones.
UPGRADE_CODE = uuid.UUID('8e42c854-12d8-4d91-aab0-4a07d7645f63')
NS = 'http://wixtoolset.org/schemas/v4/wxs'
ET.register_namespace('', NS)


def element(parent, tag, **attributes):
    return ET.SubElement(parent, '{'+NS+'}'+tag, attributes)


def stable_id(prefix, name):
    return prefix+hashlib.sha256(name.encode()).hexdigest()[:32]


def guid(family, name):
    return str(uuid.uuid5(family, name)).upper()


def payload_xml(payload, family, arch, registry_key):
    payload = Path(payload).resolve()
    files = sorted(p for p in payload.rglob('*') if p.is_file())
    if not (payload/'TresVizo-Med.exe').is_file():
        raise ValueError('Falta el ejecutable compilado.')
    allowed_roots = {'TresVizo-Med.exe', '_internal', 'licencias', 'build-info.json'}
    if any(p.relative_to(payload).parts[0] not in allowed_roots or p.is_symlink() for p in files):
        raise ValueError('La distribución contiene archivos ajenos al paquete permitido.')
    wix = ET.Element('{'+NS+'}Wix')
    fragment = element(wix, 'Fragment')
    base = element(fragment, 'DirectoryRef', Id='INSTALLFOLDER')
    directories = {Path('.'): (base, 'INSTALLFOLDER')}
    for directory in sorted({p.relative_to(payload).parent for p in files}, key=lambda p: (len(p.parts), p.as_posix())):
        for ancestor in [*reversed(directory.parents), directory]:
            if ancestor in directories:
                continue
            parent = directories[ancestor.parent][0]
            identifier = stable_id('D', ancestor.as_posix())
            directories[ancestor] = (element(parent, 'Directory', Id=identifier, Name=ancestor.name), identifier)
    group = element(fragment, 'ComponentGroup', Id='AppFiles')
    cleaned = set()
    for path in files:
        relative = path.relative_to(payload)
        name = relative.as_posix()
        identifier = stable_id('C', name)
        component = element(group, 'Component', Id=identifier, Directory=directories[relative.parent][1],
                            Guid=guid(family, arch+'/file/'+name), Bitness='always64' if arch == 'x64' else 'always32')
        # HKCU key paths para componentes instalados en el perfil del usuario (ICE38).
        element(component, 'File', Id=stable_id('F', name), Source=str(path), KeyPath='no')
        element(component, 'RegistryValue', Root='HKCU', Key=registry_key+r'\Files', Name=identifier,
                Type='integer', Value='1', KeyPath='yes')
        for directory in (relative.parent, *relative.parent.parents):
            if directory == Path('.') or directory in cleaned:
                continue
            cleaned.add(directory)
            element(component, 'RemoveFolder', Id=stable_id('R', directory.as_posix()), Directory=directories[directory][1], On='uninstall')
    ET.indent(wix)
    return ET.tostring(wix, encoding='unicode')


def rtf(text):
    escaped = ''.join(('\\'+c if c in '\\{}' else '\\par\n' if c == '\n' else c if ord(c) < 128 else '\\u'+str(ord(c))+'?') for c in text)
    return '{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Segoe UI;}}\\f0\\fs20 '+escaped+'}'


def installer_images(work, version):
    """Componer los paneles nativos reutilizando el logo, sin modificar el asset."""
    import os
    from PIL import Image, ImageDraw, ImageFont
    fonts = Path(os.environ['WINDIR'])/'Fonts'
    panel = Image.new('RGB', (493, 312), 'white')
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, 163, 311), fill='#EDF4F8')
    draw.rectangle((0, 0, 163, 7), fill='#095388')
    with Image.open(ROOT/'assets/clinica_icono.png') as source:
        logo = source.convert('RGBA')
    logo.thumbnail((114, 114), Image.Resampling.LANCZOS)
    panel.paste(logo, ((164-logo.width)//2, 48), logo)
    draw.text((18, 179), 'TresVizo', fill='#123F67', font=ImageFont.truetype(str(fonts/'seguisb.ttf'), 27))
    draw.text((18, 218), 'Med', fill='#123F67', font=ImageFont.truetype(str(fonts/'segoeui.ttf'), 20))
    draw.text((18, 276), version, fill='#405A70', font=ImageFont.truetype(str(fonts/'segoeui.ttf'), 13))
    panel.save(work/'Dialog.bmp')
    banner = Image.new('RGB', (493, 58), 'white')
    logo.thumbnail((44, 44), Image.Resampling.LANCZOS)
    banner.paste(logo, (437, 5), logo)
    ImageDraw.Draw(banner).rectangle((0, 56, 492, 57), fill='#095388')
    banner.save(work/'Banner.bmp')


def build_msi(payload, output, arch, version=VERSION, test_family=None):
    version_tuple(version)
    if arch not in ('x86', 'x64'):
        raise ValueError('Arquitectura inválida.')
    payload, output = Path(payload).resolve(), Path(output).resolve()
    info = json.loads((payload/'build-info.json').read_text(encoding='utf-8'))
    if info['architecture'] != arch or (not test_family and (version != VERSION or info['version'] != VERSION)):
        raise ValueError('La versión o arquitectura del ejecutable no coincide con el MSI.')
    family = uuid.uuid5(UPGRADE_CODE, 'test/'+test_family) if test_family else UPGRADE_CODE
    suffix = '-Test-'+test_family if test_family else ''
    registry_key = REGISTRY_KEY+('Test\\'+test_family if test_family else '')
    run_key = registry_key+r'\TestRun' if test_family else RUN_KEY
    work = ROOT/'build'/'msi'/('test-'+test_family if test_family else arch)/version
    work.mkdir(parents=True, exist_ok=True)
    installer_images(work, version)
    output.parent.mkdir(parents=True, exist_ok=True)
    (work/'Payload.wxs').write_text(payload_xml(payload, family, arch, registry_key), encoding='utf-8')
    intro = ('TresVizo Med '+version+'\n\nSe instala para esta cuenta de Windows. Los datos clínicos y las preferencias se conservan en Documentos/RegistroClinico, incluso al desinstalar.\n\n'
             'El inicio automático queda activado en la primera instalación. Puedes cambiarlo en Configuración > General. Las actualizaciones respetan tu elección. Guarda tu trabajo y cierra la aplicación antes de continuar.\n\n')
    (work/'License.rtf').write_text(rtf(intro+(ROOT/'LICENSE').read_text(encoding='utf-8')), encoding='ascii')
    definitions = {'ProductName': 'TresVizo Med'+suffix, 'InstallName': 'TresVizo-Med'+suffix,
        'Version': version, 'Architecture': arch, 'UpgradeCode': str(family), 'ProductCode': guid(family, arch+'/product/'+version),
        'RegistryKey': registry_key, 'RunKey': run_key, 'RunName': RUN_NAME,
        'SettingsGuid': guid(family, 'settings'),
        'ShortcutsGuid': guid(family, 'shortcuts'), 'IconPath': str(ROOT/'assets/clinica.ico'),
        'LicenseRtf': str(work/'License.rtf'), 'DialogBmp': str(work/'Dialog.bmp'), 'BannerBmp': str(work/'Banner.bmp')}
    if test_family:
        definitions['TestFamily'] = test_family
    command = ['wix', 'build', str(ROOT/'scripts/installer/Product.wxs'), str(work/'Payload.wxs'),
               '-arch', arch, '-culture', 'es-es', '-ext', 'WixToolset.UI.wixext/4.0.6',
               '-ext', 'WixToolset.Util.wixext/4.0.6', '-cc', str(ROOT/'build/msi-cab-cache'),
               '-intermediatefolder', str(work/'obj'), '-out', str(output)]
    for key, value in definitions.items():
        command.extend(['-d', key+'='+value])
    subprocess.run(command, cwd=ROOT, check=True)
    return {'file': output.name, 'version': version, 'architecture': arch,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'bytes': output.stat().st_size,
            'upgrade_code': str(family), 'product_code': definitions['ProductCode']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arch', choices=['x64', 'x86'], required=True)
    parser.add_argument('--version', default=VERSION)
    parser.add_argument('--test-family', help='Familia aislada; sus registros de inicio nunca entran en Windows Run.')
    args = parser.parse_args()
    print(json.dumps(build_msi(args.payload, args.output, args.arch, args.version, args.test_family), indent=2))
