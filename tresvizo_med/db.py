"""Acceso a la base de Med. El código de la app no usa ``using=`` salvo en ``transaction.atomic`` (contrato §3.7)."""
from django.db import transaction

ALIAS = "med"


def atomico():
    """Transacción en la base ``med``."""
    return transaction.atomic(using=ALIAS)
