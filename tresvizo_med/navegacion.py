"""Navegación de Med como datos (contrato tvplataforma 1.5, §12): el armazón pinta con esto el lateral, el cajón del teléfono,
la paleta (⌘K) y la hoja de atajos, solo con Med y filtrado por rol."""
from tvplataforma.navegacion import Accion, Busqueda, Entrada

MENU = (
    Entrada('Pacientes', 'users', 'med:pacientes', atajo='g p', clave='pacientes'),
    Entrada('Borradores', 'file-pen-line', 'med:en_curso', atajo='g b', clave='borradores', contador='tresvizo_med.navegacion.borradores_abiertos'),
    Entrada('Estadísticas', 'chart-column', 'med:estadisticas', atajo='g e', clave='estadisticas'),
    Entrada('Exportar', 'download', 'med:exportar', clave='exportar'),
    Entrada('Configuración', 'settings', 'med:configuracion', atajo='g s', clave='configuracion'),
)

ACCIONES = (
    Accion('Nuevo paciente', 'user-plus', 'med:alta_nueva', atajo='n'),
    Accion('Mi perfil', 'circle-user-round', 'med:perfil'),
    Accion('Apariencia de Med', 'palette', 'med:apariencia'),
    Accion('Importar pacientes', 'file-up', 'med:importar', roles=('admin',)),
)

# Pacientes desde la paleta: solo en el host de Med y solo con un rol de Med (la vista lo exige con @requiere_rol).
BUSQUEDA = Busqueda('med:buscar_paleta', 'Buscar pacientes', icono='user-round')

# Sección del lateral a la que pertenece cada vista cuya ruta no cuelga de la de su entrada (request.tv_seccion).
SECCION_DE_VISTA = {
    'alta_nueva': 'pacientes', 'alta': 'pacientes', 'expediente': 'pacientes', 'evolucion': 'pacientes', 'consulta': 'pacientes',
    'revisar': 'pacientes', 'conflicto': 'pacientes', 'visor': 'pacientes', 'paquete': 'pacientes', 'pdf': 'pacientes',
    'en_curso': 'borradores', 'importar': 'configuracion', 'importar_mapear': 'configuracion', 'importar_previa': 'configuracion',
    'importar_recibo': 'configuracion', 'perfil': 'configuracion', 'perfil_de': 'configuracion',
}


def seccion(request):
    coincidencia = getattr(request, 'resolver_match', None)
    return SECCION_DE_VISTA.get(coincidencia.url_name if coincidencia else '', '')


def borradores_abiertos(request):
    """Número de borradores propios abiertos (altas, ediciones y consultas) para el contador del menú. Solo un número."""
    from .models import Consulta
    from .servicios import Actor, borradores, consultas
    actor = getattr(request, 'actor', None) or Actor.de(request.user)
    total = borradores.propios(actor).count()
    if actor.es_medico:
        total += consultas.visibles(actor).filter(estado=Consulta.Estado.BORRADOR, doctor_id=actor.cuenta_id).count()
    return total or None
