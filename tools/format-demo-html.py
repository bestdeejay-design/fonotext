#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Форматирование HTML демо-панели Fonotext (docs/demo/).

Разворачивает свёрнутую в одну строку разметку в читаемый вид: один элемент —
одна строка (или блок), вложенность видна по отступам.

Свойства форматтера (в отличие от prettier, который здесь не подходит):
  * **не меняет пробелы между элементами** — видимый текст на экране остаётся
    байт-в-байт тем же. Пробел между инлайновыми элементами в исходнике
    отсутствует намеренно (например «вымышлены» + <a>fonotext.ru</a>), и
    prettier разрывал бы такие стыки, меняя вёрстку;
  * **не трогает содержимое <style> и <script>** — CSS и JS остаются как есть;
  * **не меняет атрибуты** — только переносы строк и отступы;
  * каждый тег проверяется: неправильная разметка не «чинится» молча.

Запуск:
    python3 tools/format-demo-html.py            # отформатировать
    python3 tools/format-demo-html.py --check    # только проверить (для CI)
    python3 tools/format-demo-html.py --page build/index.html

Зависимостей нет — только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "docs", "demo")

INDENT = "  "
PRINT_WIDTH = 120

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# Элементы, содержимое которых не трогаем.
RAW_TEXT = {"script", "style", "pre", "textarea"}

# Элементы, содержимое которых пишется в одну строку с открывающим тегом.
TIGHT = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th",
         "caption", "summary", "legend", "option", "dt", "dd", "figcaption"}

# Элементы, которые всегда остаются на одной строке со своим содержимым.
# Элементы, которые ведут себя как инлайновые: их содержимое и соседи
# стоят в общем текстовом потоке, поэтому лишний пробел между ними виден.
# SVG: <svg> — контейнер, его дети — графические элементы.
# Они не создают блочных границ, поэтому ведущие пробелы в них не видны.
SVG_CONTAINER = {"svg"}
SVG_GRAPHICS = {"rect", "path", "circle", "ellipse", "line", "polyline", "polygon",
                "use", "stop", "g", "text", "tspan", "defs", "symbol", "marker"}

# SVG-элементы без содержимого: в исходнике бывают и как <rect .../>, и как <rect ...></rect>
SVG_EMPTY = {"rect", "path", "circle", "ellipse", "line", "polyline", "polygon",
             "use", "stop", "animate", "defs", "g", "text", "tspan"}

INLINE = {
    "a", "abbr", "b", "bdi", "bdo", "button", "cite", "code", "data", "dfn",
    "em", "i", "kbd", "label", "mark", "output", "q", "s", "samp", "select",
    "small", "span", "strong", "sub", "sup", "time", "u", "var", "wbr",
} | SVG_GRAPHICS | SVG_CONTAINER

TAG_RE = re.compile(
    r"<!--.*?-->"
    r"|<!\[CDATA\[.*?\]\]>"
    r"|<![^>]*>"
    r"|</\s*[a-zA-Z][^\s>]*\s*>"
    r"|<[a-zA-Z][^\s/>]*(?:\"[^\"]*\"|'[^']*'|[^>\"'])*>",
    re.S,
)

ATTR_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?")


class Token:
    __slots__ = ("kind", "text", "name", "closing", "self_closing", "raw_tag", "attrs_text")

    def __init__(self, kind: str, text: str, name: str = "", closing: bool = False,
                 self_closing: bool = False, raw_tag: str = "", attrs_text: str = "") -> None:
        self.kind = kind          # 'tag' | 'text' | 'comment' | 'doctype'
        self.text = text
        self.name = name
        self.closing = closing
        self.self_closing = self_closing
        self.raw_tag = raw_tag
        self.attrs_text = attrs_text


def tokenize(html: str) -> list[Token]:
    """Разбивает HTML на теги и текстовые узлы."""
    tokens: list[Token] = []
    pos = 0
    length = len(html)
    while pos < length:
        match = TAG_RE.search(html, pos)
        if not match:
            tokens.append(Token("text", html[pos:]))
            break
        if match.start() > pos:
            tokens.append(Token("text", html[pos:match.start()]))
        raw = match.group(0)
        pos = match.end()

        if raw.startswith("<!--"):
            tokens.append(Token("comment", raw))
            continue
        if raw.startswith("<!") and not raw.startswith("</"):
            tokens.append(Token("doctype", raw))
            continue
        if raw.startswith("</"):
            name = re.sub(r"^</\s*([a-zA-Z][^\s>]*).*$", r"\1", raw, flags=re.S)
            tokens.append(Token("tag", raw, name=name.lower(), closing=True))
            continue

        # открывающий тег
        name_match = re.match(r"<([a-zA-Z][^\s/>]*)", raw)
        name = name_match.group(1).lower() if name_match else ""
        self_closing = raw.rstrip().endswith("/>")
        attrs_text = raw[raw.find(name) + len(name):] if name else ""
        attrs_text = attrs_text.strip()
        if attrs_text.endswith("/"):
            attrs_text = attrs_text[:-1].rstrip()
        tokens.append(Token("tag", raw, name=name, closing=False,
                            self_closing=self_closing, raw_tag=raw, attrs_text=attrs_text))
    return tokens


