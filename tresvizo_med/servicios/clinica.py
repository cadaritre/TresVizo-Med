"""Identidad de la clínica y perfil profesional."""
import io
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageOps

from ..db import atomico
from ..dominio import themes
from ..dominio.errores import DataError
from ..models import Clinica, Profesional
from .errores import VersionConflict


def identidad():
    return Clinica.obtener().valores()


def guardar_identidad(actor, valores, revision=None):
    """Identidad que usan los documentos. Solo ``med.admin``; el primer guardado marca la clínica como configurada."""
    actor.exigir_admin()
    with atomico():
        fila = Clinica.objects.select_for_update().get(pk=Clinica.obtener().pk)
        if revision is not None and fila.revision != revision:
            raise VersionConflict({'revision': fila.revision, 'identidad': fila.valores()})
        datos = {**fila.valores(), **valores}
        themes.validate_identity(datos)
        fila.identidad, fila.configurada = datos, True
        fila.revision += 1
        fila.updated_at, fila.updated_by = timezone.now(), actor.cuenta_id
        fila.save()
        return fila


def guardar_perfil(actor, cuenta_id, **valores):
    """Perfil profesional. Cada persona edita el suyo; ``med.admin`` edita cualquiera."""
    if cuenta_id != actor.cuenta_id:
        actor.exigir_admin()
    permitidos = {'nombre_visible', 'cedula', 'especialidad', 'avatar', 'reducir_movimiento', 'activo'}
    if set(valores) - permitidos:
        raise DataError('Campo de perfil no admitido.')
    if 'activo' in valores:
        actor.exigir_admin()
    for clave in ('nombre_visible', 'cedula', 'especialidad'):
        if len(str(valores.get(clave, ''))) > 120:
            raise DataError('Máximo 120 caracteres.')
    perfil = Profesional.para(cuenta_id)
    for clave, valor in valores.items():
        setattr(perfil, clave, valor)
    perfil.save()
    return perfil


AVATARES = sorted(p.stem for p in (Path(__file__).resolve().parents[1]/'static'/'med'/'img'/'avatares').glob('*.png'))
LIMITE_LOGO = 10_000_000
LIMITE_FOTO = 8_000_000


def _abrir_imagen(contenido, limite, formatos, mensaje):
    if len(contenido) > limite:
        raise DataError(mensaje)
    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.load()
    except Exception as exc:
        raise DataError('El archivo no es una imagen válida.') from exc
    if imagen.format not in formatos or imagen.width*imagen.height > 20_000_000:
        raise DataError('Elige PNG o JPEG de hasta 20 megapíxeles.' if 'ICO' not in formatos else 'Elige PNG, JPEG o ICO de hasta 20 megapíxeles.')
    return ImageOps.exif_transpose(imagen)


def guardar_logo(actor, contenido):
    """Logo de la clínica para los documentos: se valida y normaliza una copia (nunca se referencia el archivo externo)."""
    actor.exigir_admin()
    imagen = _abrir_imagen(contenido, LIMITE_LOGO, ('PNG', 'JPEG', 'ICO'), 'El logo de la clínica debe ser menor de 10 MB.').convert('RGBA')
    imagen.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    carpeta = Path(settings.TV_MED_ARCHIVOS)/'clinica'
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f'logo-{uuid.uuid4()}'
    imagen.save(carpeta/(nombre+'.png'))
    mosaico = Image.new('RGBA', (256, 256))
    chico = imagen.copy()
    chico.thumbnail((240, 240), Image.Resampling.LANCZOS)
    mosaico.alpha_composite(chico, ((256-chico.width)//2, (256-chico.height)//2))
    mosaico.save(carpeta/(nombre+'.ico'), sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    from ..db import atomico
    with atomico():
        fila = Clinica.objects.select_for_update().get(pk=Clinica.obtener().pk)
        for ruta in (fila.logo_ruta, fila.icono_ruta):
            if ruta:
                (Path(settings.TV_MED_ARCHIVOS)/ruta).unlink(missing_ok=True)
        fila.logo_ruta, fila.icono_ruta = f'clinica/{nombre}.png', f'clinica/{nombre}.ico'
        fila.revision += 1
        fila.updated_at, fila.updated_by = timezone.now(), actor.cuenta_id
        fila.save()
    return fila


def quitar_logo(actor):
    actor.exigir_admin()
    fila = Clinica.obtener()
    for ruta in (fila.logo_ruta, fila.icono_ruta):
        if ruta:
            (Path(settings.TV_MED_ARCHIVOS)/ruta).unlink(missing_ok=True)
    fila.logo_ruta = fila.icono_ruta = ''
    fila.save(update_fields=['logo_ruta', 'icono_ruta'])
    return fila


def elegir_avatar(actor, cuenta_id, avatar):
    """``avatar``: un nombre de fábrica, ``initials`` o ``photo`` (si ya hay foto)."""
    if cuenta_id != actor.cuenta_id:
        actor.exigir_admin()
    perfil = Profesional.para(cuenta_id)
    if avatar == 'photo' and not perfil.foto_ruta:
        raise DataError('Todavía no hay foto de perfil.')
    if avatar not in (*AVATARES, 'initials', 'photo'):
        raise DataError('Avatar desconocido.')
    perfil.avatar = avatar
    perfil.save(update_fields=['avatar'])
    return perfil


def guardar_foto_perfil(actor, cuenta_id, contenido):
    """Foto de perfil: el recorte ya viene hecho del navegador; el servidor valida la imagen, la centra, la reduce a
    256×256 y la guarda como PNG."""
    if cuenta_id != actor.cuenta_id:
        actor.exigir_admin()
    imagen = _abrir_imagen(contenido, LIMITE_FOTO, ('PNG', 'JPEG'), 'La foto debe pesar menos de 8 MB.').convert('RGB')
    imagen = ImageOps.fit(imagen, (256, 256), Image.Resampling.LANCZOS)
    carpeta = Path(settings.TV_MED_ARCHIVOS)/'perfiles'
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f'perfiles/{uuid.uuid4()}.png'
    imagen.save(Path(settings.TV_MED_ARCHIVOS)/nombre)
    perfil = Profesional.para(cuenta_id)
    anterior = perfil.foto_ruta
    perfil.foto_ruta, perfil.avatar = nombre, 'photo'
    perfil.save(update_fields=['foto_ruta', 'avatar'])
    if anterior:
        (Path(settings.TV_MED_ARCHIVOS)/anterior).unlink(missing_ok=True)
    return perfil
