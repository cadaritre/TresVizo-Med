"""Carga de med-web.md §7.6: 10 000 pacientes y 15 000 consultas sintéticas.

Mide en el servidor (cliente de pruebas de Django, PostgreSQL local): búsqueda < 300 ms, apertura de expediente < 500 ms y
autoguardado < 200 ms (percentil 95). Resultados en ``e2e/resultados-carga.json``.
"""
import itertools
import json
import random
import statistics
import time
import uuid
from pathlib import Path

import pytest
from django.db import connections
from django.test import Client
from django.utils import timezone

from tresvizo_med.formato import a_aware, texto_busqueda
from tresvizo_med.dominio.texto import normalized
from tresvizo_med.models import Consulta, Paciente

pytestmark = [pytest.mark.django_db(databases=['default', 'med']), pytest.mark.carga]
PACIENTES, CONSULTAS = 10_000, 15_000
NOMBRES = ['Ana', 'Luis', 'María', 'José', 'Carmen', 'Juan', 'Lucía', 'Pedro', 'Sofía', 'Miguel', 'Elena', 'Jorge', 'Paula', 'Diego', 'Rosa', 'Andrés']
APELLIDOS = ['García', 'Muñoz', 'Pérez', 'Núñez', 'López', 'Hernández', 'Martínez', 'González', 'Rodríguez', 'Sánchez', 'Ramírez', 'Torres', 'Flores', 'Rivera', 'Gómez', 'Díaz']
DIAGNOSTICOS = ['Gastritis', 'Hipertensión arterial', 'Diabetes mellitus tipo 2', 'Rinofaringitis', 'Migraña', 'Lumbalgia', 'Dermatitis', 'Control prenatal']
LIMITES = {'busqueda': 300, 'expediente': 500, 'autoguardado': 200}


def p95(valores):
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados)-1, int(len(ordenados)*.95))]


def medir(funcion, veces):
    tiempos = []
    for i in range(veces):
        inicio = time.perf_counter()
        respuesta = funcion(i)
        tiempos.append((time.perf_counter()-inicio)*1000)
        # Una página que redirige o falla es rápida pero no cuenta: cada medición debe ser una respuesta correcta.
        assert respuesta is None or respuesta.status_code == 200, (respuesta.status_code, respuesta.get('Location'))
    return {'n': veces, 'mediana_ms': round(statistics.median(tiempos), 1), 'p95_ms': round(p95(tiempos), 1), 'max_ms': round(max(tiempos), 1)}


@pytest.fixture
def clinica(fabrica_actor):
    from tresvizo_med.servicios import Actor
    medicos = [Actor.de(fabrica_actor('medico')) for _ in range(5)]
    return medicos


