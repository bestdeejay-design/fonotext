#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Применение правок по аудиту демо-панели (docs/_audit/demo-panel-audit.md).

Правит сгенерированные страницы docs/demo/ «на месте» (правки идемпотентны,
скрипт можно запускать повторно).

Что делает:
  1. «сейчас 90» → «сейчас 3650» (устаревшее справочное значение окна);
  2. «отставание от источника: 11 ч» → «0 ч» (as_of == watermark);
  3. битые якоря «Связанные» на glossary-search → ../glossary/#term-*;
  4. viewbox="…" → viewBox="…" (канон SVG);
  5. вкладки справки: реальные якоря + единственный aria-current="page";
  6. <button> внутри <form>: проставляется type="submit";
  7. внутренний <footer class="v4-footer"> → <section class="v4-footer">;
  8. страница exports-disabled приводится к общей оболочке;
  9. calls-filters получает оболочку, noindex, manifest, viewport;
 10. добавляются недостающие CSS-правила (freshness, snap, term-ref, …)
     и правило .tool-chip.current.

Запуск:
    python3 tools/fix-demo-audit.py            # применить
    python3 tools/fix-demo-audit.py --dry-run  # только показать, что изменится

Зависимостей нет — только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "docs", "demo")

# Канон окна: 2016-10-30 + 3650 дней = 2026-10-28 (согласовано со снимком).
HOT_WINDOW_DAYS = "3650"
# as_of = 2026-10-28T12:00:00+03:00 = 09:00Z, watermark = 09:00Z → отставание 0 ч.
LAG_HOURS = "0"

# --- недостающие CSS-правила -------------------------------------------------
EXTRA_CSS = """
/* v4-demo-fixes: правила для классов, которые использовались в разметке, но не имели стилей */
.fresh-block{margin:16px 0 24px}
.freshness{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));
 background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 20px}
.freshness>strong{grid-column:1/-1;font-size:15px;font-weight:650}
.freshness>span{font-size:13px;color:var(--muted)}
.freshness>span.badge{color:var(--text);justify-self:start}
.snap{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
 padding:0 16px;margin:12px 0}
.snap>summary{padding:12px 0;font-weight:600}
.snap-signature{margin:12px 0 16px;border:1px solid var(--line);border-radius:var(--radius);
 overflow:hidden;font-size:13px}
.snap-signature caption{font-weight:600}
.snap-signature td:first-child{color:var(--muted);width:42%}
.snap-body>p:first-child{margin-top:0}
.docs-lead{max-width:80ch}
.term-ref{border-bottom:1px dotted var(--muted);text-decoration:none;cursor:help}
.term-ref:hover{border-bottom-color:var(--accent);color:var(--accent)}
.v4-help,.v4-method-data{background:var(--panel);border:1px solid var(--line);
 border-radius:var(--radius);padding:0 16px;margin:12px 0}
.v4-help>summary,.v4-method-data>summary{padding:12px 0;font-weight:600}
.term-list li{display:grid;grid-template-columns:minmax(0,1fr);gap:2px}
.action-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));
 gap:12px;margin:16px 0 24px}
.action-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
 padding:20px;display:grid;gap:8px;align-content:start}
.action-card h3{margin:0}
.action-card .demo-unavailable{justify-self:start}
.chip-reset,.chip-x{background:var(--panel);color:var(--text);border:1px solid var(--line);
 border-radius:8px;padding:2px 8px;font-size:12px;cursor:pointer}
.tool-chip.current{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}
.current{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}
.toolbar-label{font-size:12px;color:var(--muted)}
.rail-views,.view-save{display:grid;gap:8px}
.view-save{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap}
.data-note{font-size:13px;color:var(--muted)}
.stage,.stage-name,.stage-row{font-size:13px}
.stage-row{border-bottom:1px solid var(--line);padding:10px 0}
.stage-name{font-weight:600}
.transcript{font-size:13px;line-height:1.6;background:var(--panel);border:1px solid var(--line);
 border-radius:var(--radius);padding:14px 16px;margin:12px 0;max-height:340px;overflow:auto}
.report-controls,.report-heading,.report-sort{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
 font-size:13px;color:var(--muted)}
.report-heading{font-weight:600;color:var(--text);font-size:15px}
.time-availability{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.chips-empty{color:var(--muted);font-size:13px}
.decision,.decision-cell{font-size:13px}
.decision{font-weight:600}
.finding-row{border-bottom:1px solid var(--line);padding:10px 0}
.glossary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px}
.term-careful{font-size:13px;color:var(--muted)}
.v4-operator-filters{display:flex;align-items:end;gap:10px;flex-wrap:wrap}
.v4-actions{display:flex;align-items:center;gap:8px}
.v4-layout{display:grid}
/* /v4-demo-fixes */
"""


