"""Consultas: borradores privados, finalización, adendas sin sobrescribir, anulación y control de revisión.

Porta ``Clinic.save('encounters')``, ``addendum``, ``archive`` y ``attend`` del escritorio. Lo que el escritorio
resolvía con ``Auth.require`` aquí lo da :class:`Actor`: escribir clínica es de ``med.medico``; anular lo hace el
responsable o ``med.admin``.
"""
import uuid
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from ..db import atomico
from ..dominio.clinical_models import validate_medications, validate_vitals
from ..dominio.errores import DataError
from ..formato import a_aware, consulta_a_dict, consulta_contenido
from ..models import Adenda, ColaDocumentos, Consulta, Paciente
from .errores import NoEncontrado, PermisoDenegado, VersionConflict

ESTADOS_GUARDABLES = ('Borrador', 'Finalizada')


def visibles(actor, incluir_archivadas=False):
    """Consultas que ``actor`` puede ver: todas salvo los borradores de otras personas."""
    filas = Consulta.objects.filter(~Q(estado=Consulta.Estado.BORRADOR) | Q(doctor_id=actor.cuenta_id))
    return filas if incluir_archivadas else filas.filter(archivada=False)


def obtener(actor, identificador):
    """Un borrador ajeno no existe para quien no es su responsable (404)."""
    try:
        consulta = Consulta.objects.get(pk=identificador)
    except (Consulta.DoesNotExist, ValueError):
        raise NoEncontrado('No existe la consulta.') from None
    if consulta.estado == Consulta.Estado.BORRADOR and consulta.doctor_id != actor.cuenta_id:
        raise NoEncontrado('No existe la consulta.')
    return consulta


def como_dict(actor, consulta):
    return consulta_a_dict(Consulta.objects.prefetch_related('adendas').get(pk=consulta.pk))


def _destino_cola(**destino):
    for clave in ('paciente', 'consulta', 'borrador'):
        if destino.get(clave):
            return f'{clave}:{destino[clave]}'
    raise DataError('Destino de documentos inválido.')


def guardar(actor, datos, revision=None):
    """Crea o actualiza un borrador, o lo finaliza. ``datos`` usa el esquema del escritorio.

    Una consulta finalizada o anulada no vuelve a cambiar de contenido; solo admite adendas.
    """
    actor.exigir_medico()
    datos = dict(datos)
    try:
        identificador = uuid.UUID(str(datos.get('id') or uuid.uuid4()))
        paciente_id = uuid.UUID(str(datos.get('patient_id', '')))
    except ValueError as exc:
        raise DataError('Selecciona un paciente válido.') from exc
    if datos.get('status') not in ESTADOS_GUARDABLES:
        raise DataError('Estado de consulta inválido.')
    final = datos['status'] == 'Finalizada'
    with atomico():
        previa = Consulta.objects.select_for_update().filter(pk=identificador).first()
        if previa and previa.revision != revision:
            raise VersionConflict(consulta_a_dict(previa))
        if previa and previa.paciente_id != paciente_id:
            raise DataError('Este registro ya está vinculado a una consulta y conserva su paciente original.')
        if previa and (previa.doctor_id != actor.cuenta_id or previa.estado != Consulta.Estado.BORRADOR):
            raise DataError('Solo el responsable puede editar su borrador. Usa una adenda para consultas finalizadas.')
        if final and not all(str(datos.get(k, '')).strip() for k in ('reason', 'assessment', 'plan')):
            raise DataError('Para finalizar completa motivo, impresión diagnóstica y plan.')
        if final:
            if datos.get('editor_state', {}).get('pending'):
                raise DataError('Resuelve las capturas sin aplicar antes de finalizar.')
            if previa:
                cola = ColaDocumentos.objects.filter(
                    profesional_id=actor.cuenta_id, destino=_destino_cola(consulta=identificador)).first()
                if cola and any(fila.get('status') != 'Guardado' for fila in cola.filas):
                    raise DataError('Hay archivos seleccionados sin incorporar. Incorpóralos o retira su selección antes de finalizar.')
        try:
            datetime.fromisoformat(datos['attended_at'])
        except (ValueError, KeyError, TypeError) as exc:
            raise DataError('Fecha de atención inválida.') from exc
        if previa and previa.archivada:
            raise DataError('Restaura el borrador antes de editarlo.')
        paciente = Paciente.objects.filter(pk=paciente_id).first()
        if not paciente:
            raise DataError('El paciente ya no existe.')
        if paciente.archivado and not previa:
            raise DataError('Reactiva el expediente antes de iniciar una atención.')
        datos['vitals'] = validate_vitals(datos.get('vitals', []))
        datos['prescriptions'] = validate_medications(datos.get('prescriptions', []), final)
        ahora = timezone.now()
        consulta = previa or Consulta(id=identificador, created_at=ahora, created_by=actor.cuenta_id,
                                      doctor_id=actor.cuenta_id, captured_by=actor.cuenta_id, archivada=False)
        consulta.paciente = paciente
        consulta.estado = datos['status']
        consulta.atendida_iso = datos['attended_at']
        consulta.atendida_en = a_aware(datos['attended_at'])
        consulta.tipo = datos.get('type', '')
        consulta.motivo, consulta.diagnostico, consulta.plan = (datos.get('reason', ''), datos.get('assessment', ''),
                                                                datos.get('plan', ''))
        consulta.contenido = consulta_contenido(datos)
        consulta.editor_state = datos.get('editor_state') or {}
        consulta.revision = previa.revision+1 if previa else 1
        consulta.updated_at, consulta.updated_by = ahora, actor.cuenta_id
        consulta.save()
        return consulta