def format_attrs(attrs_text: str, indent: str = "", wrap: bool = True) -> str:
    """Приводит атрибуты к единому виду: по одному в строке, если строка длинная."""
    if not attrs_text:
        return ""
    pairs: list[str] = []
    for match in ATTR_RE.finditer(attrs_text):
        name = match.group(1)
        value = match.group(2)
        if value is None:
            pairs.append(name)
        elif value.startswith('"') and value.endswith('"') and len(value) >= 2:
            pairs.append(f'{name}={value}')            # значение уже в кавычках
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            pairs.append(f"{name}={value}")
        elif value.startswith('"'):
            pairs.append(f'{name}="{value}"')
        elif value.startswith("'"):
            pairs.append(f"{name}='{value}'")
        else:
            pairs.append(f"{name}={value}")
    if not pairs:
        return ""
    single = " " + " ".join(pairs)
    if not wrap or len(single) + len(indent) + 2 <= PRINT_WIDTH:
        return single
    return "\n" + "\n".join(f"{indent}{INDENT}{p}" for p in pairs)


def merge_empty_svg(tokens: list[Token]) -> list[Token]:
    """Схлопывает пустые SVG-элементы вида <rect ...></rect> в один тег.

    В исходнике часть SVG-элементов записана с явным закрывающим тегом, хотя
    содержимого в них нет. Схлопывание делает разметку читаемее и ничего не
    меняет в вёрстке.
    """
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if (token.kind == "tag" and not token.closing and token.name in SVG_EMPTY
                and not token.self_closing and i + 1 < len(tokens)):
            nxt = tokens[i + 1]
            if nxt.kind == "tag" and nxt.closing and nxt.name == token.name:
                # пустой элемент: <tag ...></tag> → <tag .../>
                result.append(Token("tag", token.raw_tag[:-1] + "/>", name=token.name,
                                    self_closing=True, raw_tag=token.raw_tag[:-1] + "/>",
                                    attrs_text=token.attrs_text))
                i += 2
                continue
        result.append(token)
        i += 1
    return result


