"""Preparación local de transparencia y formatos de la marca médica.

Conserva el original del proyecto de referencia. Solo procesa el PNG médico.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'assets'


def prepare():
    source = ASSETS/'tresvizo_medico_source.png'
    if not source.exists():
        source.write_bytes((ASSETS/'tresvizo_medico.png').read_bytes())
    image = Image.open(source).convert('RGBA')
    # El diseño contiene solo azul y turquesa; los píxeles casi neutros son fondo.
    pixels = []
    for r, g, b, a in image.get_flattened_data():
        if min(r, g, b) > 150 and max(r, g, b)-min(r, g, b) < 38:
            pixels.append((r, g, b, 0))
        else:
            pixels.append((r, g, b, a))
    image.putdata(pixels)
    box = image.getbbox()
    if not box:
        raise ValueError('No se encontró el símbolo en la imagen.')
    image = image.crop(box)
    image.thumbnail((448, 480), Image.Resampling.LANCZOS)
    compact = Image.new('RGBA', (512, 512))
    compact.alpha_composite(image, ((512-image.width)//2, (512-image.height)//2))
    compact.save(ASSETS/'tresvizo_medico.png')
    compact.save(ASSETS/'tresvizo_medico_compacto.png')
    # Contorno claro discreto para separar los colores originales del fondo oscuro.
    outline = compact.getchannel('A').filter(ImageFilter.MaxFilter(9))
    dark = Image.new('RGBA', compact.size, '#E7F4FA')
    dark.putalpha(outline)
    dark.alpha_composite(compact)
    dark.save(ASSETS/'tresvizo_medico_oscuro.png')
    font = ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf', 144)
    subfont = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 44)
    for suffix, symbol, ink in [('claro', compact, '#07356F'), ('oscuro', dark, '#E7F4FA')]:
        wide = Image.new('RGBA', (1350, 512))
        wide.alpha_composite(symbol, (0, 0))
        draw = ImageDraw.Draw(wide)
        draw.text((548, 122), 'TresVizo', font=font, fill=ink)
        draw.text((558, 305), 'Registro Clínico', font=subfont, fill=ink)
        wide.save(ASSETS/f'tresvizo_medico_principal_{suffix}.png')
    compact.save(ASSETS/'tresvizo_medico.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    board = Image.new('RGB', (1100, 620), '#FFFFFF')
    draw = ImageDraw.Draw(board)
    draw.rectangle((550, 0, 1100, 620), fill='#101D2E')
    labelfont = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
    for offset, symbol, ink in [(0, compact, '#263746'), (550, dark, '#F0F6FC')]:
        for size, x, y in [(256, 140, 30), (96, 50, 370), (64, 190, 388), (48, 306, 398), (32, 412, 408), (16, 482, 416)]:
            thumb = symbol.resize((size, size), Image.Resampling.LANCZOS)
            board.paste(thumb, (offset+x, y), thumb)
            draw.text((offset+x, y+size+12), f'{size} px', font=labelfont, fill=ink)
    (ROOT/'artifacts').mkdir(exist_ok=True)
    board.save(ROOT/'artifacts/marca-tamanos.png')


if __name__ == '__main__':
    prepare()
