#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Реестр документации проекта: проверка, индекс, новые артефакты.

Правила документооборота — `governance/DOCS.md`. Реестр постоянных документов —
`governance/docs.yml`. Живой индекс для людей — `governance/DOCS-INDEX.md`
(генерируется, руками не правится).

Использование:
    python3 tools/docs-registry.py --check            # проверка (CI)
    python3 tools/docs-registry.py --check --strict   # просроченные ревизии = нарушение
    python3 tools/docs-registry.py --check --changed-only docs/02-architecture.md
    python3 tools/docs-registry.py --index            # пересобрать индекс
    python3 tools/docs-registry.py --check-index      # индекс не разъехался с реестром
    python3 tools/docs-registry.py --new research "рынок-речевой-аналитики"
    python3 tools/docs-registry.py --deprecate docs/02-architecture.md --by docs/03-models.md

Код возврата: 0 — чисто, 1 — есть нарушения (или индекс разъехался).
"""
import argparse
import datetime as dt
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "governance", "docs.yml")
INDEX = os.path.join(ROOT, "governance", "DOCS-INDEX.md")

RULES_HINT = "Правила — governance/DOCS.md"

STATUS_LABEL = {
    "active": "актуален",
    "draft": "черновик",
    "deprecated": "устарел",
    "archived": "архив",
    "tombstone": "снят с публикации",
}
STATUS_ORDER = ["active", "draft", "deprecated", "archived", "tombstone"]
ARTIFACT_STATUS = {"active", "superseded", "archived"}

HEADER_RE = re.compile(r"<!--\s*artifact\s*\n(.*?)-->", re.S)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"```.*?```", re.S)


class Report:
    """Набор находок проверки: нарушения (блокируют) и предупреждения."""

    def __init__(self):
        self.fails = []
        self.warns = []

    def fail(self, where, message):
        self.fails.append((where, message))

    def warn(self, where, message):
        self.warns.append((where, message))

    def ok(self):
        return not self.fails


# ---------------------------------------------------------------- конфигурация

def load_config():
    try:
        import yaml
    except ImportError:
        sys.exit("Нужен PyYAML: python3 -m pip install pyyaml")
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def glob_to_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def match_any(path, patterns):
    return any(glob_to_regex(p).match(path) for p in patterns or [])


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ---------------------------------------------------------------- git-даты

_git_cache = {}


def git_date(path):
    """Дата последнего коммита, который трогал файл (YYYY-MM-DD) или ''."""
    p = rel(path)
    if p in _git_cache:
        return _git_cache[p]
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", p],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    _git_cache[p] = out
    return out


def parse_date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def today():
    override = os.environ.get("DOCS_TODAY")
    return parse_date(override) if override else dt.date.today()


# ---------------------------------------------------------------- шапка артефакта

def parse_artifact(path):
    """Разобрать шапку `<!-- artifact ... -->`. Возвращает dict или None."""
    text = read(path)
    m = HEADER_RE.search(text)
    if not m:
        return None
    data = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip().lower()] = value.strip()
    data["_text"] = text
    data["_header_span"] = (m.start(), m.end())
    return data


def first_h1(text):
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def doc_date(path):
    """Дата документа: шапка артефакта → git → mtime."""
    if path.endswith(".md"):
        art = parse_artifact(path)
        if art and parse_date(art.get("date")):
            return parse_date(art["date"])
    d = parse_date(git_date(path))
    if d:
        return d
    return dt.date.fromtimestamp(os.path.getmtime(path))


# ---------------------------------------------------------------- сбор файлов

_tracked = None


def tracked_files():
    """Файлы под git. Документом считается то, что закоммичено: черновики на диске
    не блокируют CI и не занимают место в реестре, но попадают в предупреждения."""
    global _tracked
    if _tracked is not None:
        return _tracked
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             capture_output=True, text=True, timeout=30).stdout
        _tracked = {p.replace(os.sep, "/") for p in out.split("\0") if p}
    except (OSError, subprocess.SubprocessError):
        _tracked = None
    return _tracked


def managed_files(cfg):
    """Все файлы, которые обязаны быть зарегистрированы."""
    patterns = cfg.get("managed") or []
    excludes = cfg.get("exclude") or []
    tracked = tracked_files()
    if tracked is None:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in {".git", "node_modules", "__pycache__", ".venv", ".zwork"})
            for name in sorted(filenames):
                candidates.append(rel(os.path.join(dirpath, name)))
    else:
        candidates = sorted(tracked)
    result = []
    for p in candidates:
        if not p.endswith(".md"):
            continue
        if match_any(p, excludes):
            continue
        if match_any(p, patterns) and os.path.exists(os.path.join(ROOT, p)):
            result.append(p)
    return sorted(result)


def artifact_areas(cfg):
    return (cfg.get("artifacts") or {}).get("areas") or []


def is_artifact(p, cfg):
    return match_any(p, [a.get("path") for a in artifact_areas(cfg) if a.get("path")])


def is_strict_artifact(p, cfg):
    for area in artifact_areas(cfg):
        if area.get("path") and glob_to_regex(area["path"]).match(p):
            return bool(area.get("strict", True))
    return False


# ---------------------------------------------------------------- проверки

def check_manifest(cfg, rep):
    docs = cfg.get("documents") or []
    seen = {}
    paths = []
    for entry in docs:
        path = entry.get("path")
        if not path:
            rep.fail("governance/docs.yml", "запись без path")
            continue
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            rep.fail(path, "зарегистрирован, но файла нет — удалить запись или вернуть файл")
            continue
        if path in seen:
            rep.fail(path, "зарегистрирован дважды")
        seen[path] = entry
        paths.append(path)

        status = entry.get("status", "active")
        if status not in STATUS_LABEL:
            rep.fail(path, f"неизвестный статус «{status}»")
        if status in ("deprecated", "archived"):
            by = entry.get("superseded_by")
            if not by:
                rep.fail(path, f"статус «{status}», но не указано superseded_by — читателю некуда идти")
            elif not re.match(r"^https?://", str(by)):
                if not os.path.exists(os.path.join(ROOT, by)):
                    rep.fail(path, f"superseded_by указывает на несуществующий «{by}»")
        if entry.get("build") == "html":
            if os.path.basename(path) == "README.md":
                html = os.path.join(os.path.dirname(path), "index.html")
            else:
                html = path[:-3] + ".html"
            if not os.path.exists(os.path.join(ROOT, html)):
                rep.warn(path, f"ожидалась собранная страница {html} — пересобрать tools/build-docs-html.py")

    return seen, paths


def check_registration(cfg, rep, manifest_paths, changed_only):
    registered = set(manifest_paths)
    for p in managed_files(cfg):
        if p in registered or is_artifact(p, cfg):
            continue
        if changed_only and p not in changed_only:
            rep.warn(p, "новый документ не зарегистрирован (проверяется только изменённое — попадёт в следующую ревизию)")
            continue
        rep.fail(p, "документ не зарегистрирован в governance/docs.yml — добавь запись или перенеси в артефакты")


def check_artifacts(cfg, rep, changed_only):
    limits = cfg.get("limits") or {}
    stale_days = int(limits.get("stale_artifact_days", 120))
    review_days = int(limits.get("artifact_review_days", 180))
    now = today()
    found = []
    legacy = {}
    tracked = sorted(tracked_files() or [])
    for area in artifact_areas(cfg):
        pattern = area.get("path")
        if not pattern:
            continue
        strict = bool(area.get("strict", True))
        area_re = glob_to_regex(pattern)
        for p in tracked:
            if not p.endswith(".md") or not area_re.match(p):
                continue
            if os.path.basename(p) == "README.md":
                continue  # README — навигация по зоне, а не артефакт
            full = os.path.join(ROOT, p)
            if not os.path.exists(full):
                continue
            fallback = os.path.splitext(os.path.basename(p))[0]
            art = parse_artifact(full)
            if art is None:
                if strict and (not changed_only or p in changed_only):
                    rep.fail(p, "у артефакта нет шапки <!-- artifact … --> — заполни по governance/templates/ARTIFACT.md")
                elif strict:
                    rep.warn(p, "у артефакта нет шапки — новый файл обязан её иметь")
                else:
                    legacy[pattern] = legacy.get(pattern, 0) + 1
                found.append({
                    "path": p, "title": first_h1(read(full)) or fallback,
                    "date": doc_date(full), "status": "active", "owner": "—",
                    "area": pattern, "header": False,
                })
                continue

            status = art.get("status", "active")
            date = parse_date(art.get("date"))
            if status not in ARTIFACT_STATUS:
                rep.fail(p, f"неизвестный статус артефакта «{status}» (можно: {', '.join(sorted(ARTIFACT_STATUS))})")
            if not date:
                rep.fail(p, "в шапке нет корректной даты `date: ГГГГ-ММ-ДД`")
            if not art.get("type"):
                rep.fail(p, "в шапке нет `type:` (research / audit / report / decision / handoff)")
            if status in ("superseded", "archived"):
                if not art.get("superseded_by"):
                    rep.fail(p, f"статус «{status}», но не указано `superseded_by:`")
                elif "⚠️" not in art["_text"]:
                    rep.fail(p, "нет видимого баннера об устаревании — читатель не узнает, что документ заменён")
            if status == "active":
                review_after = parse_date(art.get("review_after")) or (
                    date + dt.timedelta(days=review_days) if date else None
                )
                if review_after and now > review_after:
                    rep.warn(p, f"ревизия просрочена на {(now - review_after).days} дн. (была {review_after})")
                if date and (now - date).days > stale_days:
                    rep.warn(p, f"артефакту {(now - date).days} дн. — проверь, не устарел ли вывод")

            found.append({
                "path": p, "title": first_h1(art["_text"]) or fallback,
                "date": date, "status": status, "owner": art.get("owner", "—"),
                "area": pattern, "header": True,
            })
    for pattern, count in sorted(legacy.items()):
        rep.warn(pattern, f"легаси-зона: {count} файлов без шапки — шапка добавляется при следующей правке")
    return found


def check_untracked(cfg, rep):
    """Документ на диске, но не в git: работа, которую не найдут ни агенты, ни человек."""
    tracked = tracked_files()
    if tracked is None:
        return
    zones = list(cfg.get("managed") or []) + [a["path"] for a in artifact_areas(cfg) if a.get("path")]
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in {".git", "node_modules", "__pycache__", ".venv", ".zwork"})
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            p = rel(os.path.join(dirpath, name))
            if p in tracked or not match_any(p, zones):
                continue
            rep.warn(p, "документ есть на диске, но не в git — без коммита он потеряется; закоммить или удали")


def check_reviews(cfg, rep, manifest, strict):
    limits = cfg.get("limits") or {}
    default_days = int(limits.get("default_review_days", 180))
    grace = int(limits.get("overdue_grace_days", 0))
    now = today()
    for path, entry in manifest.items():
        if entry.get("status") in ("deprecated", "archived", "tombstone"):
            continue
        days = int(entry.get("review_days", default_days))
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            continue
        due = doc_date(full) + dt.timedelta(days=days)
        if now <= due:
            continue
        overdue = (now - due).days
        message = f"ревизия просрочена на {overdue} дн. (была {due}) — подтверди актуальность или переведи в устаревшие"
        if strict and overdue > grace:
            rep.fail(path, message)
        else:
            rep.warn(path, message)


def check_links(rep, cfg):
    zones = [("governance/**/*.md", True)]
    for area in artifact_areas(cfg):
        if area.get("path"):
            zones.append((area["path"], bool(area.get("strict", True))))
    broken = {}
    for p in sorted(tracked_files() or []):
        if not p.endswith(".md"):
            continue
        strict = None
        for pattern, area_strict in zones:
            if glob_to_regex(pattern).match(p):
                strict = area_strict
                break
        if strict is None:
            continue
        full = os.path.join(ROOT, p)
        if not os.path.exists(full):
            continue
        text = FENCE_RE.sub("", read(full))
        for target in LINK_RE.findall(text):
            if re.match(r"^(https?:|mailto:|tel:|#)", target):
                continue
            clean = target.split("#")[0]
            if not clean:
                continue
            dest = os.path.normpath(os.path.join(os.path.dirname(full), clean))
            if os.path.exists(dest):
                continue
            if strict:
                rep.fail(p, f"битая ссылка: {target}")
            else:
                broken[p] = broken.get(p, 0) + 1
    if broken:
        total = sum(broken.values())
        examples = ", ".join(sorted(broken)[:3])
        rep.warn("легаси-зоны", f"{total} битых ссылок в {len(broken)} файлах (например: {examples}) — правятся при миграции")


def check_orphans(cfg, rep, manifest):
    """HTML верхнего уровня docs/ без источника — либо ручная страница, либо сирота."""
    known = set(manifest)
    for name in sorted(os.listdir(os.path.join(ROOT, "docs"))):
        if not name.endswith(".html"):
            continue
        html = f"docs/{name}"
        src = html[:-5] + ".md"
        if os.path.exists(os.path.join(ROOT, src)):
            continue
        if html not in known:
            rep.warn(html, "страница без markdown-источника и без записи в реестре — ручная или забытая")


def check_duplicates(rep, artifacts):
    by_title = {}
    for a in artifacts:
        key = re.sub(r"[\s\-–—:«»\"'()]+", " ", a["title"].lower()).strip()
        key = re.sub(r"^\d+\s+", "", key)
        by_title.setdefault(key, []).append(a["path"])
    for key, paths in by_title.items():
        if len(paths) > 1 and key:
            rep.warn(", ".join(paths), f"похожие заголовки ({len(paths)} файла) — возможно, дубль")


def run_check(cfg, strict=False, changed_only=None, quiet=False):
    rep = Report()
    manifest, paths = check_manifest(cfg, rep)
    check_registration(cfg, rep, paths, changed_only)
    artifacts = check_artifacts(cfg, rep, changed_only)
    check_reviews(cfg, rep, manifest, strict)
    check_links(rep, cfg)
    checks = cfg.get("checks") or {}
    if checks.get("orphans", True):
        check_orphans(cfg, rep, manifest)
    if checks.get("duplicates", True):
        check_duplicates(rep, artifacts)
    check_untracked(cfg, rep)
    return rep, manifest, artifacts


# ---------------------------------------------------------------- генерация индекса

def build_index(cfg, manifest, artifacts):
    limits = cfg.get("limits") or {}
    type_titles = cfg.get("type_titles") or {}
    order = cfg.get("type_order") or list(type_titles)
    now = today()
    docs = []
    for path, entry in manifest.items():
        if not os.path.exists(os.path.join(ROOT, path)):
            continue
        days = int(entry.get("review_days", limits.get("default_review_days", 180)))
        due = doc_date(os.path.join(ROOT, path)) + dt.timedelta(days=days)
        docs.append({
            "path": path,
            "title": entry.get("title") or path,
            "type": entry.get("type", "page"),
            "status": entry.get("status", "active"),
            "owner": entry.get("owner", "—"),
            "updated": doc_date(os.path.join(ROOT, path)),
            "due": due,
            "overdue": now > due and entry.get("status", "active") not in ("deprecated", "archived", "tombstone"),
            "superseded_by": entry.get("superseded_by", ""),
            "build": entry.get("build", ""),
        })

    active = [d for d in docs if d["status"] in ("active", "draft")]
    stale = [d for d in docs if d["status"] in ("deprecated", "archived", "tombstone")]
    overdue = [d for d in active if d["overdue"]]
    arts = sorted([a for a in artifacts if a["date"]], key=lambda a: a["date"], reverse=True)
    art_active = [a for a in arts if a["status"] == "active"]
    art_stale = [a for a in arts if a["status"] != "active"]

    out = []
    a = out.append

    def link(relpath, text):
        full = os.path.normpath(os.path.join(ROOT, "governance", relpath))
        return f"[{text}]({relpath})" if os.path.exists(full) else text

    a("# Индекс документации Fonotext")
    a("")
    a("> **Файл сгенерирован** `tools/docs-registry.py --index`. Руками не правится:"
      " правка — в `governance/docs.yml` (реестр) или в шапке артефакта.")
    a("> Правила, по которым этот индекс живёт, — " + link("DOCS.md", "DOCS.md") + ".")
    a("")
    a(f"**Реестр:** `governance/docs.yml`, версия {cfg.get('version', '—')},"
      f" обновлён {cfg.get('updated', '—')} · **контур:** {cfg.get('contour', '—')}")
    a("")
    a(f"| Всего | Актуально | Устарело | Просрочили ревизию | Артефактов |")
    a("|---|---|---|---|---|")
    a(f"| {len(docs)} | {len(active)} | {len(stale)} | {len(overdue)} | {len(arts)} |")
    a("")
    a("## Как этим пользоваться")
    a("")
    a("| Вопрос | Ответ |")
    a("|---|---|")
    a("| Где правила? | " + link("DOCS.md", "DOCS.md") + " — типы документов, жизненный цикл, что где живёт |")
    a("| Что актуально сейчас? | таблицы ниже: статус «актуален» и дата последней правки |")
    a("| Чем заменён устаревший документ? | раздел «Устарело и заменено» — там указана замена |")
    a("| Куда положить ресёрч или аудит? | " + link("../artifacts/README.md", "artifacts/") + " + шапка из `templates/ARTIFACT.md` |")
    a("| Что делать регулярно? | " + link("recurring/docs-review.md", "recurring/docs-review.md") + " и задача с меткой `docs-review` |")
    a("")

    for type_id in order:
        group = [d for d in docs if d["type"] == type_id and d["status"] in ("active", "draft")]
        if not group:
            continue
        a(f"## {type_titles.get(type_id, type_id)}")
        a("")
        a("| Документ | Статус | Обновлён | Ревизия до | Владелец |")
        a("|---|---|---|---|---|")
        for d in sorted(group, key=lambda x: x["path"]):
            link = f"[{d['title']}](../{d['path']})"
            due = f"{d['due']}" if not d["overdue"] else f"⚠️ {d['due']}"
            a(f"| {link} | {STATUS_LABEL.get(d['status'], d['status'])} | {d['updated']} | {due} | {d['owner']} |")
        a("")

    a("## Артефакты: ресёрч, аудит, выводы")
    a("")
    if art_active:
        a(f"Актуальных: {len(art_active)}. Свежие сверху; полный список — в каталогах зон.")
        a("")
        a("| Дата | Артефакт | Тип | Владелец |")
        a("|---|---|---|---|")
        for art in art_active[:60]:
            link = f"[{art['title']}](../{art['path']})"
            a(f"| {art['date']} | {link} | {art['path'].split('/')[1] if '/' in art['path'] else '—'} | {art['owner']} |")
        if len(art_active) > 60:
            a("")
            a(f"…и ещё {len(art_active) - 60} — см. каталоги зон артефактов.")
    else:
        a("Актуальных артефактов нет.")
    a("")

    if overdue:
        a("## Просрочили ревизию")
        a("")
        a("| Документ | Ревизия была | Просрочка |")
        a("|---|---|---|")
        for d in sorted(overdue, key=lambda x: x["due"]):
            a(f"| [{d['title']}](../{d['path']}) | {d['due']} | {(now - d['due']).days} дн. |")
        a("")

    if stale or art_stale:
        a("## Устарело и заменено")
        a("")
        a("| Документ | Статус | Замена |")
        a("|---|---|---|")
        for d in sorted(stale, key=lambda x: x["path"]):
            by = d["superseded_by"] or "—"
            if by and not re.match(r"^https?://", by):
                by = f"[{by}](../{by})"
            a(f"| [{d['title']}](../{d['path']}) | {STATUS_LABEL.get(d['status'], d['status'])} | {by} |")
        for art in sorted(art_stale, key=lambda x: x["date"], reverse=True):
            a(f"| [{art['title']}](../{art['path']}) | устарел | см. шапку файла |")
        a("")

    a("---")
    a("")
    a("Индекс пересобирается командой `python3 tools/docs-registry.py --index`;"
      " CI проверяет, что он не разъехался с реестром (`--check-index`).")
    a("")
    return "\n".join(out)


# ---------------------------------------------------------------- команды

def cmd_new(args, cfg):
    types = (cfg.get("artifacts") or {}).get("types") or ["research", "audit", "report"]
    kind = args.new
    if kind not in types:
        sys.exit(f"Неизвестный тип «{kind}». Доступны: {', '.join(types)}")
    folders = {"research": "research", "audit": "audit", "report": "reports",
               "decision": "decisions", "handoff": "handoffs"}
    folder = folders.get(kind, kind)
    slug = re.sub(r"[^a-z0-9а-яё\-]+", "-", args.slug.strip().lower()).strip("-")
    if not slug:
        sys.exit("Нужен slug: латиницей или кириллицей, через дефис")
    date = today()
    path = os.path.join(ROOT, "artifacts", folder, f"{date}-{slug}.md")
    if os.path.exists(path):
        sys.exit(f"Файл уже есть: {rel(path)}")
    review = date + dt.timedelta(days=int((cfg.get("limits") or {}).get("artifact_review_days", 180)))
    body = f"""<!-- artifact
