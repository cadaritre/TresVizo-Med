"""Exportaciones: pacientes y consultas en CSV/JSON, estadísticas en CSV, paquete del expediente y exportación completa.

Permisos (med-web.md §6): cada médico exporta lo propio; ``med.admin`` lo de toda la clínica. El CSV protege contra
fórmulas de hoja de cálculo y conserva las mismas columnas que el escritorio.
"""
import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from tvplataforma import cuentas

from ..dominio import transfer
from ..dominio.errores import DataError
from ..dominio.texto import normalized
from ..formato import adenda_a_dict, consulta_a_dict, documento_a_dict, paciente_a_dict
from ..models import CatalogoMedicamento, Clinica, Consulta, Documento, Paciente, Profesional, Tema
from . import apariencia, consultas, documentos
from .errores import NoEncontrado, PermisoDenegado

CABECERA_BOM = 'utf-8-sig'


def carpeta_descargas(cuenta_id):
    return Path(settings.TV_MED_ARCHIVOS)/'descargas'/str(cuenta_id)


def pacientes_exportables(actor, consulta='', modo='Activos', ids=None):
    """Pacientes que ``actor`` puede exportar: todos para ``med.admin``; para un médico, los que atendió o dio de alta."""
    filas = Paciente.objects.all()
    if not actor.es_admin:
        propios = Consulta.objects.filter(doctor_id=actor.cuenta_id).values('paciente_id')
        filas = filas.filter(Q(pk__in=propios) | Q(created_by=actor.cuenta_id))
    for termino in normalized(consulta).split():
        filas = filas.filter(busqueda__contains=termino)
    if modo not in ('Activos', 'Archivados', 'Todos'):
        raise DataError('Modo no admitido.')
    if modo != 'Todos':
        filas = filas.filter(archivado=(modo == 'Archivados'))
    if ids is not None:
        filas = filas.filter(pk__in=ids)
    return filas.order_by('nombre_norm', 'folio')


def _nombre(prefijo, extension):
    return f'{prefijo}-{timezone.localdate().isoformat()}.{extension}'


def exportar_pacientes(actor, formato='csv', consulta='', modo='Activos', ids=None):
    """Devuelve ``(bytes, nombre, tipo_mime)``."""
    filas = [paciente_a_dict(p) for p in pacientes_exportables(actor, consulta, modo, ids)]
    if formato == 'json':
        cuerpo = json.dumps({'schema_version': 1, 'patients': filas}, ensure_ascii=False, indent=2, default=str)
        return cuerpo.encode('utf-8'), _nombre('pacientes', 'json'), 'application/json'
    if formato != 'csv':
        raise DataError('Formato no admitido.')
    flujo = io.StringIO(newline='')
    transfer.write_patient_csv(flujo, filas)
    return flujo.getvalue().encode(CABECERA_BOM), _nombre('pacientes', 'csv'), 'text/csv; charset=utf-8'


def exportar_consultas(actor, inicio='', fin='', doctor=None, borradores=False, ids=None):
    """CSV de consultas. Un médico solo las suyas; ``med.admin`` las de la clínica o las de un médico."""
    if not actor.es_admin:
        if doctor not in (None, actor.cuenta_id):
            raise PermisoDenegado('Solo el administrador exporta consultas de otros médicos.')
        doctor = actor.cuenta_id
    transfer.check_period(inicio, fin)
    filas = [consulta_a_dict(c) for c in consultas.visibles(actor).select_related('paciente')]
    filas = transfer.select_consultations(filas, start=inicio, end=fin, doctor_id=doctor if doctor not in (None, '*') else '',
                                          include_drafts=borradores, identifiers=ids)
    pacientes = {str(p.id): paciente_a_dict(p) for p in Paciente.objects.filter(pk__in={f['patient_id'] for f in filas})}
    nombres = cuentas.nombres({f['doctor_id'] for f in filas})
    flujo = io.StringIO(newline='')
    transfer.write_consultation_csv(flujo, filas, pacientes, {k: {'name': v} for k, v in nombres.items()})
    return flujo.getvalue().encode(CABECERA_BOM), _nombre('consultas', 'csv'), len(filas)


def estadisticas_csv(datos, quien):
    """CSV de las estadísticas de un periodo: ``seccion, clave, valor`` con la instantánea de filtros al principio."""
    flujo = io.StringIO(newline='')
    escritor = csv.writer(flujo)
    escritor.writerow(['seccion', 'clave', 'valor'])
    escritor.writerows([['filtros', 'periodo', f"{datos['start']} a {datos['end']}"], ['filtros', 'doctor', transfer.safe_csv(quien)],
                        ['filtros', 'tipo', transfer.safe_csv(datos['filters']['type'])],
                        ['filtros', 'diagnostico', transfer.safe_csv(datos['filters']['diagnosis'])],
                        ['filtros', 'pacientes', datos['filters']['patient_group']]])
    for clave in ('consultations', 'patients', 'new', 'recurrent', 'days', 'average', 'drafts', 'no_diagnosis', 'previous', 'difference', 'variation'):
        escritor.writerow(['resumen', clave, '' if datos[clave] is None else datos[clave]])
    for seccion in ('diagnoses', 'types', 'reasons', 'ages', 'sexes', 'activity', 'frequency'):
        for clave, valor in datos[seccion].items():
            escritor.writerow([seccion, transfer.safe_csv(clave), valor])
    return flujo.getvalue().encode(CABECERA_BOM), _nombre('estadisticas', 'csv')


