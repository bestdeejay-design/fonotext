#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор визуальных материалов Fonotext: OG-превью, иконки, карточки для соцсетей.

Создаёт (относительно docs/):
    og-image.png                 1200×630  — превью для Telegram, VK, LinkedIn, X, WhatsApp
    social/square-1080.png       1080×1080 — пост в Telegram/VK/Instagram
    social/stories-1080x1920.png 1080×1920 — истории, клипы, shorts
    social/vk-cover-1590x400.png 1590×400  — обложка сообщества ВКонтакте
    social/linkedin-1584x396.png 1584×396  — обложка компании в LinkedIn
    social/quote-1080x1080.png   1080×1080 — карточка-цитата (шаблон под рубрику)
    icon-192.png, icon-512.png, apple-touch-icon.png — иконки сайта

Запуск:  python3 tools/make-social-assets.py
Требуется Pillow и шрифты DejaVu (обычно есть в Linux). Текст правится в TEXTS.
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SOCIAL = os.path.join(DOCS, "social")
FONTS = "/usr/share/fonts/truetype/dejavu"
F_BOLD = os.path.join(FONTS, "DejaVuSans-Bold.ttf")
F_REG = os.path.join(FONTS, "DejaVuSans.ttf")

ACCENT = (79, 70, 229)      # #4F46E5
ACCENT2 = (124, 58, 237)    # #7C3AED
INK = (15, 23, 42)          # #0F172A
WHITE = (255, 255, 255)
MUTED = (203, 210, 235)
OK = (52, 211, 153)