def iniciar(actor, paciente_id, ahora=None):
    """Atender: propone el borrador activo del mismo paciente y doctor; nunca crea dos."""
    actor.exigir_medico()
    with atomico():
        paciente = Paciente.objects.select_for_update().filter(pk=paciente_id).first()
        if not paciente:
            raise NoEncontrado('No existe el paciente.')
        existente = Consulta.objects.filter(paciente=paciente, doctor_id=actor.cuenta_id, archivada=False,
                                            estado=Consulta.Estado.BORRADOR).order_by('created_at').first()
        if existente:
            return existente, False
        momento = (ahora or timezone.localtime()).isoformat(timespec='seconds')
        return guardar(actor, {'patient_id': str(paciente.id), 'status': 'Borrador', 'attended_at': momento,
                               'type': 'General'}), True


def _agregar_adenda(actor, consulta, motivo, contenido, tipo, documento_id=None):
    ahora = timezone.now()
    adenda = Adenda.objects.create(id=uuid.uuid4(), consulta=consulta, autor_id=actor.cuenta_id, momento=ahora,
                                   tipo=tipo, motivo=motivo, contenido=contenido, documento_id=documento_id)
    consulta.revision += 1
    consulta.updated_at, consulta.updated_by = ahora, actor.cuenta_id
    return adenda


def agregar_adenda(actor, identificador, motivo, contenido, documento_id=None):
    """Agrega una adenda a una consulta finalizada. No se edita ni se borra."""
    actor.exigir_medico()
    if not motivo.strip() or not contenido.strip():
        raise DataError('Escribe contenido y motivo de la adenda.')
    with atomico():
        consulta = Consulta.objects.select_for_update().filter(pk=identificador).first()
        if not consulta or consulta.estado != Consulta.Estado.FINALIZADA:
            raise DataError('Solo se pueden agregar adendas a consultas finalizadas.')
        adenda = _agregar_adenda(actor, consulta, motivo, contenido, Adenda.Tipo.ADENDA, documento_id)
        consulta.save(update_fields=['revision', 'updated_at', 'updated_by'])
        return adenda


def _puede_anular(actor, consulta):
    if consulta.doctor_id == actor.cuenta_id and actor.es_medico:
        return True
    if not actor.es_admin:
        raise PermisoDenegado('Solo el responsable o el administrador pueden anular o restaurar esta consulta.')
    return True


def anular(actor, identificador, motivo):
    """Finalizada → Anulada con adenda automática. Excluida de las estadísticas."""
    if not motivo.strip():
        raise DataError('Indica el motivo de la operación.')
    with atomico():
        consulta = Consulta.objects.select_for_update().filter(pk=identificador).first()
        if not consulta:
            raise DataError('No existe el registro.')
        if consulta.estado != Consulta.Estado.FINALIZADA:
            raise DataError('Solo se pueden anular consultas finalizadas.')
        _puede_anular(actor, consulta)
        consulta.estado = Consulta.Estado.ANULADA
        _agregar_adenda(actor, consulta, motivo, 'Consulta anulada: '+motivo, Adenda.Tipo.ANULACION)
        consulta.save(update_fields=['estado', 'revision', 'updated_at', 'updated_by'])
        return consulta


def restaurar(actor, identificador, motivo):
    """Anulada → Finalizada con adenda automática."""
    if not motivo.strip():
        raise DataError('Indica el motivo de la operación.')
    with atomico():
        consulta = Consulta.objects.select_for_update().filter(pk=identificador).first()
        if not consulta:
            raise DataError('No existe el registro.')
        if consulta.estado != Consulta.Estado.ANULADA:
            raise DataError('Solo se pueden restaurar consultas anuladas.')
        _puede_anular(actor, consulta)
        consulta.estado = Consulta.Estado.FINALIZADA
        _agregar_adenda(actor, consulta, motivo, 'Consulta restaurada: '+motivo, Adenda.Tipo.RESTAURACION)
        consulta.save(update_fields=['estado', 'revision', 'updated_at', 'updated_by'])
        return consulta


def papelera(actor, identificador, motivo, restaurar_borrador=False, revision=None):
    """Retira o recupera un borrador propio (papelera privada; sin vaciado definitivo)."""
    actor.exigir_medico()
    if not motivo.strip():
        raise DataError('Indica el motivo de la operación.')
    with atomico():
        consulta = Consulta.objects.select_for_update().filter(pk=identificador).first()
        if not consulta:
            raise DataError('No existe el registro.')
        if revision is not None and consulta.revision != revision:
            raise DataError('El registro cambió. Actualiza antes de continuar.')
        if consulta.estado != Consulta.Estado.BORRADOR or consulta.doctor_id != actor.cuenta_id:
            raise DataError('Solo puedes retirar o restaurar tus propios borradores.')
        ahora = timezone.now()
        consulta.archivada = not restaurar_borrador
        consulta.revision += 1
        consulta.updated_at, consulta.updated_by = ahora, actor.cuenta_id
        consulta.lifecycle = [*consulta.lifecycle, {'actor': actor.cuenta_id, 'at': ahora.isoformat(timespec='seconds'),
                                                    'reason': motivo, 'action': 'restaurar' if restaurar_borrador else 'archivar'}]
        consulta.save()
        return consulta