def apply_to_panel(html: str) -> tuple[str, list[str]]:
    """Правки для страниц панели (общий шаблон)."""
    changes: list[str] = []
    out = html

    # 1. справочное значение окна
    new = out.replace("быстром слое; сейчас 90.", f"быстром слое; сейчас {HOT_WINDOW_DAYS}.")
    if new != out:
        changes.append("справочное значение окна: 90 → %s" % HOT_WINDOW_DAYS)
        out = new

    # 2. отставание от источника
    new = out.replace("отставание от источника: 11 ч", f"отставание от источника: {LAG_HOURS} ч")
    if new != out:
        changes.append("отставание от источника: 11 ч → %s ч" % LAG_HOURS)
        out = new

    # 4. регистр SVG-атрибута
    new = out.replace('viewbox="0 0 32 32"', 'viewBox="0 0 32 32"')
    if new != out:
        changes.append("SVG: viewbox → viewBox")
        out = new

    # 5. вкладки справки: реальные якоря + один aria-current
    tabs_old = re.search(r'<nav class="docs-tabs" aria-label="Разделы справки">.*?</nav>', out, re.S)
    if tabs_old:
        old = tabs_old.group(0)
        href = re.search(r'href="([^"]+)"', old).group(1)
        base = href.split("#")[0]
        new_tabs = (
            '<nav class="docs-tabs" aria-label="Разделы справки">'
            f'<a href="{base}#docs-read">Как читать</a>'
            f'<a href="{base}#docs-terms">Термины</a>'
            f'<a href="{base}#docs-next">Что дальше</a>'
            '</nav>'
        )
        # на страницах-словарях (learn-*) блоков «Как читать» и «Что дальше» нет —
        # оставляем только вкладку «Термины», чтобы не вести в пустоту.
        # Признаки смотрим в ИСХОДНОЙ разметке (out на этом шаге ещё не изменён).
        has_read_block = bool(re.search(r'<h3(\s[^>]*)?>', out))
        has_next_block = "Подробнее — в Обучении" in out
        if not (has_read_block and has_next_block):
            new_tabs = (
                '<nav class="docs-tabs" aria-label="Разделы справки">'
                f'<a href="{base}#docs-terms">Термины</a>'
                '</nav>'
            )
        out = out.replace(old, new_tabs)
        changes.append("вкладки справки: реальные якоря #docs-read/#docs-terms/#docs-next, aria-current убран")

    # ссылки-термины ведут к разделу «Термины раздела»
    n_terms_links = len(re.findall(r'class="term-ref" href="[^"]*#docs"', out))
    out = re.sub(r'(class="term-ref" href="[^"]*?)#docs"', r'\1#docs-terms"', out)
    if n_terms_links:
        changes.append(f"ссылки-термины ({n_terms_links}) ведут на #docs-terms")

    # якоря для вкладок справки (структура справки разная на разных страницах)
    out, n1 = re.subn(
        r'<h3>([^<]+)</h3>(?=<p class="docs-lead">)',
        r'<h3 id="docs-read">\1</h3>',
        out, count=1,
    )
    out, n2 = re.subn(
        r'<h4>Термины раздела(?:[^<]*)</h4>',
        lambda m: m.group(0).replace("<h4>", '<h4 id="docs-terms">', 1),
        out, count=1,
    )
    out, n3 = re.subn(
        r'<p class="docs-lead">(?=Подробнее — в Обучении)',
        '<p class="docs-lead" id="docs-next">',
        out, count=1,
    )
    # якоря ставим только под реально существующие вкладки справки
    tabs_now = re.search(r'<nav class="docs-tabs".*?</nav>', out, re.S)
    tabs_now = tabs_now.group(0) if tabs_now else ""
    if "#docs-read" in tabs_now and 'id="docs-read"' not in out:
        out = out.replace('<div class="v3-help-content">',
                          '<div class="v3-help-content" id="docs-read">', 1)
        n1 = 1
    if "#docs-terms" in tabs_now and 'id="docs-terms"' not in out:
        out = out.replace('<h4>Термины раздела',
                          '<h4 id="docs-terms">Термины раздела', 1)
        n2 = 1
    if "#docs-next" in tabs_now and 'id="docs-next"' not in out:
        out = out.replace('<p class="docs-lead">Подробнее — в Обучении:',
                          '<p class="docs-lead" id="docs-next">Подробнее — в Обучении:', 1)
        n3 = 1
    if n1 or n2 or n3:
        changes.append("добавлены якоря #docs-read, #docs-terms, #docs-next")

    # 6. type у <button> внутри <form>
    def form_repl(match: re.Match) -> str:
        form = match.group(0)

        def button_repl(btn: re.Match) -> str:
            tag = btn.group(0)
            if re.search(r"\btype=", tag):
                return tag
            return tag.replace("<button", '<button type="submit"', 1)

        return re.sub(r"<button\b[^>]*>", button_repl, form)

    out = re.sub(r"<form\b[^>]*>.*?</form>", form_repl, out, flags=re.S)
    if out.count('type="submit"') > html.count('type="submit"'):
        changes.append("кнопкам в формах проставлен type=\"submit\"")

    # 7. внутренний <footer class="v4-footer"> → <section>
    out = out.replace('<footer class="v4-footer">', '<section class="v4-footer">')
    out = out.replace('<nav class="v4-footer-nav" aria-label="Методика">',
                      '<nav class="v4-footer-nav" aria-label="Методика">')
    # закрывающий тег именно внутреннего footer — он последний внутри v4-workspace
    out = out.replace('</nav></footer></div></div><footer class="demo-footer">',
                      '</nav></section></div></div><footer class="demo-footer">')
    if '<section class="v4-footer">' in out:
        changes.append("внутренний <footer class=\"v4-footer\"> → <section>")

    # 10. недостающие CSS-правила (только там, где есть соответствующая разметка)
    needs_css = bool(re.search(r'class="[^"]*\b(freshness|snap|term-ref|action-grid|action-card|'
                               r'tool-chip current|v4-help|docs-lead)\b', out))
    if needs_css and "v4-demo-fixes" not in out:
        marker = "/* /v4-theme-palette */"
        if marker in out:
            out = out.replace(marker, marker + "\n" + EXTRA_CSS, 1)
        else:
            out = out.replace("</style>", EXTRA_CSS + "</style>", 1)
        changes.append("добавлены недостающие CSS-правила (v4-demo-fixes)")

    return out, changes