TEXTS = {
    "brand": "Fonotext",
    "headline": "Разбор 100% звонков,\nа не 3% выборки",
    "sub": "Транскрипты со спикерами · классификация · контроль скриптов\nс доказательствами · дашборды · разбор архива",
    "stats": [("100%", "покрытие звонков"), ("0,89 ₽", "за минуту всё включено"), ("300 мин", "бесплатно на старте")],
    "url": "bestdeejay-design.github.io/fonotext",
    "quote": "«Мы не обещаем волшебный WER —\nмы измеряем его на ваших записях\nи подписываемся цифрами»",
    "quote_author": "Принцип Fonotext",
    "tagline": "Речевая аналитика телефонных разговоров · обработка в РФ, 152-ФЗ",
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def gradient(size: tuple, c1=ACCENT, c2=ACCENT2, diagonal: bool = True) -> Image.Image:
    """Диагональный градиент без внешних зависимостей."""
    w, h = size
    img = Image.new("RGB", size, c1)
    px = img.load()
    total = (w + h) if diagonal else h
    for y in range(h):
        for x in range(0, w, 4):  # шаг 4 px — визуально неотличимо, быстрее в 4 раза
            k = ((x + y) / total) if diagonal else (y / h)
            r = int(c1[0] + (c2[0] - c1[0]) * k)
            g = int(c1[1] + (c2[1] - c1[1]) * k)
            b = int(c1[2] + (c2[2] - c1[2]) * k)
            for dx in range(4):
                if x + dx < w:
                    px[x + dx, y] = (r, g, b)
    return img


def wave(draw: ImageDraw.ImageDraw, x0: int, y: int, width: int, height: int,
         bars: int = 48, color=(255, 255, 255, 28)) -> None:
    """Звуковая волна — фирменный элемент."""
    import math
    step = width / bars
    for i in range(bars):
        k = abs(math.sin(i * 0.7)) * 0.85 + 0.15
        bh = max(4, int(height * k))
        bx = x0 + i * step
        draw.rounded_rectangle([bx, y - bh // 2, bx + step * 0.5, y + bh // 2],
                               radius=int(step * 0.25), fill=color)


def logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, filled=True, label=True) -> int:
    """Логотип: скруглённый квадрат с волной.

    filled=True  — для тёмного/градиентного фона: белый квадрат, волна акцентная.
    filled=False — для светлого фона: акцентный квадрат, волна белая.
    """
    if filled:
        draw.rounded_rectangle([x, y, x + size, y + size], radius=int(size * 0.22), fill=WHITE)
        wave(draw, x + size * 0.18, y + size // 2, size * 0.64, size * 0.55, bars=7, color=ACCENT)
    else:
        draw.rounded_rectangle([x, y, x + size, y + size], radius=int(size * 0.22), fill=ACCENT)
        wave(draw, x + size * 0.18, y + size // 2, size * 0.64, size * 0.55, bars=7, color=WHITE)
    if label:
        f = font(F_BOLD, int(size * 0.78))
        draw.text((x + size * 1.35, y + size * 0.5), TEXTS["brand"], font=f,
                  fill=WHITE if filled else INK, anchor="lm")
        return int(x + size * 1.35 + draw.textlength(TEXTS["brand"], font=f))
    return x + size


def wrap(draw, text: str, f, max_w: int) -> list:
    lines = []
    for paragraph in text.split("\n"):
        words, line = paragraph.split(), ""
        for w in words:
            probe = (line + " " + w).strip()
            if draw.textlength(probe, font=f) <= max_w:
                line = probe
            else:
                if line:
                    lines.append(line)
                line = w
        lines.append(line)
    return lines


def fit_font(draw, text: str, path: str, max_w: int, start: int, min_size: int = 28):
    """Подбирает максимальный размер шрифта, при котором самая длинная строка влезает в max_w."""
    size = start
    while size > min_size:
        f = font(path, size)
        longest = max(draw.textlength(line, font=f) for line in text.split("\n"))
        if longest <= max_w:
            return f
        size -= 2
    return font(path, min_size)


def draw_multiline(draw, text: str, f, x: int, y: int, fill, line_gap: float = 1.24,
                   max_w: int | None = None) -> int:
    """Рисует текст с переносами; возвращает Y после последней строки."""
    lines = wrap(draw, text, f, max_w) if max_w else text.split("\n")
    asc, desc = f.getmetrics()
    step = int((asc + desc) * line_gap)
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += step
    return y


def save_og() -> None:
    W, H = 1200, 630
    img = gradient((W, H))
    d = ImageDraw.Draw(img, "RGBA")
    wave(d, 60, H - 60, W - 120, 70, bars=56, color=(255, 255, 255, 26))

    logo(d, 72, 64, 64)

    PAD = 72
    f_head = fit_font(d, TEXTS["headline"], F_BOLD, W - PAD * 2, 66)
    y = draw_multiline(d, TEXTS["headline"], f_head, PAD, 206, WHITE)

    f_sub = fit_font(d, TEXTS["sub"], F_REG, W - PAD * 2, 27)
    y = draw_multiline(d, TEXTS["sub"], f_sub, PAD, y + 16, MUTED, 1.4)

    # плашки со цифрами
    f_num, f_lab = font(F_BOLD, 34), font(F_REG, 19)
    x = 72
    for num, lab in TEXTS["stats"]:
        w = max(int(d.textlength(num, font=f_num)), int(d.textlength(lab, font=f_lab))) + 44
        d.rounded_rectangle([x, H - 168, x + w, H - 84], radius=14, fill=(255, 255, 255, 30))
        d.text((x + 22, H - 156), num, font=f_num, fill=WHITE)
        d.text((x + 22, H - 112), lab, font=f_lab, fill=MUTED)
        x += w + 16

    f_url = font(F_BOLD, 22)
    d.text((W - 72, H - 52), TEXTS["url"], font=f_url, fill=WHITE, anchor="rm")
    img.save(os.path.join(DOCS, "og-image.png"), optimize=True)


def save_square() -> None:
    S = 1080
    img = gradient((S, S), ACCENT2, ACCENT)
    d = ImageDraw.Draw(img, "RGBA")
    wave(d, 80, 812, S - 160, 120, bars=40, color=(255, 255, 255, 30))
    logo(d, 80, 80, 72)

    PAD = 80
    f_head = fit_font(d, TEXTS["headline"], F_BOLD, S - PAD * 2, 74)
    y = draw_multiline(d, TEXTS["headline"], f_head, PAD, 300, WHITE)

    f_sub = fit_font(d, TEXTS["sub"], F_REG, S - PAD * 2, 27)
    draw_multiline(d, TEXTS["sub"].replace("\n", " "), f_sub, PAD, y + 20, MUTED, 1.4, S - PAD * 2)

    f_num, f_lab = font(F_BOLD, 40), font(F_REG, 21)
    y = S - 250
    for num, lab in TEXTS["stats"]:
        d.text((80, y), num, font=f_num, fill=OK)
        d.text((80 + 150, y + 12), lab, font=f_lab, fill=MUTED)
        y += 62

    f_url = font(F_BOLD, 24)
    d.text((80, S - 70), TEXTS["url"], font=f_url, fill=WHITE)
    img.save(os.path.join(SOCIAL, "square-1080.png"), optimize=True)


def save_stories() -> None:
    W, H = 1080, 1920
    img = gradient((W, H), ACCENT, ACCENT2)
    d = ImageDraw.Draw(img, "RGBA")
    wave(d, 80, H - 420, W - 160, 200, bars=34, color=(255, 255, 255, 28))
    logo(d, 90, 140, 84)

    PAD = 90
    f_head = fit_font(d, TEXTS["headline"], F_BOLD, W - PAD * 2, 80)
    y = draw_multiline(d, TEXTS["headline"], f_head, PAD, 540, WHITE)

    f_sub = fit_font(d, TEXTS["sub"], F_REG, W - PAD * 2, 32)
    y = draw_multiline(d, TEXTS["sub"].replace("\n", " "), f_sub, PAD, y + 30, MUTED, 1.4, W - PAD * 2)

    f_num, f_lab = font(F_BOLD, 46), font(F_REG, 24)
    for num, lab in TEXTS["stats"]:
        y += 26
        d.text((90, y), num, font=f_num, fill=OK)
        d.text((90, y + 58), lab, font=f_lab, fill=MUTED)
        y += 62

    f_cta = font(F_BOLD, 34)
    d.rounded_rectangle([90, H - 300, W - 90, H - 210], radius=18, fill=WHITE)
    d.text((W // 2, H - 255), "300 минут бесплатно", font=f_cta, fill=ACCENT, anchor="mm")
    f_url = font(F_BOLD, 26)
    d.text((W // 2, H - 160), TEXTS["url"], font=f_url, fill=WHITE, anchor="mm")
    img.save(os.path.join(SOCIAL, "stories-1080x1920.png"), optimize=True)


def save_widescreen(path: str, W: int, H: int, big: bool = False) -> None:
    img = gradient((W, H))
    d = ImageDraw.Draw(img, "RGBA")
    wave(d, 40, H - 34, W - 80, 46, bars=int(W / 26), color=(255, 255, 255, 24))
    size = 56 if big else 46
    logo(d, 48, H // 2 - size // 2, size)
    f = font(F_BOLD, 30 if big else 24)
    d.text((W - 48, H // 2), TEXTS["tagline"], font=f, fill=MUTED, anchor="rm")
    img.save(path, optimize=True)


def save_quote() -> None:
    S = 1080
    img = Image.new("RGB", (S, S), (246, 247, 251))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, S, 14], fill=ACCENT)
    d.rounded_rectangle([0, 0, 26, S], radius=0, fill=ACCENT)
    logo(d, 100, 90, 60, filled=False)

    f_q = fit_font(d, TEXTS["quote"], F_BOLD, S - 220, 54)
    y = draw_multiline(d, TEXTS["quote"], f_q, 100, 380, INK)

    f_a = font(F_REG, 26)
    d.text((100, y + 20), TEXTS["quote_author"], font=f_a, fill=(85, 97, 122))
    f_u = font(F_BOLD, 24)
    d.text((100, S - 90), TEXTS["url"], font=f_u, fill=ACCENT)
    img.save(os.path.join(SOCIAL, "quote-1080x1080.png"), optimize=True)


def save_icons() -> None:
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        img = Image.new("RGB", (size, size), WHITE)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=ACCENT)
        wave(d, size * 0.16, size // 2, size * 0.68, size * 0.52,
             bars=7, color=WHITE)
        img.save(os.path.join(DOCS, name), optimize=True)

    # favicon.svg — векторная иконка (та же геометрия, что в inline-версии на странице)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="7" fill="#4F46E5"/>'
           '<path d="M7 16h2m3-6v12m3-9v6m3-9v12m3-6h2" stroke="white" stroke-width="2" '
           'stroke-linecap="round" fill="none"/></svg>')
    with open(os.path.join(DOCS, "favicon.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg)


def main() -> None:
    os.makedirs(SOCIAL, exist_ok=True)
    save_og()
    save_square()
    save_stories()
    save_widescreen(os.path.join(SOCIAL, "vk-cover-1590x400.png"), 1590, 400)
    save_widescreen(os.path.join(SOCIAL, "linkedin-1584x396.png"), 1584, 396, big=True)
    save_quote()
    save_icons()
    for f in sorted(os.listdir(DOCS)):
        if f.endswith((".png", ".svg")) or f == "social":
            print("  docs/" + f)
    print("Соцсети:")
    for f in sorted(os.listdir(SOCIAL)):
        print("  docs/social/" + f)


if __name__ == "__main__":
    main()