# --- ZIP: paquete del expediente y exportación completa --------------------------------------------------------

def _escribir_zip(destino, escribir):
    """Escribe un ZIP en ``destino`` de forma atómica y lo verifica antes de publicarlo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name('.'+destino.name+'.tmp')
    try:
        with zipfile.ZipFile(temporal, 'w', zipfile.ZIP_DEFLATED) as zip_:
            escribir(zip_)
        with zipfile.ZipFile(temporal) as zip_:
            if zip_.testzip():
                raise DataError('No se pudo verificar el archivo generado.')
        temporal.replace(destino)
    finally:
        temporal.unlink(missing_ok=True)


def crear_paquete_expediente(actor, paciente_id, documento_ids, consulta_id=None, progreso=lambda f, m='': None):
    """ZIP del expediente de un paciente: ``expediente.json``, los documentos elegidos y un manifiesto SHA-256."""
    persona = Paciente.objects.filter(pk=paciente_id).first()
    if persona is None:
        raise NoEncontrado('No existe el paciente.')
    filas_consulta = [c for c in consultas.visibles(actor).filter(paciente=persona) if not consulta_id or str(c.id) == str(consulta_id)]
    docs = []
    for identificador in documento_ids:
        x = documentos.obtener(actor, identificador)
        if x.paciente_id != persona.id or x.borrador_id or (consulta_id and str(x.consulta_id) != str(consulta_id)):
            raise DataError('La selección contiene documentos de otro destino.')
        docs.append(x)
    identificador = uuid.uuid4()
    destino = carpeta_descargas(actor.cuenta_id)/f'{identificador}.zip'

    def escribir(zip_):
        progreso(.2, 'Reuniendo el expediente')
        encuentros = [consulta_a_dict(c) for c in filas_consulta]
        archivos = [documento_a_dict(x) for x in docs]
        carga = json.dumps({'schema_version': 2, 'patient': paciente_a_dict(persona), 'encounters': encuentros, 'attachments': archivos},
                           ensure_ascii=False, default=str).encode('utf-8')
        manifiesto = {'schema_version': 2, 'kind': 'patient-export', 'files': {'expediente.json': hashlib.sha256(carga).hexdigest()}}
        zip_.writestr('expediente.json', carga)
        for i, x in enumerate(docs, 1):
            progreso(.2+.7*i/max(1, len(docs)), f'Documento {i} de {len(docs)}')
            ruta = documentos.ruta_verificada(actor, x.id)
            nombre = f'documentos/{x.id}{ruta.suffix}'
            zip_.write(ruta, nombre)
            manifiesto['files'][nombre] = x.sha256
        zip_.writestr('manifest.json', json.dumps(manifiesto))
    _escribir_zip(destino, escribir)
    return identificador


def uuid_de_cuenta(cuenta_id):
    """Las cuentas del portal son enteros; el formato del escritorio usa UUID: se derivan de forma estable."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f'tresvizo-med:cuenta:{int(cuenta_id)}'))


CLAVES_CUENTA = ('doctor_id', 'captured_by', 'created_by', 'updated_by', 'actor')