def fix_glossary_search(html: str) -> tuple[str, list[str]]:
    """Ссылки «Связанные» на странице поиска ведут в полный словарь."""
    changes: list[str] = []
    out = html
    for frag in ("term-coverage", "term-item-state", "term-bounds"):
        old = f'href="#{frag}"'
        new = f'href="../glossary/#{frag}"'
        if old in out:
            out = out.replace(old, new)
            changes.append(f"ссылка #{frag} → ../glossary/#{frag}")
    return out, changes


SHELL_HEAD = """<!doctype html><html lang="ru" data-ui="v4" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><link rel="icon" type="image/svg+xml" href="../brand/favicon.svg"><link rel="apple-touch-icon" href="../brand/icon-192.png"><link rel="manifest" href="../brand/manifest.webmanifest"><title>{title}</title>"""

RIBBON = ('<aside class="demo-ribbon"><strong>Демонстрационные данные · все записи и имена вымышлены</strong>'
          '<a class="demo-banner-link" href="https://fonotext.ru/">fonotext.ru</a>'
          '<a href="../calls-filters/">Готовые фильтры звонков</a></aside>')

DEMO_CSS = ("<style>.demo-ribbon{padding:8px 18px;background:#1A2238;color:#EDF0FA;font:12px/1.4 system-ui,sans-serif;"
            "display:flex;gap:12px;justify-content:center;flex-wrap:wrap;border-bottom:1px solid #8B93FF}"
            ".demo-ribbon a,.demo-footer a{color:#AEB3FF}"
            ".demo-footer{padding:18px;text-align:center;color:#A8B3CC;font:12px/1.5 system-ui,sans-serif;"
            "border-top:1px solid #252E3D}"
            ".demo-unavailable{display:inline-block;margin:8px 0;padding:4px 8px;border:1px solid #8B93FF;"
            "border-radius:8px;color:#EDF0FA;font-size:12px}"
            ".demo-static-hint{display:block;color:#A8B3CC;font-size:12px;margin:8px 0}"
            ".demo-password-hint{font-size:12px;opacity:.68}"
            ".demo-banner-link{font-weight:650}"
            ".demo-theme{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;flex:none;"
            "border:1px solid var(--line);border-radius:10px;background:transparent;color:var(--muted);cursor:pointer;"
            "transition:color .15s,border-color .15s,background .15s;padding:0}"
            ".demo-theme:hover{color:var(--accent);border-color:var(--accent);background:var(--panel)}"
            ".demo-theme:focus-visible{outline:2px solid var(--accent);outline-offset:2px}"
            ".demo-theme svg{width:18px;height:18px;display:block}"
            ".demo-theme .ic-sun{display:none}.demo-theme .ic-sun{display:block}.demo-theme .ic-moon{display:none}"
            "[data-theme=dark] .demo-theme .ic-sun{display:block}[data-theme=dark] .demo-theme .ic-moon{display:none}"
            "</style>")