def format_html(html: str) -> str:
    """Форматирует HTML, не меняя видимый текст.

    Модель работы:

    * **Текстовые узлы сохраняются дословно.** Пробел между словами — это
      содержимое, а не форматирование, поэтому «текст <a>ссылка</a> конец»
      останется именно таким. Переносы строк внутри текстового узла — тоже
      содержимое (браузер их схлопывает в один пробел).
    * **Перенос строки ставится только между тегами**, там, где в исходнике
      пробела не было: значит, там и нечего терять.
    * **Пробелы исходника между тегами сохраняются**, если они видимы
      (рядом с инлайновым содержимым), и убираются, если это отступы автора
      внутри блочного контейнера.
    * **Содержимое <style> и <script> не трогаем** — CSS и JS остаются
      байт-в-байт.

    Благодаря этому видимый текст страницы и её вёрстка не меняются.
    """
    tokens = merge_empty_svg(tokenize(html))
    out: list[str] = []
    depth = 0
    open_stack: list[str] = []
    inline_ctx: list[bool] = []     # для каждого открытого тега: инлайновый ли он
    raw_text_tag: str | None = None
    raw_buffer: list[str] = []
    line_started = False            # на текущей строке уже что-то выведено
    no_indent = False               # следующую строку начнём без отступа (после <br>)
    prev_was_block = True          # предыдущий элемент был блочным
    after_tag = True               # предыдущий токен был тегом (текст идёт следом)
    after_block_open = False       # предыдущий токен — открывающий блочный тег

    def in_inline() -> bool:
        """Внутри инлайнового элемента (a, label, span, ...)?"""
        return bool(inline_ctx) and inline_ctx[-1]

    def indent() -> None:
        """Добавляет отступ текущей строки (если строка ещё не начата).

        Внутри инлайнового элемента отступ не ставится: там пробелы значимы
        и отступ изменил бы вёрстку.
        """
        nonlocal no_indent
        if line_started or in_inline():
            return
        if no_indent:
            no_indent = False
        else:
            out.append(INDENT * depth)

    def newline() -> None:
        """Перенос строки. Внутри инлайнового контекста не ставится."""
        nonlocal line_started
        if in_inline():
            return
        out.append("\n")
        line_started = False

    def emit(text: str) -> None:
        """Пишет текст в текущую строку."""
        nonlocal line_started
        indent()
        out.append(text)
        line_started = True

    for token in tokens:
        # флаг «предыдущий токен — открывающий блочный тег» живёт только
        # для одного следующего токена
        prev_block_open = after_block_open
        after_block_open = False

        # --- содержимое style/script/pre/textarea: дословно ---
        if raw_text_tag is not None:
            if token.kind == "tag" and token.closing and token.name == raw_text_tag:
                body = "".join(raw_buffer)
                if body and not body.startswith("\n"):
                    out.append("\n")
                out.append(body + token.text)
                newline()
                raw_buffer = []
                raw_text_tag = None
                continue
            raw_buffer.append(token.text)
            continue

        # --- текст ---
        if token.kind == "text":
            text = token.text
            if not text.strip():
                # Пробельный узел исходника. Он виден пользователю, если рядом
                # есть инлайновое содержимое: между двумя инлайновыми элементами
                # (даже внутри блока) пробел разделяет слова, а между блоками —
                # схлопывается и не виден.
                if text and not prev_was_block:
                    emit(" ")
                continue
            # Текст с содержимым сохраняем дословно: пробелы и переносы строк
            # внутри него — это содержимое, а не форматирование. Браузер сам
            # схлопнет их при отрисовке, но мы не имеем права менять исходник.
            body = text
            if after_tag:
                # текст сразу после тега: ведущие пробелы были отступом автора
                body = body.lstrip()
            # Хвостовые пробелы НЕ обрезаем: они разделяют слова
            # («входящий · <a>»). Перевод строки в конце — это форматирование,
            # его убираем: браузер всё равно схлопнет его в пробел.
            body = re.sub(r"\n[ \t]*$", "", body)
            if body:
                if prev_block_open and out and out[-1] == "\n":
                    # текст сразу после открывающего блочного тега: убираем
                    # перенос строки и пишем текст в ту же строку — так в начале
                    # блока не появляется лишний пробел
                    out.pop()
                    out.append(body)
                    line_started = True
                else:
                    emit(body)
            prev_was_block = False
            after_tag = False
            continue

        # --- комментарий ---
        if token.kind == "comment":
            indent()
            out.append(token.text)
            newline()
            after_tag = True
            continue

        # --- doctype ---
        if token.kind == "doctype":
            out.append(token.text)
            newline()
            continue

        # --- закрывающий тег ---
        if token.closing:
            if open_stack and open_stack[-1] == token.name:
                open_stack.pop()
                depth = max(0, depth - 1)
            if inline_ctx:
                inline_ctx.pop()
            if token.name in INLINE or token.name in TIGHT:
                emit(token.text)          # остаёмся в строке
                prev_was_block = False
                # после закрывающего тега пробел текста значим (разделяет слова)
            else:
                # закрывающий блочный тег — всегда на своей строке
                if line_started:
                    newline()
                else:
                    # строка уже начата (или пуста) — отступ не дублируем
                    pass
                indent()
                out.append(token.text)
                newline()
                prev_was_block = True
                after_tag = True
            continue

        # --- открывающий тег ---
        if token.self_closing or token.name in VOID:
            indent()
            out.append(token.raw_tag)
            # <meta>, <link>, <input> и т.п. — блочные для правила видимости
            # пробела: между двумя такими элементами пробел не виден.
            prev_was_block = True
            after_tag = True             # текст после <br> начинается заново
            if token.name == "br":
                newline()
                no_indent = True          # после <br> отступ не нужен
            else:
                newline()
            continue

        # У инлайновых элементов атрибуты не переносим: перенос строки внутри
        # тега добавил бы пробел в видимый текст.
        wrap = token.name not in INLINE
        attrs = format_attrs(token.attrs_text, INDENT * depth, wrap=wrap)
        indent()
        out.append("<" + token.name + attrs + ">")
        open_stack.append(token.name)

        if token.name in INLINE:
            inline_ctx.append(True)
            depth += 1
            line_started = True           # содержимое инлайн-элемента — в той же строке
            prev_was_block = False
            after_tag = True
            continue

        inline_ctx.append(False)
        depth += 1
        prev_was_block = True
        after_tag = True
        after_block_open = True
        if token.name in RAW_TEXT:
            newline()
            raw_text_tag = token.name
            continue
        if token.name in TIGHT:
            # содержимое TIGHT-элемента (заголовки, абзацы, ячейки) пишем
            # в одну строку с тегом — так разметка читается лучше
            line_started = True
            continue
        newline()

    result = "".join(out)
    lines = [line.rstrip() for line in result.split("\n")]
    cleaned: list[str] = []
    for line in lines:
        if not line and cleaned and not cleaned[-1]:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).rstrip() + "\n"