type: {kind}
date: {date}
status: active
owner: {args.owner}
contour: {cfg.get('contour', 'public')}
review_after: {review}
sources:
-->

# {args.title or args.slug}

## Вопрос

<Что проверяли и зачем. Одно-два предложения.>

## Что проверено

| Источник | Что взято | Дата проверки |
|---|---|---|
| | | {date} |

## Выводы

<Только то, что подтверждается источниками выше. Непроверенное — помечай «не знаю».>

## Что делать

<Следствия: что меняем, что не меняем, что уходит в заявку.>

## Источники

<Полные пути или URL. Для внутренних источников — имя файла закрытого контура.>
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"Создан {rel(path)}")
    print("Дальше: заполнить разделы, затем `python3 tools/docs-registry.py --index`")
    return 0


def cmd_deprecate(args, cfg):
    target = args.deprecate
    target = rel(os.path.abspath(target)) if os.path.isabs(target) else target
    full = os.path.join(ROOT, target)
    if not os.path.exists(full):
        sys.exit(f"Нет файла {target}")
    if args.by:
        by = args.by
        if not re.match(r"^https?://", by):
            if not os.path.exists(os.path.join(ROOT, by)):
                sys.exit(f"Замена не найдена: {by}")
        if os.path.isabs(by):
            by = rel(by)
    else:
        by = ""

    if is_artifact(target, cfg):
        art = parse_artifact(full)
        if not art:
            sys.exit("У артефакта нет шапки — переведи вручную по governance/DOCS.md §5")
        text = art["_text"]
        start, end = art["_header_span"]
        header = text[start:end]
        header = re.sub(r"^status:.*$", "status: superseded", header, flags=re.M)
        if "superseded_by:" not in header:
            header = header.replace("-->\n", f"superseded_by: {by}\n-->\n") if by else header
        else:
            header = re.sub(r"^superseded_by:.*$", f"superseded_by: {by}", header, flags=re.M)
        banner = f"> ⚠️ **Устарело** ({today()}). Замена: {by or 'не указана — см. задачу'}.\n\n"
        text = text[:start] + header + "\n" + banner + text[end:].lstrip("\n")
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Артефакт переведён в устаревшие: {target}")
    else:
        raw = read(CONFIG)
        block = re.search(r"(?ms)^  - path: " + re.escape(target) + r"\n(.*?)(?=^  - path: |\Z)", raw)
        if not block:
            sys.exit(f"{target} нет в governance/docs.yml — добавь запись вручную")
        body = block.group(1)
        if re.search(r"^    status:", body, re.M):
            body = re.sub(r"^    status:.*$", "    status: deprecated", body, flags=re.M)
        else:
            body = "    status: deprecated\n" + body
        if by:
            if re.search(r"^    superseded_by:", body, re.M):
                body = re.sub(r"^    superseded_by:.*$", f"    superseded_by: {by}", body, flags=re.M)
            else:
                body = body.rstrip("\n") + f"\n    superseded_by: {by}\n"
        raw = raw[:block.start(1)] + body + raw[block.end(1):]
        with open(CONFIG, "w", encoding="utf-8") as fh:
            fh.write(raw)
        print(f"Реестр: {target} → deprecated" + (f", замена {by}" if by else ""))
    print("Дальше: `python3 tools/docs-registry.py --index` и коммит обоих файлов.")
    return 0


