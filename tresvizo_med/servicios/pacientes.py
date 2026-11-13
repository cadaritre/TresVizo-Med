"""Pacientes: búsqueda, alta y edición con control de revisión, archivo y restauración.

Porta ``Clinic.search_patients``, ``Clinic.save('patients')`` y ``Clinic.archive`` del escritorio.
"""
import uuid
from datetime import date

from django.db import connections, router
from django.utils import timezone

from ..db import atomico
from ..dominio.errores import DataError
from ..dominio.texto import normalized
from ..formato import paciente_a_dict, paciente_columnas, paciente_resumen, texto_busqueda
from ..models import Documento, Paciente
from .errores import NoEncontrado, VersionConflict

MODOS = ('Activos', 'Archivados', 'Todos')


def siguiente_folio():
    """Folio ``RC-000001`` de la secuencia de PostgreSQL (arranca después del mayor folio importado)."""
    with connections[router.db_for_write(Paciente)].cursor() as cursor:
        cursor.execute("SELECT nextval('med_folio_seq')")
        return f'RC-{cursor.fetchone()[0]:06d}'


def reiniciar_secuencia(minimo):
    """Fija la secuencia para que el siguiente folio sea mayor que ``minimo`` (la usa la importación)."""
    with connections[router.db_for_write(Paciente)].cursor() as cursor:
        cursor.execute("SELECT last_value, is_called FROM med_folio_seq")
        ultimo, usada = cursor.fetchone()
        if minimo > (ultimo if usada else 0):
            cursor.execute("SELECT setval('med_folio_seq', %s, true)", [minimo])


def obtener(actor, identificador):
    try:
        return Paciente.objects.get(pk=identificador)
    except (Paciente.DoesNotExist, ValueError, DataError):
        raise NoEncontrado('No existe el paciente.') from None


def buscar(actor, consulta='', modo='Activos', pagina=0, tamano=100):
    """Busca por nombre, nombre preferido, folio y teléfono, sin acentos ni mayúsculas.

    Devuelve ``(filas, total, página_actual)``; la página se ajusta al rango real.
    """
    if modo not in MODOS:
        raise DataError('Modo de búsqueda no admitido.')
    filas = Paciente.objects.all()
    for termino in normalized(consulta).split():
        filas = filas.filter(busqueda__contains=termino)
    if modo != 'Todos':
        filas = filas.filter(archivado=(modo == 'Archivados'))
    total = filas.count()
    actual = min(max(0, pagina), max(0, (total-1)//tamano))
    pagina_filas = filas.order_by('nombre_norm', 'folio')[actual*tamano:(actual+1)*tamano]
    return [paciente_resumen(p) for p in pagina_filas], total, actual


def validar(datos):
    if not datos.get('name', '').strip():
        raise DataError('El nombre del paciente es obligatorio.')
    if datos.get('birth_date'):
        try:
            if date.fromisoformat(datos['birth_date']) > timezone.localdate():
                raise ValueError()
        except ValueError as exc:
            raise DataError('Nacimiento inválido. Usa AAAA-MM-DD y una fecha no futura.') from exc
    if datos.get('birth_date') and datos.get('approx_age', {}).get('value') not in ('', None):
        raise DataError('Elige fecha de nacimiento o edad aproximada.')
    if datos.get('allergy_records') and datos.get('allergy_status') == 'Sin alergias conocidas':
        raise DataError('Revisa las alergias registradas antes de declarar ausencia de alergias.')


def guardar(actor, datos, revision=None):
    """Alta (sin ``id`` o con un ``id`` nuevo) o edición con control optimista de revisión."""
    datos = dict(datos)
    validar(datos)
    ahora = timezone.now()
    try:
        identificador = uuid.UUID(str(datos.get('id') or uuid.uuid4()))
    except ValueError as exc:
        raise DataError('Identificador de paciente inválido.') from exc
    with atomico():
        previo = Paciente.objects.select_for_update().filter(pk=identificador).first()
        if previo and previo.revision != revision:
            raise VersionConflict(paciente_a_dict(previo))
        foto = None
        if datos.get('photo_attachment_id'):
            try:
                foto = uuid.UUID(str(datos['photo_attachment_id']))
            except ValueError as exc:
                raise DataError('Foto del paciente inválida.') from exc
            documento = Documento.objects.filter(pk=foto).first()
            if (not documento or documento.paciente_id != identificador or documento.borrador_id
                    or not documento.mime.startswith('image/')):
                raise DataError('La foto debe ser una imagen incorporada al expediente de este paciente.')
        columnas = paciente_columnas(datos)
        folio = previo.folio if previo else siguiente_folio()
        datos_completos = {**datos, 'file_number': folio}
        paciente = previo or Paciente(id=identificador, created_at=ahora, created_by=actor.cuenta_id)
        paciente.nombre = columnas['nombre']
        paciente.nombre_norm = normalized(columnas['nombre'])
        paciente.nacimiento, paciente.edad_aproximada = columnas['nacimiento'], columnas['edad_aproximada']
        paciente.sexo, paciente.telefono, paciente.datos = columnas['sexo'], columnas['telefono'], columnas['datos']
        paciente.folio, paciente.foto_documento = folio, foto
        paciente.busqueda = texto_busqueda(datos_completos)
        paciente.revision = previo.revision+1 if previo else 1
        paciente.updated_at, paciente.updated_by = ahora, actor.cuenta_id
        if not previo:
            paciente.archivado = False
        paciente.save()
        return paciente


def archivar(actor, identificador, motivo, restaurar=False, revision=None):
    """Archiva o restaura un paciente (administrador). Nada clínico se borra."""
    actor.exigir_admin()
    if not motivo.strip():
        raise DataError('Indica el motivo de la operación.')
    with atomico():
        paciente = Paciente.objects.select_for_update().filter(pk=identificador).first()
        if not paciente:
            raise DataError('No existe el registro.')
        if revision is not None and paciente.revision != revision:
            raise DataError('El registro cambió. Actualiza antes de continuar.')
        ahora = timezone.now()
        paciente.archivado = not restaurar
        paciente.revision += 1
        paciente.updated_at, paciente.updated_by = ahora, actor.cuenta_id
        paciente.lifecycle = [*paciente.lifecycle, {'actor': actor.cuenta_id, 'at': ahora.isoformat(timespec='seconds'),
                                                    'reason': motivo, 'action': 'restaurar' if restaurar else 'archivar'}]
        paciente.save()
        return paciente


def posibles_duplicados(datos, excluir=None):
    """Pacientes (activos o archivados) con el mismo nombre o teléfono normalizados. Aceptar significa «persona
    distinta»: nunca se fusionan."""
    nombre, telefono = normalized(datos.get('name', '')), normalized(datos.get('phone', ''))
    filas = Paciente.objects.none()
    if nombre:
        filas = filas | Paciente.objects.filter(nombre_norm=nombre)
    if telefono:
        filas = filas | Paciente.objects.filter(telefono__isnull=False).exclude(telefono='').filter(busqueda__contains=telefono)
    if excluir:
        filas = filas.exclude(pk=excluir)
    return [p for p in filas.order_by('nombre_norm', 'folio')[:5]
            if p.nombre_norm == nombre or (telefono and normalized(p.telefono) == telefono)]
