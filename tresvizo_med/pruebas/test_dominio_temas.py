"""Temas, contraste e identidad (portado de tests/test_core.py y test_clinic_update.py del escritorio)."""
import uuid
import pytest

from tresvizo_med.dominio.errores import DataError
from tresvizo_med.dominio.themes import (BUILTINS, DEFAULT_IDENTITY, contrast, derived, issues, repair,
                                         validate_appearance_state, validate_identity, validate_theme, validate_url)


@pytest.mark.parametrize('name', BUILTINS)
def test_builtin_contrast(name):
    assert not issues(BUILTINS[name])
    t = derived(BUILTINS[name])
    for key in ('button', 'secondary', 'header', 'sidebar', 'selection'):
        for suffix in ('', '_hover', '_pressed', '_disabled'):
            assert contrast(t[key+suffix], t['on_'+key+suffix]) >= 4.5


def test_repair_and_semantic_tokens():
    t = {k: '#FFFFFF' for k in BUILTINS['Clínico']}
    assert issues(t)
    fixed = repair(t)
    assert not issues(fixed)
    for kind in ('error', 'success', 'warning'):
        for suffix in ('bg', 'fg'):
            assert derived(fixed)[kind+'_'+suffix] == derived(BUILTINS['Azul profundo'])[kind+'_'+suffix]


def test_builtins_have_nineteen_tokens():
    assert len(BUILTINS) == 5  # la sexta de fábrica es el editor «Personalizada»
    assert all(len(tokens) == 19 for tokens in BUILTINS.values())


@pytest.mark.parametrize('url', ['file:///c:/x', 'javascript:alert(1)', 'ftp://example.com', 'https://', 'https://a b.com',
                                 'https://user:password@example.com', 'https://example.com:bad'])
def test_bad_links(url):
    with pytest.raises(DataError):
        validate_url(url)


def test_good_link_is_returned_unchanged():
    assert validate_url('https://www.tresvizo.com/') == 'https://www.tresvizo.com/'


def test_theme_validation_rejects_bad_colors():
    tokens = dict(BUILTINS['Clínico'])
    assert validate_theme({'schema_version': 1, 'name': 'Mío', 'tokens': tokens})['name'] == 'Mío'
    with pytest.raises(DataError):
        validate_theme({'schema_version': 1, 'name': 'Mío', 'tokens': {**tokens, 'primary': 'rojo'}})


def test_identity_validation():
    assert validate_identity(dict(DEFAULT_IDENTITY))
    for bad in ({'website': 'javascript:alert(1)'}, {'clinic_name': '  '}, {'app_name': 'x'*121}, {'document_text': '#12'}):
        with pytest.raises(DataError):
            validate_identity({**DEFAULT_IDENTITY, **bad})


def appearance_state(**changes):
    state = {'schema_version': 1, 'clinic': 'Clínico', 'custom': {}, 'users': {}, 'owners': {}}
    state.update(changes)
    return state


def test_appearance_state_roundtrip_and_rejections():
    validate_appearance_state(appearance_state())
    doctor, theme_key = str(uuid.uuid4()), str(uuid.uuid4())
    custom = {'name': 'Mío', 'schema_version': 1, 'tokens': dict(BUILTINS['Clínico'])}
    validate_appearance_state(appearance_state(custom={theme_key: custom}, owners={theme_key: doctor},
                                               users={doctor: {'inherit': False, 'theme': theme_key}}))
    with pytest.raises(DataError):
        validate_appearance_state(appearance_state(clinic='Inexistente'))
    with pytest.raises(DataError):
        validate_appearance_state(appearance_state(users={'no-uuid': {'inherit': True, 'theme': 'Clínico'}}))
    with pytest.raises(DataError):
        validate_appearance_state(appearance_state(custom={theme_key: custom}))  # sin propietario
    with pytest.raises(DataError):
        validate_appearance_state({'schema_version': 2})
