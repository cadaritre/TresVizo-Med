"""Destino de subida ``med.documento`` (contrato tvplataforma §7)."""
from django.conf import settings
from tvplataforma.subidas import ErrorDeSubida, destino_subida

from .dominio.errores import DataError
from .servicios import Actor, documentos


@destino_subida('med.documento', rol=('med', 'medico'), max_bytes=lambda: settings.TV_MED_LIMITE_DOCUMENTO)
def recibir(archivo, metadatos, usuario):
    """Valida el contenido real y deja el archivo en la lista de subidos de la persona.

    Devuelve el identificador con el que la página lo asocia a un expediente, consulta o borrador de alta.
    """
    try:
        fila = documentos.registrar_subida(Actor.de(usuario), archivo)
    except DataError as error:
        raise ErrorDeSubida(str(error)) from error
    return {'subido_id': fila['id'], 'nombre': fila['name'], 'tipo': fila['mime']}
