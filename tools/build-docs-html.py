#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка HTML-версий документации Fonotext из markdown-файлов.

Зачем: GitHub Pages отдаёт .md как простой текст (text/plain) — без навигации, стилей и CTA.
Плюс ссылки на github.com/<repo>/blob/main/... дают 404, пока работа не влита в main.
Решение: генерируем настоящие HTML-страницы на сайте, со своими title/description/OG/JSON-LD,
навигацией, оглавлением и футером с реквизитами правообладателя.

Запуск:
    python3 tools/build-docs-html.py            # собрать страницы + sitemap.xml
    python3 tools/build-docs-html.py --dry-run  # показать, что будет собрано

Особенности:
  * markdown-парсер на стандартной библиотеке (заголовки, таблицы, списки, код, цитаты, ссылки);
  * перелинковка: (.md → .html), README.md → index.html, внешние ссылки без изменений;
  * якоря заголовков совместимы с GitHub (кириллица сохраняется), чтобы внутренние ссылки работали;
  * оглавление, хлебные крошки, «предыдущий/следующий» документ, ссылка на исходный markdown.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SITE = "https://bestdeejay-design.github.io/fonotext/"
REPO = "https://github.com/bestdeejay-design/fonotext"
TODAY = "2026-10-03"

LEGAL = {
    "holder": "ООО «Аксиома»",
    "inn": "7842223709",
    "ogrn": "1247800067690",
    "address": "192029, г. Санкт-Петербург, ул. Профессора Качалова, д. 15А, литера А",
    "email": "hello@axiiom.ru",
    "phone": "+7 (812) 928-74-78",
    "site": "https://axiiom.ru",
}

# документы, которые публикуются как HTML (порядок = порядок в навигации)
PUBLISH = [
    ("01-integration.md", "Интеграция и анкета подключения к АТС",
     "Как Fonotext подключается к системе записи заказчика: REST, вебхуки, S3/SFTP, форматы аудио, анкета из семи блоков на 20 минут."),
    ("02-architecture.md", "Архитектура: пайплайн, стек, безопасность",
     "Компоненты Fonotext, поток обработки звонка, режимы live и backfill, переклассификация без ASR, безопасность и карта рисков с митигациями."),
    ("03-models.md", "Модели распознавания и методика оценки качества",
     "Кандидаты ASR (Whisper, GigaAM, T-one, Parakeet), лицензии, выбор LLM для классификации, методика замера WER и вердикты, которые фиксирует пилот."),
    ("04-hardware.md", "Мощности и стоимость обработки минуты",
     "Сколько часов аудио берёт одна карта в сутки, почему мы арендуем GPU вместо покупки, автоскейл и прерываемые инстансы, расчёт парка под ваш объём."),
    ("05-poc-plan.md", "План пилота: измерение качества на ваших данных",
     "Что делаем за 2–4 недели пилота, какие метрики считаем (WER по слоям, F1 классов), критерии Go/No-Go и стоимость участия."),
    ("06-pricing.md", "Цены и тарифы: подписки, API и on-prem",
     "Прайс v2.0: API-транскрибация 0,85–1,50 ₽/мин, подписки с включёнными минутами, коробка on-prem, разбор архива от 0,38 ₽/мин и правила скидок."),
    ("07-deployment.md", "Поставка, внедрение и безопасность",
     "Три сценария поставки Fonotext, требования к инфраструктуре, процесс внедрения за 4–8 недель, соответствие 152-ФЗ и состав поддержки."),
    ("08-api.md", "Спецификация API v1: загрузка и вебхуки",
     "Асинхронный REST API Fonotext: отправка звонка, статусы, поля результата, вебхуки с HMAC-подписью, лимиты, ошибки и логика тарификации."),
    ("09-competitive-landscape.md", "Конкурентный анализ: цены и позиционирование",
     "Объём рынка речевой аналитики РФ, четыре группы конкурентов с публичными ценами и источниками, функциональное сравнение и честные слабые места Fonotext."),
    ("10-feature-specs/README.md", "Спецификации фич: 8 отличий от рынка",
     "Спецификации восьми функций Fonotext: аудит 100% звонков, конструктор таксономии, доказательная проверка скриптов, архив, приватный контур, LLM-аналитик."),
]
FEATURE_DOCS = [
    ("10-feature-specs/01-full-coverage.md", "Аудит 100% звонков без повторного ASR",
     "Почему выборочное прослушивание 1–7% звонков не работает, как классифицируются все записи и как переклассификация идёт за часы без нового распознавания."),
    ("10-feature-specs/02-taxonomy-builder.md", "Конструктор таксономии и правил без релиза",
     "Как бизнес сам описывает нужные сценарии разговора — правила, примеры, пороги — и получает новую таксономию за дни, без разработки и повторной расшифровки."),
    ("10-feature-specs/03-script-evidence.md", "Контроль скриптов с доказательной базой",
     "Каждое нарушение скрипта подтверждено цитатой, таймкодом и каналом: оператор видит доказательство, может оспорить, спорный звонок уходит в ручной разбор."),
    ("10-feature-specs/04-archive.md", "Архив под ключ: разбор накопленных записей",
     "Что делать с архивом 50–500 тысяч часов: этапы конвейера, сроки, фикс-цена от 0,38 ₽/мин за минуту аудио и отчёт о том, что в записях нашлось."),
    ("10-feature-specs/05-private-shard.md", "Приватный контур на аренде (managed private)",
     "Выделенный шард с своими ключами и хранилищем в РФ, без капзатрат на коробку: кому нужен, как устроена изоляция, чем отличается от on-prem по цене и срокам."),
    ("10-feature-specs/06-ask-your-calls.md", "LLM-аналитик: «спросите свои звонки»",
     "Вопрос к базе разговоров обычными словами — с ответом, цифрами и ссылками на конкретные звонки: как работают ограничения доступа и почему ответы проверяемы."),
    ("10-feature-specs/07-quality-drift.md", "Мониторинг качества и дрейфа моделей",
     "Мы публикуем точность на ваших записях и следим за её изменением во времени: эталонный набор, метрики по слоям, пороги алертов и план деградации ASR."),
    ("10-feature-specs/08-alerts-actions.md", "Алерты и автодействия: отчёт приходит вовремя",
     "Тревоги по событиям разговора и автодействия — письмо руководителю, задача в CRM, блокировка звонка: как настраиваются правила, каналы и защита от ложных срабатываний."),
]