def sembrar(medicos, azar):
    ahora = timezone.now()
    pacientes = []
    for n in range(1, PACIENTES+1):
        nombre = f'{azar.choice(NOMBRES)} {azar.choice(APELLIDOS)} {azar.choice(APELLIDOS)}'
        telefono = f'55{azar.randint(10_000_000, 99_999_999)}'
        datos = {'allergy_status': 'Alergias registradas' if n % 10 == 0 else 'No interrogado'}
        if n % 10 == 0:
            datos['allergy_records'] = [{'substance': azar.choice(['Penicilina', 'Sulfas', 'Látex']), 'severity': 'Moderada'}]
        d = {'name': nombre, 'file_number': f'RC-{n:06d}', 'phone': telefono}
        pacientes.append(Paciente(
            id=uuid.uuid4(), folio=d['file_number'], nombre=nombre, nombre_norm=normalized(nombre), busqueda=texto_busqueda(d),
            nacimiento=f'{azar.randint(1940, 2024)}-{azar.randint(1, 12):02d}-{azar.randint(1, 28):02d}', telefono=telefono, datos=datos,
            created_at=ahora, created_by=medicos[0].cuenta_id, updated_at=ahora, updated_by=medicos[0].cuenta_id))
    Paciente.objects.bulk_create(pacientes, batch_size=2000)
    # Unos pacientes concentran muchas consultas (crónicos); el resto, pocas.
    pesos = [30 if i < 100 else 1 for i in range(PACIENTES)]
    consultas = []
    acumulados = list(itertools.accumulate(pesos))
    for n in range(CONSULTAS):
        paciente = azar.choices(pacientes, cum_weights=acumulados)[0]
        medico = azar.choice(medicos)
        dia = azar.randint(0, 700)
        momento = f'{2025 + (dia // 365)}-{(dia % 365) // 31 + 1:02d}-{(dia % 28) + 1:02d}T{azar.randint(8, 19):02d}:{azar.choice([0, 15, 30, 45]):02d}:00-06:00'
        diag = azar.choice(DIAGNOSTICOS)
        borrador = n % 40 == 0
        contenido = {
            'subjective': f'Paciente refiere síntomas de {azar.randint(1, 14)} días de evolución. ' * 6, 'objective': 'Exploración sin hallazgos relevantes. ' * 4,
            'diagnoses': [{'id': str(uuid.uuid4()), 'name': diag}], 'study_orders': [],
            'vitals': [{'id': str(uuid.uuid4()), 'at': momento, 'values': {'systolic': {'value': '120', 'unit': 'mmHg', 'normalized_value': 120.0, 'normalized_unit': 'mmHg'},
                                                                           'diastolic': {'value': '80', 'unit': 'mmHg', 'normalized_value': 80.0, 'normalized_unit': 'mmHg'}}}],
            'prescriptions': [{'id': str(uuid.uuid4()), 'name': 'Paracetamol', 'strength': '500 mg', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral',
                               'frequency': '8', 'frequency_kind': 'Cada N horas'}]}
        consultas.append(Consulta(
            id=uuid.uuid4(), paciente=paciente, doctor_id=medico.cuenta_id, captured_by=medico.cuenta_id, estado='Borrador' if borrador else 'Finalizada',
            atendida_iso=momento, atendida_en=a_aware(momento), tipo='General', motivo=f'Motivo de la consulta {n}', diagnostico=diag, plan='Reposo e hidratación',
            contenido=contenido, created_at=ahora, created_by=medico.cuenta_id, updated_at=ahora, updated_by=medico.cuenta_id))
    Consulta.objects.bulk_create(consultas, batch_size=2000)
    with connections['med'].cursor() as cursor:
        cursor.execute("SELECT setval('med_folio_seq', %s, true)", [PACIENTES])
        for tabla in ('med_paciente', 'med_consulta'):
            cursor.execute(f'ANALYZE {tabla}')
    return pacientes, consultas