def print_report(rep, manifest, artifacts, cfg):
    print(f"Проверка документооборота · контур {cfg.get('contour', '—')} · реестр governance/docs.yml")
    print(f"Документов в реестре: {len(manifest)} · артефактов: {len(artifacts)}")
    print("")
    if rep.fails:
        print(f"НАРУШЕНИЯ ({len(rep.fails)}) — блокируют:")
        for where, message in rep.fails:
            print(f"  ✗ {where} — {message}")
        print("")
    if rep.warns:
        print(f"ПРЕДУПРЕЖДЕНИЯ ({len(rep.warns)}):")
        for where, message in rep.warns:
            print(f"  ⚠ {where} — {message}")
        print("")
    if rep.ok():
        print(f"Итог: 0 нарушений, {len(rep.warns)} предупреждений ✓")
    else:
        print(f"Итог: {len(rep.fails)} нарушений, {len(rep.warns)} предупреждений")
        print(RULES_HINT)


def main():
    parser = argparse.ArgumentParser(description="Реестр документации: проверка и индекс")
    parser.add_argument("--check", action="store_true", help="проверить реестр и артефакты")
    parser.add_argument("--strict", action="store_true", help="просроченная ревизия = нарушение")
    parser.add_argument("--changed-only", nargs="*", default=None,
                        help="проверять строго только перечисленные файлы (для PR)")
    parser.add_argument("--index", action="store_true", help="пересобрать governance/DOCS-INDEX.md")
    parser.add_argument("--check-index", action="store_true", help="индекс не разъехался с реестром")
    parser.add_argument("--new", metavar="TYPE", help="создать артефакт: research / audit / report")
    parser.add_argument("slug_pos", nargs="?", default="", help="короткое имя файла (позиционно)")
    parser.add_argument("--slug", default="", help="короткое имя файла для --new")
    parser.add_argument("--title", default="", help="заголовок для --new")
    parser.add_argument("--owner", default="research", help="владелец для --new")
    parser.add_argument("--deprecate", metavar="PATH", help="перевести документ в устаревшие")
    parser.add_argument("--by", default="", help="путь или URL замены для --deprecate")
    args = parser.parse_args()

    cfg = load_config()

    if args.new:
        args.slug = args.slug or args.slug_pos
        return cmd_new(args, cfg)
    if args.deprecate:
        return cmd_deprecate(args, cfg)

    if args.index or args.check_index:
        rep, manifest, artifacts = run_check(cfg, strict=False)
        text = build_index(cfg, manifest, artifacts)
        if args.index:
            with open(INDEX, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"Индекс пересобран: {rel(INDEX)} ({len(manifest)} документов, {len(artifacts)} артефактов)")
            if rep.fails:
                print(f"Внимание: при проверке найдено нарушений — {len(rep.fails)}. Подробнее: --check")
            return 0
        current = read(INDEX) if os.path.exists(INDEX) else ""
        if current != text:
            print("Индекс разъехался с реестром — запусти `python3 tools/docs-registry.py --index`")
            return 1
        print("Индекс соответствует реестру ✓")
        return 0

    rep, manifest, artifacts = run_check(cfg, strict=args.strict, changed_only=args.changed_only)
    print_report(rep, manifest, artifacts, cfg)
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