# ---------------------------------------------------------------- markdown → html

def slugify(text: str) -> str:
    """Якорь в стиле GitHub: кириллица сохраняется, пунктуация вырезается."""
    t = re.sub(r"<[^>]+>", "", text)
    t = t.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t.strip())
    return t or "section"


def inline(text: str) -> str:
    """Инлайн-разметка: код, жирный, курсив, ссылки."""
    stash: list[str] = []

    def keep(html_snippet: str) -> str:
        stash.append(html_snippet)
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: keep(f'<a href="{m.group(2)}">{m.group(1)}</a>'), text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = text.replace("&lt;br/&gt;", "<br>").replace("&lt;br&gt;", "<br>")
    def restore(m):
        return stash[int(m.group(1))]
    return re.sub(r"\x00(\d+)\x00", restore, text)


def md_to_html(md: str, page_dir: str, link_map: dict, drop_first_h1: bool = True) -> tuple[str, list, str | None]:
    """Возвращает (html, оглавление, заголовок h1 из markdown)."""
    lines = md.split("\n")
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    i = 0
    used_anchors: dict[str, int] = {}
    doc_h1: str | None = None

    def fix_link(url: str) -> str:
        if url.startswith(("http", "#", "mailto:", "tel:")):
            return url
        path, _, anchor = url.partition("#")
        if path.endswith(".md"):
            target_abs = os.path.normpath(os.path.join(DOCS, page_dir, path))
            target = target_abs
            target_rel = os.path.relpath(target_abs, DOCS).replace(os.sep, "/")
            if target_rel.startswith(".."):
                # файл вне docs/ (например local-poc/README.md) — ведём на GitHub
                repo_rel = os.path.relpath(target_abs, ROOT).replace(os.sep, "/")
                return f"{REPO}/blob/main/{repo_rel}" + (("#" + anchor) if anchor else "")
            if target_rel in link_map:
                # приводим путь к виду относительно текущей страницы
                new = os.path.relpath(os.path.join(DOCS, link_map[target_rel]),
                                      os.path.join(DOCS, page_dir)).replace(os.sep, "/")
            else:
                new = path[:-3] + ".html"  # не публикуется — оставляем рядом (файл есть на Pages)
            return new + (("#" + anchor) if anchor else "")
        return url

    def add_anchor(title_html: str) -> str:
        base = slugify(title_html)
        n = used_anchors.get(base, 0)
        used_anchors[base] = n + 1
        return base if n == 0 else f"{base}-{n}"

    while i < len(lines):
        line = lines[i]

        # код-блок
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>")
            continue

        # таблица
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="table-scroll"><table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></div>')
            continue

        # заголовки
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if level == 1 and drop_first_h1 and doc_h1 is None:
                doc_h1 = re.sub(r"\*\*", "", title)  # свой h1 у страницы уже есть в шаблоне
                i += 1
                continue
            anchor = add_anchor(title)
            title_html = inline(title)
            if level > 1:
                toc.append((level, re.sub(r"<[^>]+>", "", title_html), anchor))
            out.append(f'<h{level} id="{anchor}">{title_html}</h{level}>')
            i += 1
            continue

        # горизонтальная линия
        if re.match(r"^\s*---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # цитата
        if line.strip().startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(buf)) + "</blockquote>")
            continue

        # списки
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            body = "".join(f"<li>{inline(x)}</li>" for x in items)
            out.append(f"<{tag}>{body}</{tag}>")
            continue

        # пустая строка
        if not line.strip():
            i += 1
            continue

        # абзац
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|\s*[-*]\s|\s*\d+\.\s|>|\s*```|\s*\||\s*---+\s*$)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")

    html_body = "\n".join(out)
    html_body = re.sub(r'href="([^"]+)"',
                       lambda m: 'href="%s"' % fix_link(m.group(1)), html_body)
    return html_body, toc, doc_h1


# ---------------------------------------------------------------- шаблон страницы

def page_shell(*, url_path: str, title: str, description: str, body: str, toc: list,
               breadcrumbs: list, prev_doc=None, next_doc=None, markdown_name: str | None,
               up_prefix: str, h1: str | None = None) -> str:
    toc_html = ""
    if toc:
        items = "".join(
            f'<li class="lvl{lvl}"><a href="#{anchor}">{html.escape(title_)}</a></li>'
            for lvl, title_, anchor in toc if lvl <= 3)
        toc_html = f'<nav class="toc" aria-label="Содержание"><b>Содержание</b><ul>{items}</ul></nav>'

    crumb_html = ""
    if breadcrumbs:
        parts = []
        for name, url in breadcrumbs:
            parts.append(f'<a href="{url}">{name}</a>' if url else f"<span>{name}</span>")
        crumb_html = '<nav class="crumbs" aria-label="Хлебные крошки">' + " › ".join(parts) + "</nav>"

    nav_html = ""
    if prev_doc or next_doc:
        left = (f'<a class="pn prev" href="{prev_doc[1]}">← {html.escape(prev_doc[0])}</a>'
                if prev_doc else "<span></span>")
        right = (f'<a class="pn next" href="{next_doc[1]}">{html.escape(next_doc[0])} →</a>'
                 if next_doc else "<span></span>")
        nav_html = f'<div class="pager">{left}{right}</div>'

    md_link = ""
    if markdown_name:
        md_link = f'<a class="md" href="{markdown_name}">Исходный markdown</a>'

    canonical = SITE + url_path
    og_image = SITE + "og-image.png"
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "TechArticle",
                "headline": title,
                "description": description,
                "url": canonical,
                "inLanguage": "ru-RU",
                "datePublished": TODAY,
                "dateModified": TODAY,
                "image": og_image,
                "author": {"@type": "Organization", "name": LEGAL["holder"], "url": LEGAL["site"]},
                "publisher": {
                    "@type": "Organization",
                    "name": LEGAL["holder"],
                    "url": LEGAL["site"],
                    "logo": {"@type": "ImageObject", "url": SITE + "icon-512.png"},
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": n, "name": name, "item": (SITE + u) if u else canonical}
                    for n, (name, u) in enumerate(
                        [(n, u) for n, u in breadcrumbs] + [(title, "")], start=1)
                ],
            },
        ],
    }

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — Fonotext</title>
<meta name="description" content="{html.escape(description)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#4F46E5">

<meta property="og:type" content="article">
<meta property="og:site_name" content="Fonotext">
<meta property="og:locale" content="ru_RU">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{html.escape(title)} — Fonotext">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Fonotext — речевая аналитика телефонных разговоров">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title)} — Fonotext">
<meta name="twitter:description" content="{html.escape(description)}">
<meta name="twitter:image" content="{og_image}">

<link rel="icon" href="{up_prefix}favicon.svg" type="image/svg+xml">
<link rel="icon" href="{up_prefix}icon-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="{up_prefix}apple-touch-icon.png">
<link rel="manifest" href="{up_prefix}site.webmanifest">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
<style>
  :root{{--accent:#4F46E5;--accent-2:#7C3AED;--ink:#0F172A;--muted:#55617A;--line:#E5E8F0;--soft:#F6F7FB;--ok:#0E9F6E}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Inter",Arial,sans-serif;color:var(--ink);
       line-height:1.68;-webkit-font-smoothing:antialiased}}
  a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
  header{{border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(255,255,255,.95);
          backdrop-filter:blur(8px);z-index:20}}
  .nav{{display:flex;align-items:center;gap:14px;height:60px;max-width:1100px;margin:0 auto;padding:0 24px}}
  .brand{{display:flex;align-items:center;gap:9px;font-weight:800;font-size:18px;color:var(--ink)}}
  .nav .links{{margin-left:auto;display:flex;gap:18px;font-size:14.5px}}
  .nav .links a{{color:var(--muted)}}
  .nav .links a:hover{{color:var(--accent)}}
  .layout{{max-width:1100px;margin:0 auto;padding:26px 24px 60px;display:grid;
           grid-template-columns:250px minmax(0,1fr);gap:44px;align-items:start}}
  .crumbs{{font-size:13.5px;color:var(--muted);margin-bottom:14px}}
  h1{{font-size:clamp(26px,3.6vw,38px);line-height:1.16;letter-spacing:-.02em;font-weight:800;margin-bottom:18px}}
  h2{{font-size:25px;letter-spacing:-.015em;margin:40px 0 12px;padding-top:6px}}
  h3{{font-size:19px;margin:26px 0 8px}}
  h4{{font-size:17px;margin:20px 0 6px}}
  p,li{{font-size:16.5px;color:#26314E}}
  p{{margin-bottom:14px}}
  ul,ol{{margin:0 0 16px 24px}}li{{margin-bottom:7px}}
  strong{{color:var(--ink)}}
  code{{background:#EEF0FE;border-radius:5px;padding:1px 5px;font-size:14.5px;
        font-family:"SF Mono",ui-monospace,Menlo,Consolas,monospace;color:#3730A3}}
  pre{{background:#0B1020;color:#DCE3F5;border-radius:14px;padding:18px;overflow:auto;margin:16px 0;font-size:13.5px;line-height:1.6}}
  pre code{{background:none;color:inherit;padding:0}}
  blockquote{{border-left:3px solid var(--accent);background:var(--soft);border-radius:0 10px 10px 0;
              padding:12px 18px;margin:16px 0;color:#2A3350;font-size:16px}}
  hr{{border:none;border-top:1px solid var(--line);margin:30px 0}}
  .table-scroll{{overflow-x:auto;margin:18px 0}}
  table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);
         border-radius:12px;overflow:hidden;font-size:15px}}
  th,td{{padding:11px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
  th{{background:#FAFBFF;font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
  tr:last-child td{{border-bottom:none}}
  .toc{{position:sticky;top:78px;background:#fff;border:1px solid var(--line);border-radius:12px;
        padding:16px 18px;font-size:14.5px}}
  .toc b{{display:block;margin-bottom:8px;font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
  .toc ul{{list-style:none;margin:0}}
  .toc li{{margin:0 0 5px}}
  .toc .lvl3{{padding-left:14px;font-size:13.8px}}
  .toc a{{color:#2A3350}}
  .toc a:hover{{color:var(--accent)}}
  .pager{{display:flex;justify-content:space-between;gap:14px;margin-top:44px;padding-top:20px;
          border-top:1px solid var(--line);font-size:15px}}
  .md{{display:inline-block;margin-top:22px;font-size:14px;color:var(--muted)}}
  .cta{{background:linear-gradient(100deg,#4F46E5,#7C3AED);border-radius:16px;padding:22px 26px;
        margin:36px 0 0;color:#fff;display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}}
  .cta b{{font-size:18px}}
  .cta a{{background:#fff;color:#4F46E5;padding:11px 20px;border-radius:10px;font-weight:600;font-size:15px}}
  footer{{border-top:1px solid var(--line);background:var(--soft);padding:30px 0;font-size:14.5px;color:var(--muted)}}
  footer .wrap{{max-width:1100px;margin:0 auto;padding:0 24px}}
  footer a{{color:var(--accent)}}
  @media(max-width:900px){{.layout{{grid-template-columns:1fr}}.toc{{position:static;order:-1}}}}
</style>
</head>
<body>

<header>
  <div class="nav">
    <a class="brand" href="{up_prefix}">
      <svg width="24" height="24" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#4F46E5"/><path d="M7 16h2m3-6v12m3-9v6m3-9v12m3-6h2" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/></svg>
      Fonotext
    </a>
    <div class="links">
      <a href="{up_prefix}#pricing">Цены</a>
      <a href="{up_prefix}#roi">Калькулятор</a>
      <a href="{up_prefix}rechevaya-analitika/">Речевая аналитика</a>
    </div>
  </div>
</header>

<main class="layout">
  <aside>{toc_html}</aside>
  <article>
    {crumb_html}
    <h1>{html.escape(h1 or title)}</h1>
    {body}
    {md_link}
    {nav_html}
    <div class="cta">
      <b>300 минут бесплатно и пилот на ваших записях</b>
      <a href="{up_prefix}#pricing">Подключиться</a>
    </div>
  </article>
</main>

<footer>
  <div class="wrap">
    <p><b>Fonotext</b> — речевая аналитика телефонных разговоров: 100% покрытие звонков, спикеры по
    каналам записи, контроль скриптов с доказательствами, разбор архива. Обработка и хранение
    данных — на территории РФ (152-ФЗ).</p>
    <p style="margin-top:8px">© 2026 {LEGAL['holder']} ({LEGAL['ogrn']}). Проект Fonotext ·{' '}
      <a href="{LEGAL['site']}" target="_blank" rel="noopener">axiiom.ru</a> ·
      <a href="mailto:{LEGAL['email']}">{LEGAL['email']}</a> ·
      <a href="tel:{LEGAL['phone'].replace(' ', '').replace('(', '').replace(')', '')}">{LEGAL['phone']}</a></p>
    <p style="margin-top:10px">Версия документа: 3 октября 2026 г. (прайс v2.0). Не видите
    последних изменений — обновите страницу с очисткой кэша (Ctrl+F5).</p>
    <p style="margin-top:10px">
      <a href="{up_prefix}">Главная</a> ·
      <a href="{up_prefix}dokumentaciya/">Документация</a> ·
      <a href="{SITE}06-pricing.html">Цены</a> ·
      <a href="{SITE}05-poc-plan.html">План пилота</a> ·
      <a href="{SITE}09-competitive-landscape.html">Сравнение с рынком</a> ·
      <a href="{REPO}" target="_blank" rel="noopener">GitHub</a>
    </p>
  </div>
</footer>

</body>
</html>
"""


# ---------------------------------------------------------------- сборка

def build(dry_run: bool = False) -> list:
    all_docs = PUBLISH + FEATURE_DOCS
    # карта: путь markdown (от docs/) → путь html (от docs/)
    link_map = {}
    for path, _title, *_ in all_docs:
        out = path[:-3] + ".html"
        if os.path.basename(out) == "README.html":
            out = os.path.join(os.path.dirname(out), "index.html")
        link_map[path] = out
    link_map["rechevaya-analitika/README.md"] = "rechevaya-analitika/index.html"

    built = []
    for idx, doc in enumerate(all_docs):
        path, title = doc[0], doc[1]
        description = doc[2] if len(doc) > 2 else (
            f"{title}. Документация Fonotext: речевая аналитика телефонных разговоров, "
            "разбор архива, приватный контур, цены и API.")
        src = os.path.join(DOCS, path)
        if not os.path.exists(src):
            print(f"  ! пропущен (нет файла): {path}", file=sys.stderr)
            continue
        md = open(src, encoding="utf-8").read()
        page_dir = os.path.dirname(path) or "."
        body, toc, doc_h1 = md_to_html(md, page_dir, link_map)
        page_title = title          # короткий заголовок для <title> и OG
        h1_text = doc_h1 or title   # h1 страницы — из документа
        if len(description) > 158:
            cut = description[:155].rsplit(" ", 1)[0].rstrip(" ,;:.")
            description = cut + "…"
        # уровень вложенности до корня docs/
        depth = path.count("/")
        up_prefix = "../" * depth if depth else ""
        out_rel = link_map[path]
        url_path = out_rel if not out_rel.endswith("index.html") else out_rel[:-len("index.html")]

        prev_doc = next_doc = None
        if idx > 0:
            p_path, p_title, *_ = all_docs[idx - 1]
            prev_doc = (p_title, os.path.relpath(link_map[p_path], page_dir).replace(os.sep, "/"))
        if idx < len(all_docs) - 1:
            n_path, n_title, *_ = all_docs[idx + 1]
            next_doc = (n_title, os.path.relpath(link_map[n_path], page_dir).replace(os.sep, "/"))

        crumbs = [("Fonotext", up_prefix or "./"), ("Документация", up_prefix + "dokumentaciya/"),
                  (page_title, "")]
        html_page = page_shell(
            url_path=url_path, title=page_title, h1=h1_text, description=description, body=body, toc=toc,
            breadcrumbs=crumbs, prev_doc=prev_doc, next_doc=next_doc,
            markdown_name=os.path.basename(path), up_prefix=up_prefix)

        dst = os.path.join(DOCS, out_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not dry_run:
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(html_page)
        built.append((out_rel, url_path, page_title, description, len(html_page)))
        print(f"  {'(dry) ' if dry_run else ''}{path} → docs/{out_rel} ({len(html_page)//1024} КБ)")

    if not dry_run:
        build_hub(link_map)
        build_sitemap(link_map)
    return built


def build_hub(link_map: dict) -> None:
    """Страница-каталог документации."""
    groups = [
        ("Начать работу", ["05-poc-plan.md", "01-integration.md", "06-pricing.md"]),
        ("Продукт и отличия", ["10-feature-specs/README.md"] + [d[0] for d in FEATURE_DOCS]),
        ("Технологии", ["02-architecture.md", "03-models.md", "04-hardware.md", "08-api.md"]),
        ("Поставка и безопасность", ["07-deployment.md"]),
        ("Рынок", ["09-competitive-landscape.md"]),
    ]
    titles = {p: t for p, t, *_ in PUBLISH}
    cards = []
    for group_name, paths in groups:
        items = []
        for p in paths:
            if p in link_map:
                href = os.path.relpath(link_map[p], "dokumentaciya").replace(os.sep, "/")
                name = titles.get(p, p)
                items.append(f'<li><a href="{href}">{html.escape(name)}</a></li>')
        cards.append(f'<div class="card"><h2>{html.escape(group_name)}</h2><ul>{"".join(items)}</ul></div>')

    lead = """
<p class="lead">Мы публикуем не маркетинговые обещания, а рабочие документы: методику пилота, архитектуру,
модели и качество, прайс, конкурентный анализ и спецификации фич. Их можно читать до первого
разговора с нами — и проверять нас по ним.</p>

<h2>Зачем мы показываем внутренние документы</h2>
<p>Речевая аналитика продаётся обещаниями: «внедрим и всё будет видно». На практике заказчик
получает три вопроса без ответа — как измерить качество распознавания на <em>его</em> записях,
сколько будет стоить минута после окончания пилота и что делать с архивом звонков, который
годами лежит без дела. Ответы на все три вопроса есть в документах ниже, с цифрами и формулами,
а не в разделе «преимущества».</p>
<p>Начните с <a href="../05-poc-plan.html">плана пилота</a>: там написано, как за две–четыре недели
получить измеренные метрики (WER по слоям записи, F1 по классам, полнота проверки скриптов) и при
каких значениях мы обе стороны говорим «идём дальше». Затем посмотрите
<a href="../06-pricing.html">цены</a> и <a href="../09-competitive-landscape.html">сравнение с рынком</a>
— в сравнении указаны публичные тарифы конкурентов и источники, по которым их можно проверить.
Если выбор поставщика ещё не сделан, полезен раздел «Шесть вопросов вендору» на странице
<a href="../rechevaya-analitika/index.html">«Речевая аналитика»</a>: их стоит задать всем
участникам тендера, включая нас.</p>

<h2>Что мы не публикуем</h2>
<p>Финансовую модель проекта и внутреннюю экономику поставки. Эти документы описывают нашу
себестоимость, структуру затрат и условия, на которых мы работаем с партнёрами; они передаются
заказчикам и инвесторам по запросу вместе с коммерческим предложением. Всё, что влияет на решение
заказчика — качество, сроки, цены, состав функций, — опубликовано здесь.</p>

<h2>Как читать документацию</h2>
<p>Документы идут от прикладного к техническому: пилот и подключение, затем продукт и отличия,
затем технологии, поставка и безопасность. У каждого документа есть оглавление, ссылки на
первоисточники в тексте и исходный markdown-файл внизу страницы — если удобнее читать в
репозитории. Нашли ошибку или противоречие — напишите на
<a href="mailto:hello@axiiom.ru">hello@axiiom.ru</a>, мы правим документацию быстро.</p>
"""
    body = lead + "<h2>Все документы</h2>" + "".join(cards)
    html_page = page_shell(
        url_path="dokumentaciya/", title="Документация Fonotext",
        description="Документация Fonotext: план пилота и методика измерения качества, архитектура, модели распознавания, "
                    "цены, API, поставка и конкурентный анализ, спецификации фич.",
        body=body, toc=[], breadcrumbs=[("Fonotext", "../"), ("Документация", "")],
        prev_doc=None, next_doc=None, markdown_name=None, up_prefix="../")
    html_page = html_page.replace("</style>", """
  .lead{font-size:18px;color:var(--muted);margin-bottom:26px}
  .card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-bottom:16px}
  .card h2{font-size:19px;margin:0 0 10px}
  .card ul{list-style:none;margin:0}
  .card li{padding:5px 0;border-bottom:1px dashed var(--line)}
  .card li:last-child{border-bottom:none}
</style>""")
    dst = os.path.join(DOCS, "dokumentaciya", "index.html")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(html_page)
    print("  каталог → docs/dokumentaciya/index.html")


def build_sitemap(link_map: dict) -> None:
    """sitemap.xml: главная, SEO-страница, каталог документации и все HTML-документы."""
    urls = [
        ("", "1.0", "daily"),
        ("rechevaya-analitika/", "0.9", "weekly"),
        ("dokumentaciya/", "0.8", "weekly"),
        ("06-pricing.html", "0.9", "weekly"),
        ("05-poc-plan.html", "0.8", "weekly"),
        ("09-competitive-landscape.html", "0.8", "weekly"),
        ("04-hardware.html", "0.7", "monthly"),
        ("08-api.html", "0.8", "monthly"),
        ("01-integration.html", "0.7", "monthly"),
        ("02-architecture.html", "0.7", "monthly"),
        ("03-models.html", "0.7", "monthly"),
        ("07-deployment.html", "0.7", "monthly"),
        ("10-feature-specs/", "0.7", "weekly"),
    ] + [(link_map[d[0]] if not link_map[d[0]].endswith("index.html") else link_map[d[0]][:-len("index.html")],
          "0.6", "monthly") for d in FEATURE_DOCS if d[0] in link_map] + [
        ("404.html", "0.1", "yearly"),
    ]
    seen, items = set(), []
    for path, prio, freq in urls:
        if path in seen:
            continue
        seen.add(path)
        loc = SITE + path
        items.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{TODAY}</lastmod>\n"
                     f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(items) + "\n</urlset>\n")
    with open(os.path.join(DOCS, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    print(f"  sitemap.xml → {len(seen)} URL")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print("Сборка HTML-документации:" if not args.dry_run else "Проверка (без записи):")
    built = build(dry_run=args.dry_run)
    print(f"Готово: {len(built)} страниц.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