def test_rendimiento_con_10000_pacientes_y_15000_consultas(clinica, crear_usuario, roles):
    from tvplataforma import hosts
    from tvplataforma.modulos import modulo
    azar = random.Random(20261113)
    inicio = time.perf_counter()
    pacientes, consultas = sembrar(clinica, azar)
    sembrado = time.perf_counter()-inicio
    assert Paciente.objects.count() == PACIENTES and Consulta.objects.count() == CONSULTAS
    usuario = crear_usuario('carga')
    roles.conceder(usuario, 'med', 'medico')
    from tresvizo_med.servicios import Actor
    actor = Actor.de(usuario)
    cliente = Client(HTTP_HOST=hosts.host_de(modulo('med')))
    cliente.force_login(usuario)
    resultados = {'pacientes': PACIENTES, 'consultas': CONSULTAS, 'sembrado_s': round(sembrado, 1)}

    # Búsqueda: nombre parcial, apellido sin acentos, folio y teléfono (HTMX, como escribe el médico).
    terminos = ['garcia', 'nunez munoz', 'maria', 'ana lopez', 'RC-0042', 'RC-009999', '5551', '5587', 'zzzz', 'luis perez torres', 'carmen', 'sofia']
    resultados['busqueda'] = medir(lambda i: cliente.get('/pacientes/', {'q': terminos[i % len(terminos)]}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='resultados'), 60)
    resultados['busqueda_pagina_completa'] = medir(lambda i: cliente.get('/pacientes/', {'q': terminos[i % len(terminos)]}), 24)
    muestra_busqueda = cliente.get('/pacientes/', {'q': 'garcia'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='resultados').content.decode()
    assert 'García' in muestra_busqueda and 'med-paciente' in muestra_busqueda and '<html' not in muestra_busqueda

    # Apertura de expediente: típico, con consultas y el de mayor número de consultas.
    muestra = azar.sample(pacientes, 40)
    pagina = cliente.get(f'/pacientes/{muestra[0].id}/').content.decode()
    assert muestra[0].nombre in pagina and muestra[0].folio in pagina and '<html' in pagina
    resultados['expediente_resumen'] = medir(lambda i: cliente.get(f'/pacientes/{muestra[i].id}/'), 40)
    resultados['expediente_consultas'] = medir(lambda i: cliente.get(f'/pacientes/{muestra[i].id}/', {'pestana': 'consultas'}), 40)
    pesado = max(pacientes, key=lambda p: Consulta.objects.filter(paciente=p).count())
    resultados['consultas_del_paciente_mas_activo'] = Consulta.objects.filter(paciente=pesado).count()
    resultados['expediente_mas_activo'] = medir(lambda i: cliente.get(f'/pacientes/{pesado.id}/', {'pestana': 'consultas'}), 10)
    resultados['evolucion'] = medir(lambda i: cliente.get(f'/pacientes/{pesado.id}/', {'pestana': 'evolucion', 'periodo': 'todo'}), 10)

    # Autoguardado de un borrador (HTMX): sin cambios y con cambios.
    borradores = []
    for p in azar.sample(pacientes, 30):
        from tresvizo_med.servicios import consultas as servicio
        c, _ = servicio.iniciar(actor, p.id)
        borradores.append(c)

    def guardar(i):
        c = Consulta.objects.get(pk=borradores[i % len(borradores)].id)
        d = c.atendida_iso
        respuesta = cliente.post(f'/consultas/{c.id}/guardar/', {'date': d[:10], 'time': d[11:16], 'type': 'General', 'reason': f'Motivo {i}', 'plan': 'Reposo',
                                                              'subjective': 'Nota', 'objective': '', 'assessment_notes': '', 'revision': c.revision,
                                                              'base': json.dumps({})}, HTTP_HX_REQUEST='true')
        assert respuesta.status_code == 200 and 'Guardado' in respuesta.content.decode(), (respuesta.status_code, respuesta.content[:200])
        return respuesta
    resultados['autoguardado'] = medir(guardar, 60)
    jefe = crear_usuario('jefa')
    roles.conceder(jefe, 'med', 'admin')
    cliente_admin = Client(HTTP_HOST=hosts.host_de(modulo('med')))
    cliente_admin.force_login(jefe)
    resultados['estadisticas_toda_la_clinica'] = medir(lambda i: cliente_admin.get('/estadisticas/', {'desde': '2025-01-01', 'hasta': '2026-12-31', 'doctor': '*'}), 3)
    resultados['exportar_consultas_csv_toda_la_clinica'] = medir(lambda i: cliente_admin.get('/exportar/consultas/', {'doctor': '*'}), 2)

    ruta = Path(__file__).with_name('resultados-carga.json')
    ruta.write_text(json.dumps(resultados, ensure_ascii=False, indent=2))
    print('\n'+json.dumps(resultados, ensure_ascii=False, indent=2))
    assert resultados['busqueda']['p95_ms'] < LIMITES['busqueda'], resultados['busqueda']
    for clave in ('expediente_resumen', 'expediente_consultas'):
        assert resultados[clave]['p95_ms'] < LIMITES['expediente'], (clave, resultados[clave])
    assert resultados['autoguardado']['p95_ms'] < LIMITES['autoguardado'], resultados['autoguardado']