def _a_formato_escritorio(valor):
    if isinstance(valor, dict):
        return {k: (uuid_de_cuenta(v) if k in CLAVES_CUENTA and isinstance(v, int) else _a_formato_escritorio(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_a_formato_escritorio(v) for v in valor]
    return valor


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str).encode('utf-8')


def crear_exportacion_completa(actor, progreso=lambda f, m='': None):
    """ZIP de toda la clínica con el formato del respaldo del escritorio (``manifest.json`` v1 con SHA-256 por archivo).

    Es la salida de datos de la clínica; restaurar es una operación del propietario en el servidor.
    """
    actor.exigir_admin()
    identificador = uuid.uuid4()
    destino = carpeta_descargas(actor.cuenta_id)/f'{identificador}.zip'

    def escribir(zip_):
        archivos = {}

        def agregar(nombre, datos):
            archivos[nombre] = hashlib.sha256(datos).hexdigest()
            zip_.writestr(nombre, datos)

        def agregar_archivo(nombre, ruta):
            with ruta.open('rb') as flujo:
                archivos[nombre] = hashlib.file_digest(flujo, 'sha256').hexdigest()
            zip_.write(ruta, nombre)

        progreso(.05, 'Identidad y apariencia')
        clinica = Clinica.obtener()
        identidad = dict(clinica.valores())
        for campo, ruta_relativa in (('clinic_logo', clinica.logo_ruta), ('clinic_icon', clinica.icono_ruta)):
            origen = Path(settings.TV_MED_ARCHIVOS)/ruta_relativa if ruta_relativa else None
            if origen and origen.is_file():
                nombre = f'config/{origen.name}'
                agregar_archivo(nombre, origen)
                identidad[campo] = nombre
        agregar('config/schema.json', _json({'version': 2}))
        agregar('config/identity.json', _json(identidad))
        temas = {str(t.id): {'schema_version': 1, 'name': t.nombre, 'tokens': t.tokens} for t in Tema.objects.all()}
        usuarios = {uuid_de_cuenta(p.cuenta_id): {'inherit': p.hereda_tema, 'theme': p.tema} for p in Profesional.objects.exclude(tema='')
                    if p.tema in temas or p.tema in apariencia.listar()}
        agregar('config/appearance.json', _json({'schema_version': 1, 'clinic': clinica.tema_clinica if clinica.tema_clinica in apariencia.listar() else 'Clínico',
                                                 'custom': temas, 'users': usuarios,
                                                 'owners': {str(t.id): uuid_de_cuenta(t.dueno_id) for t in Tema.objects.all()}}))

        progreso(.15, 'Pacientes')
        pacientes = list(Paciente.objects.all())
        for p in pacientes:
            agregar(f'data/patients/{p.id}.json', _json(_a_formato_escritorio(paciente_a_dict(p))))
        progreso(.35, 'Consultas')
        involucrados = set()
        for c in Consulta.objects.select_related('paciente').prefetch_related('adendas'):
            d = consulta_a_dict(c)
            involucrados |= {d['doctor_id'], d['captured_by'], *[a['actor'] for a in d['addenda']]}
            agregar(f'data/encounters/{c.id}.json', _json(_a_formato_escritorio(d)))
        progreso(.55, 'Documentos')
        documentos_todos = list(Documento.objects.exclude(paciente=None))
        for i, x in enumerate(documentos_todos, 1):
            d = documento_a_dict(x)
            origen = documentos.ruta_absoluta(x)
            if origen.is_file():
                d['path'] = f'attachments/originals/{x.id}{origen.suffix}'
                agregar_archivo(d['path'], origen)
            agregar(f'data/attachments/{x.id}.json', _json(_a_formato_escritorio(d)))
            progreso(.55+.3*i/max(1, len(documentos_todos)), f'Documento {i} de {len(documentos_todos)}')
        for m in CatalogoMedicamento.objects.prefetch_related('favoritos'):
            agregar(f'data/medication_catalog/{m.id}.json', _json({
                'id': str(m.id), 'name': m.producto, 'ingredient': m.principio_activo, 'presentation': m.presentacion,
                'strength': m.concentracion, 'favorites': [uuid_de_cuenta(f.cuenta_id) for f in m.favoritos.all()]}))
        progreso(.9, 'Personas')
        perfiles = {p.cuenta_id: p for p in Profesional.objects.all()}
        involucrados |= set(perfiles) | {persona.id for rol in ('medico', 'admin') for persona in cuentas.con_rol('med', rol)}
        personas = cuentas.personas(involucrados)
        admins = {persona.id for persona in cuentas.con_rol('med', 'admin')}
        for cuenta in involucrados:
            uid = uuid_de_cuenta(cuenta)
            persona = personas.get(cuenta)
            agregar(f'data/users/{uid}.json', _json({
                'schema_version': 1, 'id': uid, 'name': persona.nombre if persona else 'Cuenta eliminada',
                'username': persona.usuario if persona else uid, 'role': 'admin' if cuenta in admins else 'doctor',
                'active': persona is not None, 'created_at': timezone.now().isoformat(timespec='seconds')}))
            perfil = perfiles.get(cuenta)
            if perfil:
                agregar(f'config/profiles/{uid}.json', _json({'avatar': perfil.avatar or 'initials', 'reduce_motion': perfil.reducir_movimiento,
                                                              'license': perfil.cedula, 'specialty': perfil.especialidad}))
        manifiesto = {'schema_version': 1, 'created_at': datetime.now().astimezone().isoformat(), 'files': archivos}
        zip_.writestr('manifest.json', json.dumps(manifiesto))
    _escribir_zip(destino, escribir)
    transfer.verify_backup(destino)
    return identificador


def ruta_descarga(actor, identificador):
    """ZIP generado para ``actor`` (cada persona solo ve los suyos)."""
    ruta = carpeta_descargas(actor.cuenta_id)/f'{identificador}.zip'
    if not ruta.is_file():
        raise NoEncontrado('La descarga ya no está disponible.')
    return ruta


def ruta_pdf(actor, identificador):
    from .pdf import carpeta_pdf
    ruta = carpeta_pdf(actor.cuenta_id)/f'{identificador}.pdf'
    if not ruta.is_file():
        raise NoEncontrado('El PDF ya no está disponible.')
    return ruta
