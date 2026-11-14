"""Importación de pacientes desde CSV: lectura, mapeo, vista previa, duplicados y lote idempotente (``med.admin``)."""
import re
import uuid
from datetime import date

from django.db.models import Max
from django.utils import timezone

from ..db import atomico
from ..dominio import transfer
from ..dominio.errores import DataError
from ..dominio.texto import normalized
from ..formato import paciente_a_dict
from ..models import LoteImportacion, Paciente
from . import pacientes
from .errores import NoEncontrado


def _instantanea():
    return {'total': Paciente.objects.count(), 'ultimo': str(Paciente.objects.aggregate(m=Max('updated_at'))['m'])}


def _lote(actor, identificador, estado=None):
    actor.exigir_admin()
    try:
        lote = LoteImportacion.objects.get(pk=identificador, tipo=LoteImportacion.Tipo.CSV)
    except (LoteImportacion.DoesNotExist, ValueError):
        raise NoEncontrado('No existe el lote de importación.') from None
    if estado and lote.estado != estado:
        raise DataError('Este lote ya no está disponible para esa operación.')
    return lote


def leer(actor, contenido, nombre, delimitador=','):
    """Lee el CSV (UTF-8, hasta 10 MB y 10 000 filas) y crea un lote en ensayo con su contenido."""
    actor.exigir_admin()
    fuente = transfer.read_csv_bytes(contenido, nombre, delimitador)
    return LoteImportacion.objects.create(tipo=LoteImportacion.Tipo.CSV, actor_id=actor.cuenta_id, momento=timezone.now(),
                                          conteos={'filas': len(fuente['rows'])}, recibo={'fuente': fuente, 'nombre': nombre})


SINONIMOS = {
    'name': ('nombre', 'nombre completo', 'nombre del paciente', 'nombres', 'paciente', 'name', 'full name'),
    'birth_date': ('fecha de nacimiento', 'fecha nacimiento', 'nacimiento', 'fecha nac', 'f nacimiento', 'birth date', 'birthdate', 'birth_date'),
    'phone': ('telefono', 'tel', 'celular', 'movil', 'telefono celular', 'telefono movil', 'whatsapp', 'phone'),
    'email': ('correo', 'correo electronico', 'email', 'e mail', 'mail', 'correo e'),
}
PREFIJOS = {'phone': ('telefono', 'celular', 'movil'), 'email': ('correo', 'email'), 'birth_date': ('nacimiento', 'fecha de nacimiento')}


def _clave_columna(texto):
    return normalized(texto.replace('_', ' ').replace('-', ' ').replace('.', ' ').replace(':', ' '))


def sugerir_mapeo(columnas):
    """Columna sugerida para cada dato: nombres en español o en inglés, con o sin acentos y en cualquier capitalización
    («Teléfono», «Fecha de nacimiento», «E-mail»). Cada columna se sugiere una sola vez."""
    claves = {c: _clave_columna(c) for c in columnas}
    usadas, sugerido = set(), {}
    for campo, sinonimos in SINONIMOS.items():
        elegida = next((c for c, k in claves.items() if k in sinonimos and c not in usadas), '')
        if not elegida:
            elegida = next((c for c, k in claves.items() if c not in usadas and any(k.startswith(p) for p in PREFIJOS.get(campo, ()))), '')
        if elegida:
            usadas.add(elegida)
        sugerido[campo] = elegida
    return sugerido


def _con_fechas_iso(fuente, mapeo):
    """Las hojas de cálculo de aquí traen la fecha como día/mes/año: se convierte a AAAA-MM-DD antes de validar."""
    columna = mapeo.get('birth_date')
    if not columna:
        return fuente
    filas = []
    for fila in fuente['rows']:
        valor = (fila.get(columna) or '').strip()
        coincide = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', valor)
        if coincide:
            dia, mes, anio = (int(x) for x in coincide.groups())
            try:
                valor = date(anio, mes, dia).isoformat()
            except ValueError:
                pass
            fila = {**fila, columna: valor}
        filas.append(fila)
    return {**fuente, 'rows': filas}


def vista_previa(actor, identificador, mapeo):
    """Errores por fila y posibles duplicados con el mapeo elegido. No escribe pacientes."""
    lote = _lote(actor, identificador, LoteImportacion.Estado.ENSAYO)
    existentes = [{'name': p.nombre, 'file_number': p.folio, 'phone': p.telefono} for p in Paciente.objects.all()]
    filas = transfer.inspect_import(_con_fechas_iso(lote.recibo['fuente'], mapeo), mapeo, existentes)
    lote.recibo = {**lote.recibo, 'mapeo': mapeo, 'filas': filas, 'instantanea': _instantanea()}
    lote.conteos = {**lote.conteos, 'validas': sum(not f['errors'] for f in filas), 'con_errores': sum(bool(f['errors']) for f in filas),
                    'con_duplicados': sum(bool(f['duplicates']) for f in filas)}
    lote.save()
    return lote


def importar(actor, identificador, seleccion, duplicados_aceptados=()):
    """Confirma el lote en una sola transacción. Repetir la confirmación devuelve el mismo recibo, sin duplicar nada."""
    actor.exigir_admin()
    with atomico():
        lote = LoteImportacion.objects.select_for_update().filter(pk=identificador, tipo=LoteImportacion.Tipo.CSV).first()
        if lote is None:
            raise NoEncontrado('No existe el lote de importación.')
        if lote.estado == LoteImportacion.Estado.CONFIRMADO:
            return lote
        if 'filas' not in lote.recibo:
            raise DataError('Revisa la vista previa antes de importar.')
        if lote.recibo['instantanea'] != _instantanea():
            raise DataError('Los pacientes cambiaron desde la vista previa. Vuelve a validar el lote; no se importó ninguna fila.')
        elegidas = [f for f in lote.recibo['filas'] if f['number'] in set(seleccion)]
        if not elegidas:
            raise DataError('Selecciona al menos una fila válida.')
        creados = []
        for fila in elegidas:
            datos = dict(fila['patient'])
            if fila['errors'] or transfer.validate_import_patient(datos):
                raise DataError(f"Fila {fila['number']}: corrige los campos indicados antes de importar.")
            if fila['duplicates'] and fila['number'] not in set(duplicados_aceptados):
                raise DataError(f"Fila {fila['number']}: confirma que corresponde a una persona distinta.")
            identificador_paciente = uuid.uuid5(lote.id, str(fila['number']))
            persona = pacientes.guardar(actor, {**datos, 'id': str(identificador_paciente), 'allergy_status': 'No interrogado',
                                                'provenance': {'import_batch': str(lote.id), 'row': fila['number']}})
            creados.append(str(persona.id))
        lote.estado = LoteImportacion.Estado.CONFIRMADO
        lote.conteos = {**lote.conteos, 'importados': len(creados)}
        lote.recibo = {'actor': actor.cuenta_id, 'at': timezone.now().isoformat(timespec='seconds'), 'patients': creados,
                       'count': len(creados), 'nombre': lote.recibo.get('nombre', '')}
        lote.save()
        return lote
