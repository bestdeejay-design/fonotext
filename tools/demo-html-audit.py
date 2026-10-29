#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Структурный аудит HTML демо-панели Fonotext (docs/demo/).

Проверяет то, чего не проверяет tools/site-audit.py (SEO-аудит исключает /demo/):
  * баланс и вложенность HTML-тегов;
  * дубли id и несуществующие якоря (#fragment);
  * единственный <main> и единственный <h1>;
  * доступные имена у ссылок и полей форм;
  * согласованность CSS-классов: классы в разметке без правил;
  * регистр SVG-атрибутов (viewBox);
  * внутренние ссылки на существующие файлы;
  * инварианты страниц demo/build и demo/glossary-search.

Запуск:
    python3 tools/demo-html-audit.py             # сводный отчёт
    python3 tools/demo-html-audit.py --verbose   # проверки без замечаний
    python3 tools/demo-html-audit.py --page demo/build/index.html

Зависимостей нет — только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "docs", "demo")

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

FAIL, WARN, INFO, OK = "FAIL", "WARN", "INFO", "OK"


class DemoPage(HTMLParser):
    """Собирает структурные факты страницы."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, tuple[int, int]]] = []
        self.errors: list[tuple[str, str, tuple[int, int]]] = []   # критичные
        self.style_issues: list[tuple[str, str, tuple[int, int]]] = []  # неканон
        self.ids: dict[str, tuple[int, int]] = {}
        self.duplicate_ids: list[tuple[str, tuple[int, int]]] = []
        self.fragments: list[tuple[str, tuple[int, int]]] = []
        self.links: list[tuple[str, tuple[int, int]]] = []
        self.labels_for: set[str] = set()
        self.controls: list[tuple[str, dict, tuple[int, int], bool]] = []
        self.buttons_without_type: list[tuple[str, tuple[int, int]]] = []
        self.aria_current: list[tuple[str, str, tuple[int, int]]] = []
        self._label_depth = 0
        self._form_depth = 0
        self.empty_links: list[tuple[str, tuple[int, int]]] = []
        self.headings: list[str] = []
        self.main_count = 0
        self.h1_count = 0
        self.lang = None
        self.title = ""
        self._in_title = False
        self._link_stack: list[list] = []

    # --- callbacks -------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        pos = self.getpos()
        raw_tag = self.get_starttag_text() or ""

        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "main":
            self.main_count += 1
        elif tag == "h1":
            self.h1_count += 1
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(tag)

        element_id = a.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.append((element_id, pos))
            else:
                self.ids[element_id] = pos

        # HTML-парсер приводит имена атрибутов к нижнему регистру, поэтому регистр
        # viewBox проверяем по исходному тексту тега.
        if re.search(r"\bviewbox\s*=", raw_tag):
            self.style_issues.append(
                ("SVG_ATTR_CASE", "атрибут viewbox в нижнем регистре (канон SVG: viewBox)", pos)
            )

        href = a.get("href", "")
        if href:
            self.links.append((href, pos))
            if href.startswith("#") and len(href) > 1:
                self.fragments.append((href[1:], pos))

        if tag == "label":
            if a.get("for"):
                self.labels_for.add(a["for"])
            self._label_depth += 1
        if tag in ("input", "select", "textarea"):
            self.controls.append((tag, a, pos, self._label_depth > 0))
        if tag == "form":
            self._form_depth += 1
        if tag == "button":
            if self._form_depth and "type" not in a:
                self.buttons_without_type.append((a.get("name") or a.get("value") or "?", pos))
        if tag == "a" and a.get("aria-current"):
            self.aria_current.append((a["aria-current"], a.get("href", ""), pos))
        if tag == "a":
            self._link_stack.append([href, [], a.get("aria-label"), a.get("title")])

        if tag not in VOID:
            self.stack.append((tag, pos))

    def handle_startendtag(self, tag: str, attrs) -> None:
        pos = self.getpos()
        raw_tag = self.get_starttag_text() or ""
        if re.search(r"\bviewbox\s*=", raw_tag):
            self.style_issues.append(
                ("SVG_ATTR_CASE", "атрибут viewbox в нижнем регистре (канон SVG: viewBox)", pos)
            )

    def handle_endtag(self, tag: str) -> None:
        pos = self.getpos()
        if tag == "title":
            self._in_title = False
        if tag == "label" and self._label_depth:
            self._label_depth -= 1
        if tag == "form" and self._form_depth:
            self._form_depth -= 1
        if tag == "a" and self._link_stack:
            link = self._link_stack.pop()
            if not "".join(link[1]).strip() and not link[2] and not link[3]:
                self.empty_links.append((link[0], pos))
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(("EXTRA_END", f"лишний </{tag}>", pos))
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
            return
        open_tags = [item[0] for item in self.stack]
        if tag in open_tags:
            while self.stack:
                unclosed = self.stack.pop()
                if unclosed[0] == tag:
                    break
                self.errors.append(
                    ("UNCLOSED", f"<{unclosed[0]}> не закрыт до </{tag}>", unclosed[1])
                )
        else:
            self.errors.append(("EXTRA_END", f"лишний </{tag}>", pos))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._link_stack:
            self._link_stack[-1][1].append(data)

    def close(self) -> None:
        super().close()
        for tag, pos in self.stack:
            self.errors.append(("UNCLOSED_EOF", f"<{tag}> не закрыт", pos))


def relative_target(path: str, href: str) -> str | None:
    """Путь локального файла, если href ведёт внутрь репозитория."""
    if not href or href.startswith(("http:", "https:", "mailto:", "tel:", "javascript:", "data:")):
        return None
    clean = href.split("#")[0].split("?")[0]
    if not clean:
        return None
    base = os.path.dirname(path)
    candidate = os.path.normpath(os.path.join(base, clean))
    if candidate.endswith(os.sep) or os.path.isdir(candidate):
        candidate = os.path.join(candidate, "index.html")
    return candidate


def used_classes(html: str) -> Counter:
    body = re.sub(r"<style\b.*?</style>|<script\b.*?</script>", "", html, flags=re.S | re.I)
    counter: Counter = Counter()
    for value in re.findall(r'class\s*=\s*"([^"]*)"', body):
        counter.update(value.split())
    return counter


def css_classes(html: str) -> Counter:
    counter: Counter = Counter()
    for css in re.findall(r"<style\b[^>]*>(.*?)</style>", html, flags=re.S | re.I):
        for match in re.finditer(r"\.([A-Za-z_][\w-]*)", css):
            counter[match.group(1)] += 1
    return counter


def labelled_controls(page: DemoPage) -> list[tuple[str, str, tuple[int, int]]]:
    """Поля форм без доступного имени."""
    result = []
    for tag, attrs, pos, inside_label in page.controls:
        if attrs.get("type") == "hidden":
            continue
        if attrs.get("aria-label") or attrs.get("aria-labelledby"):
            continue
        if attrs.get("id") and attrs["id"] in page.labels_for:
            continue
        # control, обёрнутый в <label> без for, — корректный вариант
        if inside_label:
            continue
        result.append((tag, attrs.get("name") or attrs.get("id") or "?", pos))
    return result


def audit_file(path: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], dict]:
    """Возвращает (критичные, некритичные, статистика)."""
    critical: list[tuple[str, str, str]] = []
    minor: list[tuple[str, str, str]] = []
    add_c = lambda area, msg: critical.append((FAIL, area, msg))
    add_m = lambda area, msg: minor.append((WARN, area, msg))

    raw = open(path, encoding="utf-8").read()
    page = DemoPage()
    page.feed(raw)
    page.close()

    rel = os.path.relpath(path, ROOT)

    if page.errors:
        for kind, message, pos in page.errors:
            add_c("HTML-структура", f"{rel}:{pos[0]} — {kind}: {message}")
    else:
        minor.append((OK, "HTML-структура", f"{rel}: теги сбалансированы и корректно вложены"))

    if page.duplicate_ids:
        for element_id, pos in page.duplicate_ids:
            add_c("id", f"{rel}:{pos[0]} — повторяется id={element_id!r}")
    else:
        minor.append((OK, "id", f"{rel}: дубли id не найдены"))

    missing = [(frag, pos) for frag, pos in page.fragments if frag not in page.ids]
    if missing:
        for frag, pos in missing:
            add_c("Якоря", f"{rel} (строка {pos[0]}) — ссылка на несуществующий якорь #{frag}")
    else:
        minor.append((OK, "Якоря", f"{rel}: все локальные #fragment существуют"))

    if page.main_count != 1:
        add_c("Семантика", f"{rel}: <main> встречается {page.main_count} раз (нужен 1)")
    if page.h1_count != 1:
        add_c("Семантика", f"{rel}: <h1> встречается {page.h1_count} раз (нужен 1)")

    unlabelled = labelled_controls(page)
    if unlabelled:
        for tag, name, pos in unlabelled:
            add_m("Формы", f"{rel}:{pos[0]} — <{tag}> без доступного имени ({name})")
    else:
        minor.append((OK, "Формы", f"{rel}: все видимые поля форм имеют доступное имя"))

    if page.empty_links:
        for href, pos in page.empty_links:
            add_m("Ссылки", f"{rel}:{pos[0]} — ссылка без текста/aria-label: {href!r}")
    else:
        minor.append((OK, "Ссылки", f"{rel}: нет ссылок без доступного имени"))

    if page.buttons_without_type:
        add_m("Формы", f"{rel}: {len(page.buttons_without_type)} <button> внутри <form> без type= "
                        f"(по умолчанию type=submit)")

    if len(page.aria_current) > 1:
        add_m("Доступность", f"{rel}: aria-current у {len(page.aria_current)} ссылок — "
                              f"активным должен быть один (страница + вкладки справки)")

    dead = []
    for href, pos in page.links:
        target = relative_target(path, href)
        if target and not os.path.exists(target):
            dead.append((href, pos))
    if dead:
        for href, pos in dead:
            add_c("Ссылки", f"{rel}:{pos[0]} — битая внутренняя ссылка {href!r}")
    else:
        minor.append((OK, "Ссылки", f"{rel}: внутренние ссылки ведут на существующие файлы"))

    classes = css_classes(raw)
    used = used_classes(raw)
    missing_css = sorted(c for c in used if c not in classes)
    if missing_css:
        add_m("CSS", f"{rel}: классы без правил CSS: {', '.join(missing_css)}")

    if page.style_issues:
        counts = Counter(issue[1] for issue in page.style_issues)
        for message, count in counts.items():
            add_m("SVG", f"{rel}: {message} — {count} шт.")

    stats = {
        "file": rel,
        "fails": sum(1 for level, *_ in critical if level == FAIL),
        "warns": sum(1 for level, *_ in minor if level == WARN),
    }
    return critical, minor, stats


def audit_hot_window(path: str) -> tuple[list, list]:
    """«Горячее окно»: значение в UI должно совпадать со справкой/словарём."""
    critical: list[tuple[str, str, str]] = []
    rel = os.path.relpath(path, ROOT)
    raw = open(path, encoding="utf-8").read()
    shown = set(re.findall(r"горячее окно (\d+) дн\.", raw))
    stated = set(re.findall(r"быстром слое; сейчас (\d+)", raw))
    if shown and stated and shown != stated:
        critical.append((
            FAIL, "Данные",
            f"{rel}: в UI «горячее окно {', '.join(sorted(shown))} дн.», "
            f"а в справке/словаре «сейчас {', '.join(sorted(stated))}»",
        ))
    return critical, []


def audit_lag(path: str) -> tuple[list, list]:
    """Проверка «отставание от источника» = as_of − watermark на всех страницах."""
    critical: list[tuple[str, str, str]] = []
    raw = open(path, encoding="utf-8").read()
    rel = os.path.relpath(path, ROOT)
    as_of = re.search(r"as_of:\s*<code>([^<]+)</code>", raw)
    watermark = re.search(r"watermark:\s*<code>([^<]+)</code>", raw)
    lags = re.findall(r"отставание от источника:\s*([^<]+)</span>", raw)
    if not (as_of and watermark and lags):
        return critical, []
    try:
        a = datetime.fromisoformat(as_of.group(1).replace("Z", "+00:00"))
        w = datetime.fromisoformat(watermark.group(1).replace("Z", "+00:00"))
    except ValueError:
        return critical, []
    delta_h = round((a - w).total_seconds() / 3600)
    for shown in lags:
        shown = shown.strip()
        match = re.match(r"(-?\d+)", shown)
        if not match:
            continue
        if int(match.group(1)) != delta_h:
            critical.append((
                FAIL, "Данные",
                f"{rel}: «отставание от источника: {shown}» ≠ as_of − watermark = {delta_h} ч",
            ))
            break
    return critical, []


def audit_build_contract(path: str) -> tuple[list, list]:
    """Инварианты demo/build, выявленные при аудите."""
    critical: list[tuple[str, str, str]] = []
    minor: list[tuple[str, str, str]] = []
    raw = open(path, encoding="utf-8").read()
    rel = os.path.relpath(path, ROOT)

    # проверки «горячее окно» и «отставание» вынесены в audit_hot_window() и audit_lag()
    # и применяются ко всем страницам панели.

    return critical, minor


def audit_glossary_search(path: str) -> tuple[list, list]:
    """Страница поиска по словарю: «Связанные» должны вести в полный словарь."""
    critical: list[tuple[str, str, str]] = []
    rel = os.path.relpath(path, ROOT)
    raw = open(path, encoding="utf-8").read()
    for frag in ("term-coverage", "term-item-state", "term-bounds"):
        if f'href="#{frag}"' in raw and f'id="{frag}"' not in raw:
            critical.append((
                FAIL, "Якоря",
                f"{rel}: «Связанные» ведёт на #{frag}, но на странице поиска такого элемента нет "
                f"(нужно ../glossary/#{frag})",
            ))
    return critical, []


def main() -> int:
    parser = argparse.ArgumentParser(description="Структурный аудит HTML демо-панели Fonotext")
    parser.add_argument("--verbose", action="store_true", help="показывать и успешные проверки")
    parser.add_argument("--page", help="проверить только одну страницу (путь относительно docs/demo)")
    args = parser.parse_args()

    if args.page:
        files = [os.path.join(DEMO, args.page)]
        if not os.path.exists(files[0]):
            print(f"Файл не найден: {files[0]}", file=sys.stderr)
            return 2
    else:
        files = sorted(glob.glob(os.path.join(DEMO, "**", "index.html"), recursive=True))

    if not files:
        print("Не найдены HTML-файлы в docs/demo/", file=sys.stderr)
        return 2

    critical: list[tuple[str, str, str]] = []
    minor: list[tuple[str, str, str]] = []
    stats = []

    for path in files:
        c, m, s = audit_file(path)
        critical.extend(c)
        minor.extend(m)
        stats.append(s)

        c_lag, m_lag = audit_lag(path)
        critical.extend(c_lag)
        minor.extend(m_lag)

        c_hot, m_hot = audit_hot_window(path)
        critical.extend(c_hot)
        minor.extend(m_hot)

    build = os.path.join(DEMO, "build", "index.html")
    if build in files:
        c, m = audit_build_contract(build)
        critical.extend(c)
        minor.extend(m)

    glossary_search = os.path.join(DEMO, "glossary-search", "index.html")
    if glossary_search in files:
        c, m = audit_glossary_search(glossary_search)
        critical.extend(c)
        minor.extend(m)

    fails = [f for f in critical if f[0] == FAIL]
    warns = [f for f in minor if f[0] == WARN]

    print(f"Проверено страниц: {len(files)}")
    print(f"Критичных: {len(fails)} · предупреждений: {len(warns)}")

    if fails:
        print("\n❌ Критичные замечания:")
        grouped: Counter = Counter()
        examples: dict[str, str] = {}
        for _, area, msg in fails:
            # убираем путь к файлу, чтобы одинаковые находки по разным страницам сливались
            generic = re.sub(r"^docs/[^:]+[:(]\s*", "", msg)
            generic = re.sub(r"^строка \d+\) — ", "", generic)
            key = f"{area}: {generic}"
            grouped[key] += 1
            examples.setdefault(key, msg)
        for key, count in grouped.most_common():
            suffix = f" — на {count} страницах" if count > 1 else ""
            print(f"- {key}{suffix}")

    if warns:
        print("\n⚠️ Предупреждения:")
        css_classes_seen: Counter = Counter()
        svg_pages: Counter = Counter()
        pattern_pages: Counter = Counter()
        other: list[tuple[str, str]] = []
        for _, area, msg in warns:
            if area == "CSS":
                for cls in re.findall(r"\b([a-zA-Z][\w-]+)\b", msg.split("без правил CSS:")[-1]):
                    css_classes_seen[cls] += 1
            elif area == "SVG":
                svg_pages[re.sub(r"^[^:]+:\s*", "", msg).split(" — ")[0]] += 1
            elif area in ("Формы", "Доступность"):
                # группируем одинаковые замечания по страницам
                pattern = re.sub(r"^[^:]+:\s*", "", msg)
                pattern = re.sub(r"^[\d—]+ — ", "", pattern)
                pattern = re.sub(r"\d+ <button>", "N <button>", pattern)
                pattern = re.sub(r"у \d+ ссылок", "у N ссылок", pattern)
                pattern_pages[(area, pattern)] += 1
            else:
                other.append((area, msg))
        if css_classes_seen:
            print("- CSS: классы без правил (число страниц):")
            for cls, count in css_classes_seen.most_common():
                print(f"    .{cls} — {count}")
        if svg_pages:
            print("- SVG:")
            for msg, count in svg_pages.most_common():
                print(f"    {msg} — на {count} страницах")
        for (area, pattern), count in pattern_pages.most_common():
            print(f"- {area} (на {count} страницах): {pattern}")
        for area, msg in other:
            print(f"- {area}: {msg}")

    if args.verbose:
        print("\n✅ Проверки без замечаний:")
        for _, area, msg in minor:
            if _ == OK:
                print(f"- {area}: {msg}")

    print("\nСводка по страницам (только с замечаниями):")
    shown = False
    for page_stats in stats:
        if page_stats["fails"] or page_stats["warns"]:
            shown = True
            print(f"- {page_stats['file']}: критичных {page_stats['fails']}, предупреждений {page_stats['warns']}")
    if not shown:
        print("- замечаний нет")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
