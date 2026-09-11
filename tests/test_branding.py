from PIL import Image
from app.branding import ASSETS


def test_transparency_and_windows_icon_resolutions():
    for name in ('tresvizo_medico.png', 'tresvizo_medico_compacto.png', 'tresvizo_medico_oscuro.png',
                 'tresvizo_medico_principal_claro.png', 'tresvizo_medico_principal_oscuro.png'):
        with Image.open(ASSETS/name) as image:
            assert image.mode == 'RGBA'
            assert image.getchannel('A').getextrema() == (0, 255)
            assert image.getpixel((0, 0))[3] == 0
    with Image.open(ASSETS/'tresvizo_medico.ico') as image:
        assert {(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)} == image.ico.sizes()
