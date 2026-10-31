from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'launch-assets' / '2026-05-31-first-share'
OUT.mkdir(parents=True, exist_ok=True)

PALETTE = {
    'bg': (5, 5, 16),
    'panel': (12, 18, 36),
    'cyan': (0, 240, 255),
    'blue': (0, 128, 255),
    'purple': (168, 85, 247),
    'ink': (248, 250, 252),
    'muted': (148, 163, 184),
    'green': (0, 255, 136),
    'red': (255, 51, 102),
    'warn': (251, 191, 36),
}

FONT_CANDIDATES = [
    Path('C:/Windows/Fonts/inter.ttf'),
    Path('C:/Windows/Fonts/Inter.ttf'),
    Path('C:/Windows/Fonts/arial.ttf'),
    Path('C:/Windows/Fonts/segoeui.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
]
BOLD_CANDIDATES = [
    Path('C:/Windows/Fonts/arialbd.ttf'),
    Path('C:/Windows/Fonts/segoeuib.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
]
MONO_CANDIDATES = [
    Path('C:/Windows/Fonts/consola.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'),
]

def first_font(candidates):
    for p in candidates:
        if p.exists():
            return str(p)
    return None

REG = first_font(FONT_CANDIDATES)
BOLD = first_font(BOLD_CANDIDATES) or REG
MONO = first_font(MONO_CANDIDATES) or REG

def font(path, size):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()

def gradient(size, start, end):
    w, h = size
    img = Image.new('RGBA', size)
    px = img.load()
    for x in range(w):
        t = x / max(1, w - 1)
        col = tuple(int(start[i] * (1 - t) + end[i] * t) for i in range(3)) + (255,)
        for y in range(h):
            px[x, y] = col
    return img

def rounded_gradient(draw_img, xy, radius=28):
    x1, y1, x2, y2 = xy
    grad = gradient((x2-x1, y2-y1), PALETTE['cyan'], PALETTE['blue'])
    mask = Image.new('L', grad.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, x2-x1, y2-y1), radius=radius, fill=255)
    layer = Image.new('RGBA', draw_img.size, (0, 0, 0, 0))
    layer.paste(grad, (x1, y1), mask)
    draw_img.alpha_composite(layer)

def multiline(draw, xy, text, fnt, fill, width_px, line_spacing=1.08):
    words = text.split()
    lines, line = [], ''
    for word in words:
        test = f'{line} {word}'.strip()
        if draw.textbbox((0,0), test, font=fnt)[2] <= width_px or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    x, y = xy
    lh = int((draw.textbbox((0,0), 'Ay', font=fnt)[3] - draw.textbbox((0,0), 'Ay', font=fnt)[1]) * line_spacing)
    for ln in lines:
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += lh
    return y

def draw_chart(base, x, y, w, h):
    d = ImageDraw.Draw(base, 'RGBA')
    d.rounded_rectangle((x, y, x+w, y+h), radius=30, fill=(255,255,255,10), outline=(255,255,255,35), width=2)
    for gx in range(x+50, x+w, 70):
        d.line((gx, y+20, gx, y+h-20), fill=(255,255,255,13), width=1)
    for gy in range(y+55, y+h, 62):
        d.line((x+20, gy, x+w-20, gy), fill=(255,255,255,13), width=1)
    pts = [(x+50,y+h-80),(x+120,y+h-150),(x+200,y+h-118),(x+285,y+h-225),(x+365,y+h-145),(x+w-55,y+86)]
    for i in range(len(pts)-1):
        d.line((pts[i], pts[i+1]), fill=PALETTE['cyan']+(255,), width=8)
    d.rounded_rectangle((x+int(w*.56), y+48, x+int(w*.91), y+120), radius=14, fill=(255,51,102,25), outline=(255,51,102,95), width=2)
    d.text((x+int(w*.59), y+72), 'SUPPLY', font=font(MONO, max(17, w//25)), fill=(255,138,166))
    d.rounded_rectangle((x+48, y+h-122, x+int(w*.45), y+h-54), radius=14, fill=(0,255,136,25), outline=(0,255,136,95), width=2)
    d.text((x+70, y+h-98), 'DEMAND', font=font(MONO, max(17, w//25)), fill=(121,255,189))
    d.ellipse((x+w-96, y+90, x+w-66, y+120), fill=PALETTE['green'])
    d.text((x+w-145, y+132), 'MCP', font=font(MONO, max(15, w//28)), fill=PALETTE['green'])

def make_asset(filename, size, title, subtitle, bullets):
    w, h = size
    img = Image.new('RGBA', size, PALETTE['bg']+(255,))
    # glow layers
    glow = Image.new('RGBA', size, (0,0,0,0))
    gd = ImageDraw.Draw(glow, 'RGBA')
    gd.ellipse((-w//4, -h//5, int(w*.85), int(h*.65)), fill=PALETTE['cyan']+(38,))
    gd.ellipse((int(w*.48), -h//6, int(w*1.15), int(h*.45)), fill=PALETTE['purple']+(34,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(55)))
    d = ImageDraw.Draw(img, 'RGBA')
    for gx in range(0, w, 64):
        d.line((gx,0,gx,h), fill=(255,255,255,14), width=1)
    for gy in range(0, h, 64):
        d.line((0,gy,w,gy), fill=(255,255,255,14), width=1)

    portrait = h > w
    square = h == w
    margin = 72 if portrait else 90
    logo = 70 if portrait else 62
    rounded_gradient(img, (margin, margin, margin+logo, margin+logo), 18)
    d = ImageDraw.Draw(img, 'RGBA')
    d.line((margin+18, margin+logo-20, margin+30, margin+logo-38, margin+42, margin+logo-32, margin+54, margin+20), fill=(255,255,255), width=5, joint='curve')
    d.text((margin+logo+18, margin+logo//2-18), 'u²Algo', font=font(BOLD, 36 if not portrait else 40), fill=PALETTE['ink'])

    top = 245 if portrait else 190
    d.text((margin, top), 'BUILD-IN-PUBLIC · RISK DISCIPLINE', font=font(MONO, 18), fill=PALETTE['cyan'])
    title_font = font(BOLD, 72 if portrait else (58 if square else 66))
    sub_font = font(REG, 31 if portrait else (26 if square else 29))
    title_w = (w - margin*2) if portrait else (520 if square else min(720, w-margin*2))
    y = multiline(d, (margin, top+48), title, title_font, PALETTE['ink'], title_w, 0.98)
    multiline(d, (margin, y+28), subtitle, sub_font, PALETTE['muted'], title_w if (portrait or square) else 680, 1.22)

    if portrait:
        by = 660
        gap = 78
        bullet_font = font(BOLD, 34)
    elif square:
        by = 620
        gap = 58
        bullet_font = font(BOLD, 30)
    else:
        by = 560
        gap = 58
        bullet_font = font(BOLD, 29)
    for i, b in enumerate(bullets):
        yy = by + i*gap
        d.ellipse((margin, yy-20, margin+18, yy-2), fill=PALETTE['cyan'])
        d.text((margin+38, yy-34), b, font=bullet_font, fill=PALETTE['ink'])

    if portrait:
        draw_chart(img, 80, h-640, w-160, 360)
        # cover any right-side marker text spill with background-colored margin
        d.rectangle((w-26, h-650, w, h-250), fill=PALETTE['bg']+(255,))
    elif square:
        draw_chart(img, 590, 300, 380, 285)
    else:
        draw_chart(img, w-560, 190, 470, 360)

    footer_font = font(MONO, 24 if portrait else 22)
    d.text((margin, h-(100 if portrait else 70)), 'Yatırım tavsiyesi değildir · DYOR · Risk içerir', font=footer_font, fill=PALETTE['warn'])
    img.convert('RGB').save(OUT / filename, quality=94)

assets = [
    ('x-launch-1600x900.png', (1600,900), 'Bot analiz akışı artık daha görünür', 'TradingView + MCP gözlem katmanı ile efloud-bot’un takip ettiği coin evreni açıklanabilir markerlarla izleniyor.', ['SMC tabanlı araştırma', 'Scalp · Mid · Long profilleri', 'Public-safe gözlem katmanı']),
    ('instagram-carousel-cover-1080x1080.png', (1080,1080), 'Sinyal değil, açıklanabilir araştırma', 'u2algo public site: risk-disiplinli algoritmik trading araştırması ve chart üstü bot hareketleri.', ['TradingView + MCP', 'Coin evreni gözlemi', 'DYOR + risk çerçevesi']),
    ('shorts-cover-1080x1920.png', (1080,1920), 'Trading bot analizini görünür kılmak', 'u2algo, efloud-bot tabanlı SMC araştırmasını chart üzerinde izlenebilir hale getiriyor.', ['Bot markerları', 'Risk disiplini', 'Build-in-public']),
]
for args in assets:
    make_asset(*args)
print('\n'.join(str(OUT / a[0]) for a in assets))