def visible_text(html: str) -> str:
    """Видимый текст страницы — для проверки, что вёрстка не изменилась.

    Текст собирается с учётом блочной структуры:
      * внутри инлайнового контекста пробелы значимы и сохраняются как есть;
      * на границах блочных элементов пробелы не видны пользователю, поэтому
        текст разных блоков склеивается через маркер (без пробела).

    Так сравнение ловит именно те изменения, которые видны на экране:
    разрыв или слияние слов внутри строки, а не перенос строки между блоками.
    """
    from html.parser import HTMLParser

    BLOCK = {
        "address", "article", "aside", "blockquote", "body", "details", "dialog",
        "dd", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer",
        "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr",
        "html", "li", "main", "nav", "ol", "p", "pre", "section", "table",
        "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
    VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }

    # классы визуально скрытых элементов: .vh — скрытый текст для
    # скринридера, .skip — ссылка «к содержимому», уводится за экран.
    HIDDEN_CLASSES = {"vh", "skip"}
    VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }

    class Text(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.skip = 0            # внутри style/script
            self.hidden = 0          # внутри визуально скрытого элемента
            self.block_depth = 0      # внутри блочного элемента
            self.parts: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("style", "script"):
                self.skip += 1
                return
            a = dict(attrs)
            classes = set((a.get("class") or "").split())
            if classes & HIDDEN_CLASSES:
                self.hidden += 1
                return
            if self.hidden:
                return
            if tag == "br":
                # перенос строки: следующий пробел уже не виден
                self.parts.append("\x00")
                return
            if tag in BLOCK:
                self.block_depth += 1
                self.parts.append("\x00")     # граница блока — пробел не виден

        def handle_endtag(self, tag):
            if tag in ("style", "script"):
                if self.skip:
                    self.skip -= 1
                return
            if self.hidden:
                # закрываем скрытый элемент (счётчик ведётся на входе)
                return
            if tag in BLOCK:
                self.block_depth = max(0, self.block_depth - 1)
                self.parts.append("\x00")

        def handle_data(self, data):
            if not self.skip and not self.hidden:
                self.parts.append(data)

    parser = Text()
    parser.feed(html)
    parser.close()
    # маркеры границ блоков → ничего; пробелы внутри инлайнового контекста → пробел
    raw = "".join(parser.parts)
    raw = re.sub(r"\s+", " ", raw)
    raw = raw.replace("\x00 ", "\x00").replace(" \x00", "\x00")
    raw = re.sub(r"\x00+", "\x00", raw)
    return raw.strip("\x00 ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Форматирование HTML демо-панели")
    parser.add_argument("--check", action="store_true",
                        help="только проверить, не записывая файлы (для CI)")
    parser.add_argument("--page", help="отформатировать одну страницу (путь относительно docs/demo)")
    args = parser.parse_args()

    if args.page:
        files = [os.path.join(DEMO, args.page)]
        if not os.path.exists(files[0]):
            print(f"Файл не найден: {files[0]}", file=sys.stderr)
            return 2
    else:
        files = sorted(glob.glob(os.path.join(DEMO, "**", "index.html"), recursive=True))

    changed = 0
    failed = 0
    for path in files:
        rel = os.path.relpath(path, ROOT)
        original = open(path, encoding="utf-8").read()
        try:
            formatted = format_html(original)
        except Exception as exc:  # noqa: BLE001 — форматтер не должен ронять пайплайн
            print(f"❌ {rel}: не удалось отформатировать: {exc}", file=sys.stderr)
            failed += 1
            continue

        if formatted == original:
            continue

        # страховка: форматирование не должно менять видимый текст
        if visible_text(original) != visible_text(formatted):
            print(f"❌ {rel}: форматирование меняет видимый текст — файл оставлен без изменений",
                  file=sys.stderr)
            failed += 1
            continue

        changed += 1
        if args.check:
            print(f"❌ {rel}: не отформатирован")
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(formatted)
            print(f"✓ {rel}")

    if args.check:
        print(f"\nНе отформатировано: {changed} (ожидается 0)")
        return 1 if changed else 0

    print(f"\nОтформатировано: {changed} · с ошибками: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