AUTH_SCRIPT = ('<script>(function(){if(sessionStorage.getItem("fonotext-demo-auth")!=="1"){'
               'var seg=location.pathname.replace(/\\/+$/,"").split("/").pop();'
               'location.replace("../?next="+encodeURIComponent(seg+"/"));}})();</script>')

THEME_SCRIPT = ('<script>(function(){var t=localStorage.getItem("fonotext-demo-theme");if(t){'
                'document.documentElement.setAttribute("data-theme",t);'
                'document.addEventListener("click",function(ev){var b=ev.target&&ev.target.closest?'
                'ev.target.closest("#demo-theme-toggle"):null;if(!b){return;}'
                'var d=document.documentElement;'
                'var n=(d.getAttribute("data-theme")==="light")?"dark":"light";'
                'd.setAttribute("data-theme",n);localStorage.setItem("fonotext-demo-theme",n);});})();</script>')

DEMO_FOOTER = ('<footer class="demo-footer">Демонстрационный стенд. Данные вымышлены; телефоны и цитаты '
               'замаскированы. <a href="https://fonotext.ru/">fonotext.ru</a></footer>')

PANEL_CSS = (".v4-layout{display:grid;grid-template-columns:224px minmax(0,1fr);max-width:1600px;margin:auto}"
             ".v4-workspace{min-width:0;padding:40px 48px 56px}"
             ".v4-main{max-width:1080px;margin:auto;min-width:0}"
             ".v4-nav{display:grid;gap:5px}"
             ".v4-nav a{display:flex;align-items:center;gap:12px;color:var(--muted);text-decoration:none;"
             "min-height:44px;padding:10px 14px;border-radius:10px;font-size:14px}"
             ".v4-nav a[aria-current=page]{background:var(--panel);color:var(--accent);font-weight:600}"
             ".v4-nav-index{font:11px ui-monospace,monospace;opacity:.7}"
             ".v4-nav-divider{height:1px;background:var(--line);margin:16px 14px}"
             ".v4-sidebar{position:sticky;top:81px;max-height:calc(100dvh - 81px);overflow-y:auto;"
             "padding:28px 16px;border-right:1px solid var(--line)}"
             "h1{font-size:clamp(26px,3vw,38px);letter-spacing:-.04em;line-height:1.15;font-weight:650;margin:0 0 16px}"
             "h2{font-size:20px;letter-spacing:-.02em;margin-top:32px}"
             "h3{font-size:16px}h4{font-size:14px}"
             "p{margin:0 0 16px;line-height:1.55}"
             "ul{padding-left:20px}li{margin:6px 0}"
             "a{color:var(--accent);text-underline-offset:3px}"
             "body{margin:0;background:#0B0F17;color:#EDF0FA;font:15px/1.55 -apple-system,BlinkMacSystemFont,"
             "'Segoe UI',Inter,'Helvetica Neue',Arial,sans-serif}"
             ":root{--bg:#0B0F17;--panel:#1A2238;--line:#252E3D;--accent:#8B93FF;--text:#EDF0FA;"
             "--muted:#A8B3CC;--on-accent:#0B0F17;--radius:14px}"
             "code,.mono{font-family:ui-monospace,Menlo,Consolas,monospace}"
             ".v4-footer{max-width:1080px;margin:40px auto 0;border-top:1px solid var(--line);padding-top:16px;"
             "color:var(--muted);font-size:13px}"
             ".v4-footer-nav{display:flex;gap:16px;flex-wrap:wrap;margin-top:20px}"
             ".v4-actions{display:flex;align-items:center;gap:8px}"
             ".v4-topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 32px;"
             "border-bottom:1px solid var(--line)}"
             ".v4-brand{display:inline-flex;align-items:center;gap:10px;font-weight:650;font-size:21px;"
             "text-decoration:none;color:var(--text)}"
             "button,input,select,textarea{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);"
             "border-radius:8px;padding:9px 12px;min-height:44px}"
             "button{cursor:pointer}button:hover{border-color:var(--accent)}"
             "label{display:grid;gap:4px;font-size:13px;color:var(--muted)}"
             "table{border-collapse:collapse;width:100%;font-size:14px}"
             "th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}"
             "th{font-size:12px;font-weight:600;color:var(--muted)}"
             ".table-scroll{max-width:100%;overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);"
             "margin:12px 0 24px}"
             ".skip{position:absolute;left:-9999px}.skip:focus{left:12px;top:12px;z-index:50;"
             "background:var(--panel);padding:12px}"
             ".vh{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}"
             "@media(max-width:760px){.v4-layout{display:block}.v4-sidebar{position:static;max-height:none;"
             "padding:10px 16px;border-right:0;border-bottom:1px solid var(--line);overflow:visible}"
             ".v4-nav{display:flex;overflow-x:auto;gap:4px;padding:4px}.v4-nav a{flex-shrink:0;padding:8px 12px}"
             ".v4-workspace{padding:28px 16px}}")

