#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Технический SEO/социальный аудит статического сайта Fonotext (docs/).

Проверяет каждый HTML-файл в docs/ по чек-листу: мета-теги, Open Graph, Twitter Card,
структурированные данные, заголовки, доступность, скорость, индексируемость.

Запуск:
    python3 tools/site-audit.py                # краткий отчёт в stdout
    python3 tools/site-audit.py --full         # все проверки, включая информационные
    python3 tools/site-audit.py --out docs/_audit/site-audit.md   # выгрузить отчёт

Зависимостей нет — только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SITE = "https://bestdeejay-design.github.io/fonotext/"

OK, WARN, FAIL, INFO = "✅", "⚠️", "❌", "ℹ️"


class Page(HTMLParser):
    """Собирает факты о странице: теги, атрибуты, текст."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metas = []
        self.links = []          # (rel, href, extra)
        self.headings = []       # (level, text)
        self.imgs = []           # (src, alt)
        self.anchors = []        # (href, text, target, rel)
        self.scripts = []        # (src|None, inline_len)
        self.stylesheets = []
        self.jsonld = []
        self.forms = {"inputs": 0, "labelled": 0, "ranges": 0, "ranges_labelled": 0}
        self.title = ""
        self.lang = None
        self.has_main = False
        self.has_skip_link = False
        self.text_parts = []
        self._in = {}
        self._buf = []
        self._cur_link = None
        self._cur_script = None
        self._pending_label_for = set()
        self._heading = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._in[tag] = self._in.get(tag, 0) + 1
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta":
            self.metas.append((a.get("name") or a.get("property") or a.get("charset") or "", a.get("content", "")))
        elif tag == "link":
            self.links.append((a.get("rel", ""), a.get("href", ""), a))
        elif tag in ("h1", "h2", "h3", "h4"):
            self._heading = (int(tag[1]), [])
            self.headings.append(self._heading)
        elif tag == "img":
            self.imgs.append((a.get("src", ""), a.get("alt")))
        elif tag == "a":
            self._cur_link = [a.get("href", ""), [], a.get("target"), a.get("rel"), a.get("aria-label")]
        elif tag == "script":
            self._cur_script = []
            if a.get("type") == "application/ld+json":
                self._jsonld_buf = []
                self._in["ldjson"] = 1
            if a.get("src"):
                self.scripts.append((a["src"], 0))
        elif tag == "style":
            self.stylesheets.append("inline")
        elif tag == "main":
            self.has_main = True
        elif tag == "input":
            self.forms["inputs"] += 1
            if a.get("type") == "range":
                self.forms["ranges"] += 1
                if a.get("aria-label"):
                    self.forms["ranges_labelled"] += 1
            if a.get("id") and a.get("id") in self._pending_label_for:
                self.forms["labelled"] += 1
        elif tag == "label":
            if a.get("for"):
                self._pending_label_for.add(a["for"])

    def handle_endtag(self, tag):
        if tag in self._in:
            self._in[tag] -= 1
        if tag == "a" and self._cur_link:
            self.anchors.append((self._cur_link[0], "".join(self._cur_link[1]).strip(),
                                 self._cur_link[2], self._cur_link[3], self._cur_link[4]))
            self._cur_link = None
        if tag == "script":
            if self._cur_script is not None:
                self.scripts.append((None, sum(len(x) for x in self._cur_script)))
                self._cur_script = None
            if "ldjson" in self._in and self._in["ldjson"]:
                self.jsonld.append("".join(getattr(self, "_jsonld_buf", [])))
                self._in["ldjson"] = 0
        if tag in ("h1", "h2", "h3", "h4") and self._heading:
            self._heading = None

    def handle_data(self, data):
        if self._cur_link is not None:
            self._cur_link[1].append(data)
        if self._cur_script is not None:
            self._cur_script.append(data)
        if self._in.get("ldjson"):
            self._jsonld_buf.append(data)
        if self._heading:
            self._heading[1].append(data)
        if self._in.get("title"):
            self.title += data
        if not any(self._in.get(t) for t in ("script", "style")):
            self.text_parts.append(data)

    @property
    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()

    def meta(self, key, prop=False):
        for k, v in self.metas:
            if k.lower() == key.lower():
                return v
        return None


UTILITY_PAGES = {"404.html"}


def check_page(path: str) -> tuple[list, dict]:
    name = os.path.basename(path)
    utility = name in UTILITY_PAGES
    raw = open(path, encoding="utf-8").read()
    p = Page()
    p.feed(raw)
    findings = []
    add = lambda level, area, msg: findings.append((level, area, msg))

    # --- индексируемость и базовое ---
    if not p.lang:
        add(FAIL, "HTML", "нет атрибута lang у <html>")
    elif not p.lang.lower().startswith("ru"):
        add(WARN, "HTML", f"lang={p.lang} (ожидается ru)")
    else:
        add(OK, "HTML", f"lang={p.lang}")

    title = (p.title or "").strip()
    if not title:
        add(FAIL, "Заголовок", "нет <title>")
    elif len(title) < 30:
        add(WARN, "Заголовок", f"{len(title)} симв. — коротко: «{title}»")
    elif len(title) > 65:
        add(WARN, "Заголовок", f"{len(title)} симв. — обрежется в выдаче (норма ≤ 60): «{title}»")
    else:
        add(OK, "Заголовок", f"{len(title)} симв.: «{title}»")

    desc = p.meta("description") or ""
    if not desc:
        add(FAIL, "Description", "нет мета-description")
    elif not (110 <= len(desc) <= 165):
        add(WARN, "Description", f"{len(desc)} симв. — норма 120–160")
    else:
        add(OK, "Description", f"{len(desc)} симв.")

    robots = (p.meta("robots") or "").lower()
    if utility:
        if "noindex" in robots:
            add(OK, "Индексация", "служебная страница закрыта noindex — корректно")
        else:
            add(WARN, "Индексация", "служебная страница без noindex")
    elif "noindex" in robots:
        add(FAIL, "Индексация", "страница закрыта noindex")
    else:
        add(OK, "Индексация", "индексация разрешена" + (f" ({robots})" if robots else ""))

    canon = [href for rel, href, _ in p.links if "canonical" in rel]
    if utility and not canon:
        canon = ["https://bestdeejay-design.github.io/fonotext/"]  # условная заглушка
    if not canon:
        add(WARN, "Канонизация", "нет <link rel=canonical> — риск дублей")
    elif not canon[0].startswith("http"):
        add(WARN, "Канонизация", f"canonical относительный: {canon[0]}")
    else:
        add(OK, "Канонизация", canon[0])

    # --- заголовки ---
    h1 = [t for lvl, t in p.headings if lvl == 1]
    h1_text = ["".join(t).strip() for _, t in p.headings if _ == 1] if False else \
              [re.sub(r"\s+", " ", "".join(t)).strip() for lvl, t in p.headings if lvl == 1]
    if len(h1) == 0:
        add(FAIL, "Заголовки", "нет <h1>")
    elif len(h1) > 1:
        add(WARN, "Заголовки", f"{len(h1)} тега <h1> — должен быть один")
    else:
        add(OK, "Заголовки", f"h1: «{h1_text[0][:70]}»")
    levels = [lvl for lvl, _ in p.headings]
    jumps = [f"h{levels[i]}→h{levels[i+1]}" for i in range(len(levels) - 1) if levels[i + 1] - levels[i] > 1]
    if jumps:
        add(WARN, "Заголовки", f"перескок уровней: {', '.join(set(jumps))}")
    else:
        add(OK, "Заголовки", f"иерархия без перескоков ({len(p.headings)} заголовков)")

    # --- OG / Twitter ---
    og = {k: v for k, v in p.metas if k.lower().startswith("og:")}
    og_required = ["og:title", "og:description", "og:type", "og:url", "og:image"]
    missing = [k for k in og_required if k not in og]
    if utility:
        missing = []
    if missing:
        add(FAIL, "Open Graph", "нет обязательных: " + ", ".join(missing))
    else:
        add(OK, "Open Graph", f"{len(og)} тегов, включая image")
    for k in ("og:image", "og:url"):
        if k in og and not og[k].startswith("http"):
            add(FAIL, "Open Graph", f"{k} должен быть абсолютным URL: {og[k]}")
    if not utility and ("og:image:width" not in og or "og:image:height" not in og):
        add(WARN, "Open Graph", "не указаны размеры og:image — превью может обрезаться")
    if not utility and "og:image:alt" not in og:
        add(WARN, "Open Graph", "нет og:image:alt (нужен для доступности)")

    tw = {k: v for k, v in p.metas if k.lower().startswith("twitter:")}
    tw_card = tw.get("twitter:card")
    if utility:
        tw_card = None  # служебная страница: Twitter Card не требуется
    if tw_card is None and utility:
        pass
    elif not tw_card:
        add(WARN, "Twitter Card", "нет twitter:card")
    elif tw_card != "summary_large_image":
        add(WARN, "Twitter Card", f"card={tw_card} (для картинок нужен summary_large_image)")
    else:
        need = [k for k in ("twitter:title", "twitter:description", "twitter:image") if k not in tw]
        if need:
            add(WARN, "Twitter Card", "нет: " + ", ".join(need))
        else:
            add(OK, "Twitter Card", "summary_large_image настроен")

    # --- структурированные данные ---
    if utility:
        pass
    elif not p.jsonld:
        add(WARN, "JSON-LD", "нет структурированных данных (Schema.org)")
    else:
        types = []
        broken = 0
        for blob in p.jsonld:
            try:
                data = json.loads(blob)
            except Exception:
                broken += 1
                continue
            items = data if isinstance(data, list) else data.get("@graph", [data])
            for it in items:
                if isinstance(it, dict) and it.get("@type"):
                    types.append(it["@type"] if isinstance(it["@type"], str) else ",".join(it["@type"]))
        if broken:
            add(FAIL, "JSON-LD", f"{broken} блок(ов) с невалидным JSON")
        if types:
            add(OK, "JSON-LD", "типы: " + ", ".join(sorted(set(types))))

    # --- скорость ---
    ext_css = [href for rel, href, _ in p.links if "stylesheet" in rel and href.startswith("http")]
    ext_js = [src for src, _ in p.scripts if src and src.startswith("http")]
    inline_js = sum(n for src, n in p.scripts if src is None)
    size_kb = len(raw.encode("utf-8")) / 1024
    if ext_css or ext_js:
        add(WARN, "Скорость", f"внешние ресурсы: {len(ext_css)} CSS, {len(ext_js)} JS — блокируют рендер")
    else:
        add(OK, "Скорость", f"нет внешних ресурсов; {size_kb:.0f} КБ HTML, JS внутри {inline_js/1024:.0f} КБ")
    if size_kb > 150:
        add(WARN, "Скорость", f"HTML {size_kb:.0f} КБ — тяжеловато для одной страницы")
    for m in (p.meta("theme-color"),):
        if not m:
            add(INFO, "Мобильные", "нет theme-color")

    # --- доступность ---
    imgs_no_alt = [s for s, alt in p.imgs if alt is None]
    if p.imgs and imgs_no_alt:
        add(WARN, "Доступность", f"{len(imgs_no_alt)} изображений без alt")
    elif p.imgs:
        add(OK, "Доступность", f"все {len(p.imgs)} изображений с alt")
    if not p.has_main:
        add(WARN, "Доступность", "нет семантического <main>")
    if p.forms["ranges"] and p.forms["ranges_labelled"] < p.forms["ranges"]:
        add(WARN, "Доступность", f"ползунки без aria-label: {p.forms['ranges'] - p.forms['ranges_labelled']}")
    elif p.forms["ranges"]:
        add(OK, "Доступность", f"все {p.forms['ranges']} ползунков подписаны (aria-label)")
    empty_links = [a for a in p.anchors if not a[1] and a[0]]
    if empty_links:
        add(WARN, "Доступность", f"{len(empty_links)} ссылок без текста (icon-only?) — нужен aria-label")
    unsafe = [h for h, t, target, rel, _ in p.anchors if target == "_blank" and (not rel or "noopener" not in rel)]
    if unsafe:
        add(WARN, "Безопасность", f"{len(unsafe)} ссылок target=_blank без rel=noopener")
    elif any(t == "_blank" for _, _, t, _, _ in p.anchors):
        add(OK, "Безопасность", "внешние ссылки с rel=noopener")
    for h, t, target, rel, aria in p.anchors:
        if target == "_blank" and rel and "nofollow" not in rel and h.startswith("http") and "github.com" not in h:
            add(INFO, "Ссылки", f"внешняя ссылка без nofollow: {h[:60]}")

    # --- og:image существует физически? ---
    for key in ("og:image", "twitter:image"):
        url = og.get(key) if key.startswith("og:") else tw.get(key)
        if not url:
            continue
        base = os.path.dirname(path)
        if url.startswith(SITE):
            rel = url[len(SITE):]
            candidate = os.path.join(DOCS, rel) if rel else None
            if candidate and not os.path.exists(candidate):
                add(FAIL, "OG-изображение", f"{key} указывает на несуществующий файл: {rel}")
            elif candidate:
                add(OK, "OG-изображение", f"{key} → {rel} (файл есть)")

    # --- битые внутренние ссылки ---
    dead = []
    for href, text, target, rel, aria in p.anchors:
        if not href or href.startswith(("http", "#", "mailto:", "tel:")):
            continue
        clean = href.split("#")[0].split("?")[0]
        if not clean:
            continue
        candidate = os.path.normpath(os.path.join(os.path.dirname(path), clean))
        if candidate.endswith(os.sep) or os.path.isdir(candidate):
            candidate = os.path.join(candidate, "index.html")
        if not os.path.exists(candidate):
            dead.append(href)
    if dead:
        add(FAIL, "Внутренние ссылки", f"{len(dead)} битых: " + ", ".join(sorted(set(dead))[:5]))
    else:
        add(OK, "Внутренние ссылки", f"все относительные ссылки ведут на существующие файлы")

    # --- контент ---
    words = len(p.text.split())
    if utility:
        add(OK, "Контент", f"служебная страница, {words} слов")
    elif words < 300:
        add(WARN, "Контент", f"{words} слов на странице — маловато для поискового трафика")
    else:
        add(OK, "Контент", f"{words} слов видимого текста")

    stats = {
        "file": name, "title": title, "desc_len": len(desc), "words": words,
        "size_kb": round(size_kb, 1), "h1": len(h1), "og": len(og), "jsonld_types": len(set()),
        "internal_links": sum(1 for h, *_ in p.anchors if h and not h.startswith(("http", "#"))),
        "external_links": sum(1 for h, *_ in p.anchors if h.startswith("http")),
        "fails": sum(1 for lvl, *_ in findings if lvl == FAIL),
        "warns": sum(1 for lvl, *_ in findings if lvl == WARN),
    }
    return findings, stats


def check_site_level(html_files: list) -> list:
    findings = []
    add = lambda level, area, msg: findings.append((level, area, msg))
    if os.path.exists(os.path.join(DOCS, "robots.txt")):
        txt = open(os.path.join(DOCS, "robots.txt"), encoding="utf-8").read()
        add(OK if "Sitemap:" in txt else WARN, "robots.txt",
            "есть Sitemap" if "Sitemap:" in txt else "есть, но без ссылки на Sitemap")
    else:
        add(FAIL, "robots.txt", "нет файла — поисковики не увидят карту сайта")
    if os.path.exists(os.path.join(DOCS, "sitemap.xml")):
        sm = open(os.path.join(DOCS, "sitemap.xml"), encoding="utf-8").read()
        urls = sm.count("<url>")
        add(OK, "sitemap.xml", f"{urls} URL")
        listed = set(re.findall(r"<loc>([^<]+)</loc>", sm))
        for f in html_files:
            if f == "index.html":
                url = SITE
            elif f.endswith("/index.html"):
                url = SITE + f[:-len("index.html")]
            else:
                url = SITE + f
            if f != "404.html" and url not in listed:
                add(WARN, "sitemap.xml", f"{f} не указан в карте сайта")
    else:
        add(FAIL, "sitemap.xml", "нет карты сайта")
    if os.path.exists(os.path.join(DOCS, "404.html")):
        add(OK, "404", "кастомная страница ошибки есть")
    else:
        add(WARN, "404", "нет кастомной 404 (упущенная возможность вернуть посетителя)")
    if os.path.exists(os.path.join(DOCS, "og-image.png")):
        add(OK, "OG-изображение", "og-image.png на месте")
    else:
        add(FAIL, "OG-изображение", "нет файла для превью в соцсетях")
    if os.path.exists(os.path.join(DOCS, ".nojekyll")):
        add(OK, "GitHub Pages", ".nojekyll — Jekyll не трогает статику")
    if os.path.exists(os.path.join(DOCS, "site.webmanifest")):
        add(OK, "PWA", "site.webmanifest есть")
    else:
        add(INFO, "PWA", "нет webmanifest (иконка на домашнем экране)")
    md = [f for f in os.listdir(DOCS) if f.endswith(".md")]
    add(INFO, "Контент-стратегия",
        f"{len(md)} markdown-документов в docs/: GitHub Pages отдаёт их как текст, "
        "а не как HTML — для поискового трафика нужны HTML-страницы (см. docs/12-seo.md)")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="показывать информационные пункты")
    ap.add_argument("--out", help="куда сохранить отчёт (markdown)")
    args = ap.parse_args()

    html_files = []
    for dirpath, _dirs, files in os.walk(DOCS):
        for f in sorted(files):
            if f.endswith(".html"):
                html_files.append(os.path.relpath(os.path.join(dirpath, f), DOCS).replace(os.sep, "/"))
    html_files.sort()
    lines = ["# Технический аудит сайта Fonotext", "",
             f"Сайт: {SITE} · проверено страниц: {len(html_files)}", ""]
    total_fail = total_warn = 0
    for f in html_files:
        findings, stats = check_page(os.path.join(DOCS, f))
        total_fail += stats["fails"]
        total_warn += stats["warns"]
        lines.append(f"## {f}")
        lines.append(f"_{stats['words']} слов · {stats['size_kb']} КБ · внутренних ссылок "
                     f"{stats['internal_links']} · внешних {stats['external_links']}_")
        lines.append("")
        for level, area, msg in findings:
            if level == INFO and not args.full:
                continue
            lines.append(f"- {level} **{area}** — {msg}")
        lines.append("")
    site_findings = check_site_level(html_files)
    lines.append("## Уровень сайта")
    lines.append("")
    for level, area, msg in site_findings:
        if level == INFO and not args.full:
            continue
        lines.append(f"- {level} **{area}** — {msg}")
        if level == FAIL:
            total_fail += 1
        elif level == WARN:
            total_warn += 1
    lines.append("")
    lines.append(f"**Итого:** критичных — {total_fail}, предупреждений — {total_warn}")
    lines.append("")
    report = "\n".join(lines)

    print(report)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"\nОтчёт сохранён: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
