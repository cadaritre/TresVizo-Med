"""Recursos geométricos originales: fuentes SVG y previsualizaciones PNG."""
from pathlib import Path
from PIL import Image, ImageDraw

DEST = Path(__file__).resolve().parents[1]/'assets'/'avatars'
INK = '#34465A'
NAMES = ['zorro', 'gato', 'oso', 'buho', 'conejo', 'panda', 'koala', 'tortuga', 'montana', 'sol', 'luna', 'arbol', 'flor', 'hoja', 'cometa', 'pez']

def build(name):
    image = Image.new('RGB', (768, 768), '#EAF1F7')
    draw = ImageDraw.Draw(image)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">']
    def ellipse(box, fill):
        draw.ellipse(tuple(v*3 for v in box), fill=fill)
        x, y, x2, y2 = box
        svg.append(f'<ellipse cx="{(x+x2)/2}" cy="{(y+y2)/2}" rx="{(x2-x)/2}" ry="{(y2-y)/2}" fill="{fill}"/>')
    def polygon(points, fill):
        draw.polygon([(x*3, y*3) for x,y in points], fill=fill)
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in points)}" fill="{fill}"/>')
    def line(points, fill, width=6):
        draw.line([(x*3, y*3) for x,y in points], fill=fill, width=width*3)
        svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{fill}" stroke-width="{width}" stroke-linecap="round"/>')
    def eyes(y=121):
        ellipse((92,y,105,y+15),INK)
        ellipse((151,y,164,y+15),INK)
    ellipse((0,0,256,256),'#EAF1F7')
    if name == 'zorro':
        polygon([(56,55),(108,84),(148,84),(204,55),(187,159),(128,206),(69,159)], '#CE854C')
        polygon([(65,108),(128,153),(194,108),(173,172),(128,201),(84,172)], '#FFF7E9')
        eyes(); ellipse((117,161,139,177),INK)
    elif name == 'gato':
        polygon([(59,52),(104,85),(151,85),(195,52),(197,160),(168,196),(85,196),(56,157)], '#C2A9C9')
        eyes(); polygon([(117,151),(139,151),(128,162)], '#795B78')
        for y in (152,168): line([(50,y),(94,y+3)],INK,3); line([(163,y+3),(208,y)],INK,3)
    elif name == 'oso':
        ellipse((45,55,106,116),'#96735F'); ellipse((150,55,211,116),'#96735F')
        ellipse((57,77,200,213),'#B38C70'); ellipse((89,143,169,197),'#E9CEAD'); eyes()
        ellipse((115,151,141,168),INK)
    elif name == 'buho':
        polygon([(59,63),(98,80),(162,80),(198,63),(188,178),(128,218),(68,178)], '#7394AF')
        ellipse((71,91,126,151),'#F8F0D9'); ellipse((130,91,185,151),'#F8F0D9'); eyes()
        polygon([(117,151),(139,151),(128,169)], '#D89A54')
        line([(100,179),(128,192),(156,179)], '#D8E6EF',5)
    elif name == 'conejo':
        ellipse((77,25,114,130),'#A0B9C9'); ellipse((142,25,179,130),'#A0B9C9')
        ellipse((88,42,104,105),'#E5BEC2'); ellipse((152,42,168,105),'#E5BEC2')
        ellipse((60,94,196,216),'#CDDEE8'); eyes(137); ellipse((119,168,137,180),'#AD7F8C')
    elif name == 'panda':
        ellipse((48,54,105,113),INK); ellipse((151,54,208,113),INK)
        ellipse((56,76,200,214),'#FCFDFE')
        ellipse((75,108,115,152),INK); ellipse((141,108,181,152),INK)
        ellipse((93,120,103,131),'#FFFFFF'); ellipse((153,120,163,131),'#FFFFFF'); ellipse((115,163,141,181),INK)
    elif name == 'koala':
        ellipse((25,75,110,161),'#87A4B2'); ellipse((146,75,231,161),'#87A4B2')
        ellipse((39,89,93,144),'#CCDDE4'); ellipse((163,89,217,144),'#CCDDE4')
        ellipse((70,81,186,211),'#ADC3CB'); eyes(125); ellipse((111,138,145,180),INK)
    elif name == 'tortuga':
        for x,y in [(52,74),(166,74),(52,173),(166,173)]: ellipse((x,y,x+38,y+38),'#87AF99')
        ellipse((104,24,152,88),'#87AF99'); ellipse((61,64,195,213),'#497E6A')
        polygon([(128,86),(168,115),(168,166),(128,193),(89,166),(89,115)], '#A4CBB1')
        ellipse((113,45,119,53),INK); ellipse((137,45,143,53),INK)
    elif name == 'montana':
        ellipse((161,47,197,83),'#DDB86C'); polygon([(28,206),(104,69),(173,206)], '#7296AE')
        polygon([(85,103),(104,69),(128,111),(106,102),(95,116)], '#FFFFFF')
        polygon([(99,206),(173,110),(229,206)], '#426C86')
    elif name == 'sol':
        import math
        for i in range(12):
            a=i*math.pi/6; line([(128+78*math.cos(a),128+78*math.sin(a)),(128+99*math.cos(a),128+99*math.sin(a))], '#DDA65B',8)
        ellipse((67,67,189,189),'#EFCC80'); eyes(118)
    elif name == 'luna':
        ellipse((53,41,203,209),'#7695B0'); ellipse((104,23,228,164),'#EAF1F7')
        for x,y in [(190,190),(70,43),(210,86)]: polygon([(x,y-9),(x+3,y-3),(x+9,y),(x+3,y+3),(x,y+9),(x-3,y+3),(x-9,y),(x-3,y-3)], '#DDB86C')
    elif name == 'arbol':
        polygon([(119,121),(138,121),(143,217),(115,217)], '#9A785C')
        for box,color in [((45,78,142,169),'#76AA8F'),((114,79,211,169),'#589079'),((78,35,179,145),'#92BDA1')]: ellipse(box,color)
    elif name == 'flor':
        line([(129,131),(129,224)],'#659982',9); ellipse((130,169,181,193),'#659982')
        for box in [(76,38,132,107),(124,38,180,107),(149,80,207,143),(121,117,180,182),(68,117,128,182),(48,77,107,142)]: ellipse(box,'#C39CB7')
        ellipse((94,78,160,143),'#EFD18B')
    elif name == 'hoja':
        polygon([(50,193),(58,119),(99,66),(209,40),(198,144),(153,184),(88,201)], '#74AA94')
        line([(41,220),(172,81)], '#376653',7)
        line([(89,169),(84,112)], '#D5E7DD',4); line([(121,136),(170,133)], '#D5E7DD',4)
    elif name == 'cometa':
        polygon([(128,31),(197,98),(128,175),(59,98)], '#7AA1BB')
        polygon([(128,31),(128,175),(59,98)], '#C2ABD0'); line([(128,175),(115,200),(142,220)],INK,3)
        line([(128,32),(128,174)],'#FFFFFF',3); line([(59,98),(197,98)],'#FFFFFF',3)
    elif name == 'pez':
        polygon([(64,127),(28,83),(28,170)], '#548B9D'); ellipse((52,73,219,182),'#8BBFC9')
        polygon([(119,87),(142,49),(166,84)], '#548B9D'); ellipse((177,107,190,120),INK)
        line([(160,95),(154,127),(162,156)], '#548B9D',4)
    svg.append('</svg>')
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST/(name+'.svg')).write_text('\n'.join(svg), encoding='utf-8')
    image.resize((256,256), Image.Resampling.LANCZOS).save(DEST/(name+'.png'))

if __name__ == '__main__':
    for name in NAMES:
        build(name)