SIDEBAR = ('<aside class="v4-sidebar"><nav class="v4-nav" aria-label="Разделы панели">'
           '<a href="../dashboard/"><span class="v4-nav-index" aria-hidden="true">01</span>Обзор</a>'
           '<a href="../reports/"><span class="v4-nav-index" aria-hidden="true">02</span>Отчёты</a>'
           '<a href="../calls/"><span class="v4-nav-index" aria-hidden="true">03</span>Звонки</a>'
           '<a href="../operators/"><span class="v4-nav-index" aria-hidden="true">04</span>Операторы</a>'
           '<a href="../findings/"><span class="v4-nav-index" aria-hidden="true">05</span>Находки СБ</a>'
           '<div class="v4-nav-divider" role="separator"></div>'
           '<a href="../quality/"><span class="v4-nav-index" aria-hidden="true">06</span>Качество данных</a>'
           '<a href="../build/"><span class="v4-nav-index" aria-hidden="true">07</span>Сборка</a>'
           '</nav></aside>')

TOPBAR = ('<header class="v4-topbar"><a class="v4-brand" href="../dashboard/">'
          '<svg aria-hidden="true" width="26" height="26" viewBox="0 0 32 32">'
          '<rect width="32" height="32" rx="7" fill="var(--accent)"></rect>'
          '<path d="M7 16h2m3-6v12m3-9v6m3-9v12m3-6h2" stroke="white" stroke-width="2" '
          'stroke-linecap="round"></path></svg>Fonotext</a>'
          '<div class="v4-actions"></div></header>')


