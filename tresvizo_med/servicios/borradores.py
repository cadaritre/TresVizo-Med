"""Borradores privados de alta de paciente y catálogo de medicamentos (``Care`` del escritorio)."""
import uuid
from copy import deepcopy

from django.utils import timezone

from ..db import atomico
from ..dominio import care as dominio_care
from ..dominio.errores import DataError
from ..models import BorradorAlta, CatalogoMedicamento, Consulta, Documento, Favorito
from . import pacientes
from .errores import NoEncontrado


def propios(actor):
    """Altas en borrador del usuario (los borradores de otras personas no existen para él)."""
    return BorradorAlta.objects.filter(profesional_id=actor.cuenta_id, estado=BorradorAlta.Estado.BORRADOR)


def _propio(actor, identificador):
    try:
        borrador = BorradorAlta.objects.select_for_update().get(pk=identificador, profesional_id=actor.cuenta_id)
    except (BorradorAlta.DoesNotExist, ValueError):
        raise NoEncontrado('Borrador privado no disponible.') from None
    return borrador


def guardar_borrador(actor, contenido, identificador=None, paciente_id=None, revision_origen=None):
    identificador = uuid.UUID(str(identificador)) if identificador else uuid.uuid4()
    ahora = timezone.now()
    with atomico():
        previo = BorradorAlta.objects.select_for_update().filter(pk=identificador).first()
        if previo and (previo.profesional_id != actor.cuenta_id or previo.estado != BorradorAlta.Estado.BORRADOR):
            raise NoEncontrado('Este borrador no está disponible para tu sesión.')
        borrador = previo or BorradorAlta(id=identificador, created_at=ahora, created_by=actor.cuenta_id,
                                          profesional_id=actor.cuenta_id)
        borrador.contenido = deepcopy(contenido)
        borrador.paciente = uuid.UUID(str(paciente_id)) if paciente_id else None
        borrador.revision_origen = revision_origen
        borrador.revision = previo.revision+1 if previo else 1
        borrador.updated_at, borrador.updated_by = ahora, actor.cuenta_id
        borrador.save()
        return borrador


def descartar(actor, identificador):
    with atomico():
        borrador = _propio(actor, identificador)
        borrador.estado = BorradorAlta.Estado.DESCARTADO
        borrador.updated_at, borrador.updated_by = timezone.now(), actor.cuenta_id
        borrador.save(update_fields=['estado', 'updated_at', 'updated_by'])


def registrar(actor, identificador, contenido):
    """Convierte el borrador en paciente. Idempotente: repetirlo tras un cierre inesperado devuelve el mismo paciente,
    y los documentos del borrador pasan al expediente en la misma transacción."""
    with atomico():
        borrador = _propio(actor, identificador)
        if borrador.estado == BorradorAlta.Estado.REGISTRADO:
            return pacientes.obtener(actor, borrador.paciente or borrador.objetivo)
        if borrador.estado != BorradorAlta.Estado.BORRADOR:
            raise DataError('El borrador fue descartado.')
        destino = borrador.paciente or borrador.objetivo or uuid.uuid4()
        foto = contenido.get('photo_attachment_id')
        datos = {k: v for k, v in contenido.items() if k != 'photo_attachment_id'}
        paciente = pacientes.guardar(actor, {**datos, 'id': str(destino), 'registration_draft': str(borrador.id)},
                                     borrador.revision_origen)
        movidos = list(Documento.objects.filter(borrador=borrador))
        for documento in movidos:
            documento.paciente, documento.borrador = paciente, None
            documento.updated_at = timezone.now()
            documento.save(update_fields=['paciente', 'borrador', 'updated_at'])
        if foto and any(str(d.id) == str(foto) and d.mime.startswith('image/') for d in movidos):
            paciente.foto_documento = uuid.UUID(str(foto))
            paciente.save(update_fields=['foto_documento'])
        borrador.estado, borrador.paciente, borrador.objetivo = BorradorAlta.Estado.REGISTRADO, paciente.id, paciente.id
        borrador.updated_at, borrador.updated_by = timezone.now(), actor.cuenta_id
        borrador.save(update_fields=['estado', 'paciente', 'objetivo', 'updated_at', 'updated_by'])
        return paciente


# --- Catálogo de medicamentos y favoritos ---------------------------------------------------------------------

def _fila_catalogo(medicamento, favoritos=None):
    return {'id': str(medicamento.id), 'name': medicamento.producto, 'ingredient': medicamento.principio_activo,
            'presentation': medicamento.presentacion, 'strength': medicamento.concentracion,
            'favorites': favoritos if favoritos is not None else list(medicamento.favoritos.values_list('cuenta_id', flat=True))}


def catalogo(actor, consulta=''):
    filas = [_fila_catalogo(m) for m in CatalogoMedicamento.objects.prefetch_related('favoritos').order_by('producto')]
    return dominio_care.filter_catalog(filas, consulta)


def guardar_catalogo(actor, fila, favorito=False):
    """Agrega un medicamento al catálogo de la clínica; mismo nombre y concentración reutilizan la fila."""
    todos = catalogo(actor)
    item = dominio_care.catalog_item(fila, todos, actor.cuenta_id, favorito)
    with atomico():
        medicamento, _ = CatalogoMedicamento.objects.update_or_create(
            id=uuid.UUID(item['id']), defaults={'producto': item['name'], 'principio_activo': item['ingredient'],
                                                 'presentacion': item['presentation'], 'concentracion': item['strength']})
        if favorito:
            Favorito.objects.get_or_create(medicamento=medicamento, cuenta_id=actor.cuenta_id)
    return medicamento


def alternar_favorito(actor, medicamento_id, favorito):
    medicamento = CatalogoMedicamento.objects.filter(pk=medicamento_id).first()
    if not medicamento:
        raise NoEncontrado('No existe el medicamento.')
    if favorito:
        Favorito.objects.get_or_create(medicamento=medicamento, cuenta_id=actor.cuenta_id)
    else:
        Favorito.objects.filter(medicamento=medicamento, cuenta_id=actor.cuenta_id).delete()


def evolucion(actor, paciente_id, clave):
    """Serie de una medición del paciente (consultas finalizadas, no archivadas)."""
    from ..formato import consulta_a_dict
    filas = [consulta_a_dict(c, adendas=False) for c in Consulta.objects.filter(
        paciente_id=paciente_id, estado=Consulta.Estado.FINALIZADA, archivada=False)]
    return dominio_care.evolution_points(filas, str(paciente_id), clave)
