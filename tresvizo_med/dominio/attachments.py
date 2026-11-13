"""Reglas puras de documentos: validación del contenido real, identificadores de operación y miniaturas.

La administración de archivos del escritorio (almacén, colas, adendas por documento) pasa a los servicios de
Django; aquí quedan las reglas que no dependen de dónde se guarde el archivo.
"""
import uuid
import zipfile
from copy import deepcopy
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

from .errores import DataError

CATEGORIES = ['Fotografía clínica', 'Laboratorio', 'Estudio', 'Referencia', 'Consentimiento', 'Otro documento']
MAX_BYTES = 50*1024*1024
MAX_PIXELS = 40_000_000
UPDATABLE = ('title', 'category', 'notes', 'document_date', 'archived')


def validate(path):
    """Valida el contenido real del archivo y devuelve su tipo MIME; cualquier anomalía es ``DataError``."""
    try:
        return _validate(path)
    except DataError:
        raise
    except Exception as exc:  # contenido ilegible: imagen truncada, PDF roto, ZIP inválido
        raise DataError('El archivo está dañado o no coincide con su formato.') from exc


def _validate(path):
    path = Path(path)
    size = path.stat().st_size
    if size <= 0 or size > MAX_BYTES:
        raise DataError('El archivo debe tener contenido y no superar 50 MiB.')
    suffix = path.suffix.lower()
    if suffix in ('.jpg', '.jpeg', '.png'):
        with Image.open(path) as image:
            if image.format not in ('PNG', 'JPEG') or image.width*image.height > MAX_PIXELS:
                raise DataError('Imagen incompatible o mayor de 40 megapíxeles.')
            if (suffix == '.png') != (image.format == 'PNG'):
                raise DataError('El contenido de la imagen no coincide con su extensión.')
            image.verify()
        return 'image/png' if suffix == '.png' else 'image/jpeg'
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise DataError('El PDF está protegido. Incorpora una copia accesible.')
        if not len(reader.pages):
            raise DataError('El PDF no tiene páginas.')
        return 'application/pdf'
    if suffix == '.docx':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names or any('vbaProject' in n for n in names):
                raise DataError('El archivo no es un DOCX admitido.')
            if sum(i.file_size for i in archive.infolist()) > 200*1024*1024:
                raise DataError('El contenido descomprimido del DOCX supera el límite.')
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    raise DataError('Formatos admitidos: JPEG, PNG, PDF y DOCX.')



def operation_identifier(actor_id, target, operation_id):
    """Identificador determinista: reintentar la misma operación no duplica el documento."""
    try:
        namespace = uuid.UUID(str(actor_id))
    except ValueError:  # cuentas del portal: identificador entero
        namespace = uuid.uuid5(uuid.NAMESPACE_OID, 'tresvizo-med:cuenta:'+str(actor_id))
    return str(uuid.uuid5(namespace, '|'.join(str(target.get(k) or '') for k in ('patient_id', 'encounter_id', 'draft_id'))+'|'+operation_id))


def clean_update(values):
    """Filtra y valida los campos editables de un documento."""
    values = {key: deepcopy(value) for key, value in values.items() if key in UPDATABLE}
    if 'title' in values and not values['title'].strip():
        raise DataError('El título del documento es obligatorio.')
    if values.get('document_date'):
        try:
            date.fromisoformat(values['document_date'])
        except ValueError as exc:
            raise DataError('Revisa la fecha del documento.') from exc
    return values


def make_thumbnail(source, destination, size=160):
    """Miniatura PNG con la orientación EXIF aplicada. Devuelve ``destination``."""
    destination = Path(destination)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((size, size))
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
    return destination