def rebuild_exports_disabled() -> str:
    """Страница «Экспорт отключён» в общей оболочке панели."""
    return (
        '<!doctype html><html lang="ru" data-ui="v4" data-theme="dark"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex">'
        '<link rel="icon" type="image/svg+xml" href="../brand/favicon.svg">'
        '<link rel="apple-touch-icon" href="../brand/icon-192.png">'
        '<link rel="manifest" href="../brand/manifest.webmanifest">'
        '<title>Экспорт отключён в демо — Fonotext</title>'
        f'<style>{PANEL_CSS}</style>'
        f'{DEMO_CSS}'
        f'{AUTH_SCRIPT}{THEME_SCRIPT}</head><body>'
        f'{RIBBON}'
        '<a class="skip" href="#main">К содержимому</a>'
        f'{TOPBAR}'
        '<div class="v4-layout">'
        f'{SIDEBAR}'
        '<div class="v4-workspace"><main class="v4-main" id="main" tabindex="-1">'
        '<h1>Экспорт отключён в демо</h1>'
        '<p>Выгрузка выборки (CSV/XLSX) в демо-стенде недоступна: демо показывает только '
        'подготовленные страницы, без выгрузки данных.</p>'
        '<p><a href="../calls/">К списку звонков</a> · <a href="../dashboard/">Обзор</a></p>'
        '</main></div></div>'
        f'{DEMO_FOOTER}</body></html>'
    )


def rebuild_calls_filters(body_links: str) -> str:
    """Страница «Готовые фильтры» в общей оболочке."""
    return (
        '<!doctype html><html lang="ru" data-ui="v4" data-theme="dark"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex">'
        '<link rel="icon" type="image/svg+xml" href="../brand/favicon.svg">'
        '<link rel="apple-touch-icon" href="../brand/icon-192.png">'
        '<link rel="manifest" href="../brand/manifest.webmanifest">'
        '<title>Готовые фильтры · Fonotext</title>'
        f'<style>{PANEL_CSS}</style>'
        f'{DEMO_CSS}'
        f'{AUTH_SCRIPT}{THEME_SCRIPT}</head><body>'
        f'{RIBBON}'
        '<a class="skip" href="#main">К содержимому</a>'
        f'{TOPBAR}'
        '<div class="v4-layout">'
        f'{SIDEBAR}'
        '<div class="v4-workspace"><main class="v4-main" id="main" tabindex="-1">'
        '<h1>Готовые фильтры звонков</h1>'
        f'{body_links}'
        '<p><a href="../calls/">К списку звонков</a> · <a href="../dashboard/">К обзору</a></p>'
        '</main></div></div>'
        f'{DEMO_FOOTER}</body></html>'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Правки демо-панели по результатам аудита")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что изменится")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(DEMO, "**", "index.html"), recursive=True))
    if not files:
        print("Не найдены HTML-файлы в docs/demo/", file=sys.stderr)
        return 2

    total_changed = 0
    for path in files:
        rel = os.path.relpath(path, ROOT)
        original = open(path, encoding="utf-8").read()
        html = original
        changes: list[str] = []

        name = os.path.basename(os.path.dirname(path))

        if name == "exports-disabled":
            html = rebuild_exports_disabled()
            changes.append("пересобрана в общей оболочке v4 (<main>, viewport, manifest, тема, меню)")
        elif name == "calls-filters":
            links = re.search(r"(<ul>.*?</ul>)", original, re.S)
            html = rebuild_calls_filters(links.group(1) if links else "<ul></ul>")
            changes.append("пересобрана в общей оболочке v4 + noindex + manifest")
        else:
            html, ch = apply_to_panel(html)
            changes.extend(ch)
            if name == "glossary-search":
                html, ch = fix_glossary_search(html)
                changes.extend(ch)

        if html != original:
            total_changed += 1
            print(f"• {rel}")
            for change in changes:
                print(f"    — {change}")
            if not args.dry_run:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(html)

    # 11. манифест демо: список страниц должен совпадать с фактической выкаткой
    manifest_path = os.path.join(DEMO, "demo-manifest.json")
    if os.path.exists(manifest_path):
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        pages = sorted(
            os.path.relpath(f, DEMO).replace(os.sep, "/")
            for f in glob.glob(os.path.join(DEMO, "**", "index.html"), recursive=True)
        )
        if manifest.get("pages") != pages:
            manifest["pages"] = pages
            manifest["page_count"] = len(pages)
            print("• docs/demo/demo-manifest.json — список страниц обновлён "
                  f"({len(pages)} страниц)")
            if not args.dry_run:
                with open(manifest_path, "w", encoding="utf-8") as fh:
                    json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
                    fh.write("\n")

    print(f"\n{'Изменено файлов (dry-run):' if args.dry_run else 'Изменено файлов:'} {total_changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
