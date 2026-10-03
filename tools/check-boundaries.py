#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка границ контуров: не попали ли в публикуемые материалы внутренние данные.

Использование:
    python3 tools/check-boundaries.py handoff/investors-package-for-fonotext --profile handoff
    python3 tools/check-boundaries.py handoff/public-package --profile public
    python3 tools/check-boundaries.py docs README.md --profile public        # в репозитории продукта
    python3 tools/check-boundaries.py docs/investors --profile investor      # в репозитории продукта
    python3 tools/check-boundaries.py handoff --profile handoff --strict-money

Профили:
    public   — всё, что публикуется на сайте: запрещены внутренние пути, маржа, burn, MRR,
               закупка, BOM, имя заказчика.
    investor — инвесторский раздел: маржа и метрики модели допустимы; закупка, BOM и внутренние
               пути — запрещены; во всех *.html обязателен noindex.
    handoff  — сканирует стандартные пакеты передачи, подбирая профиль по каталогу.

Код возврата: 0 — чисто, 1 — есть нарушения (или незакрытые цифры при --strict-money).
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "governance", "boundaries.json")

TEXT_EXT = {".md", ".html", ".htm", ".txt", ".xml", ".json", ".py", ".sh", ".yml", ".yaml", ".csv"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "out", "dist", "coverage"}


def norm_money(token: str) -> str:
    t = token.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        x = float(t)
    except ValueError:
        return t
    return str(int(round(x))) if abs(x - round(x)) < 1e-9 else f"{x:g}"


def load_config() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def collect_files(paths: list, cfg: dict, base_profile: str) -> list:
    files = []
    for p in paths:
        if os.path.isfile(p):
            files.append(p)
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                full = os.path.join(dirpath, name)
                if os.path.abspath(full) == CONFIG:
                    continue
                # в пакетах передачи инструкции (README, сниппеты) внутренние — их не сканируем
                # investors-раздел в продукте проверяется отдельным investor-профилем
                if base_profile == "public" and os.path.join("docs", "investors") in full.replace("\\", "/"):
                    continue
                if base_profile == "handoff" and name in cfg.get("handoff_exclude_names", []):
                    continue
                if os.path.splitext(name)[1].lower() in TEXT_EXT and os.path.getsize(full) < 2_000_000:
                    files.append(full)
    return sorted(files)


def profile_for(path: str, base: str) -> str:
    if base != "handoff":
        return base
    p = path.replace("\\", "/")
    if "investors-package" in p:
        return "investor"
    if "public-package" in p:
        return "public"
    return ""  # вне пакетов — не проверяем


def check_file(path: str, cfg: dict, base_profile: str, strict_money: bool) -> tuple:
    profile = profile_for(path, base_profile)
    fails, warns, money_bad = [], [], []
    if not profile:
        return profile, fails, warns, money_bad

    text = open(path, encoding="utf-8", errors="ignore").read()

    # директивы в начале файла:
    #   boundaries-internal        — файл не публикуется, проверки профиля к нему не применяются
    #   boundaries-allow: id, id   — конкретные правила (например, файл сам перечисляет запреты)
    head = text[:2000]
    if re.search(r"boundaries-internal", head):
        print(f"  · пропущен по директиве boundaries-internal: {os.path.relpath(path, ROOT)}")
        return profile, fails, warns, money_bad
    allowed = set()
    m = re.search(r"boundaries-allow:\s*([A-Za-z0-9_,\s-]+)", head)
    if m:
        allowed = {x.strip() for x in m.group(1).replace(",", " ").split() if x.strip()}
    # строки директив не участвуют в проверке (иначе правила матчатся на самих себе)
    text = re.sub(r"^.*boundaries-(?:allow|internal).*$", "", text, flags=re.M)

    lines = text.splitlines()
    rules = cfg["profiles"][profile]

    for rule in rules.get("fail", []):
        if rule["id"] in allowed:
            continue
        rx = re.compile(rule["regex"])
        for n, line in enumerate(lines, 1):
            if rx.search(line):
                fails.append((path, n, rule["id"], rule["message"], line.strip()[:110]))
    for rule in rules.get("warn", []):
        rx = re.compile(rule["regex"])
        for n, line in enumerate(lines, 1):
            if rx.search(line):
                warns.append((path, n, rule["id"], rule["message"], line.strip()[:110]))

    # обязательный noindex для инвесторских HTML-страниц
    if profile == "investor" and path.lower().endswith((".html", ".htm")):
        if not re.search(r'name="robots"[^>]*content="[^"]*noindex', text, re.I):
            fails.append((path, 1, "noindex-missing",
                          "в инвесторской HTML-странице нет meta robots noindex", ""))

    # инвесторский раздел не должен попадать в служебные файлы публичного контура
    base = os.path.basename(path)
    if base in ("sitemap.xml", "llms.txt") and "investors" in text:
        fails.append((path, 1, "investor-in-public-index",
                      "инвесторский раздел упомянут в служебном файле публичного контура", ""))

    # незакрытые цифры
    if profile in ("public", "investor"):
        approved = {norm_money(v) for v in cfg["approved_public_money"]["values"]}
        if profile == "investor" and "approved_investor_money" in cfg:
            approved |= {norm_money(v) for v in cfg["approved_investor_money"].get("values", [])}
        rx = re.compile(cfg["money_regex"])
        for n, line in enumerate(lines, 1):
            for m in rx.finditer(line):
                token = m.group(1)
                if norm_money(token) not in approved:
                    money_bad.append((path, n, token, "цифра вне канона", line.strip()[:110]))

    return profile, fails, warns, money_bad


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка границ контуров")
    ap.add_argument("paths", nargs="+", help="файлы или каталоги для проверки")
    ap.add_argument("--profile", choices=["public", "investor", "handoff"], default="public")
    ap.add_argument("--strict-money", action="store_true",
                    help="считать нарушением любую цифру вне approved_public_money")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    files = collect_files(args.paths, cfg, args.profile)
    if not files:
        print("Нечего проверять: файлы не найдены.")
        return 0

    all_fails, all_warns, all_money, skipped = [], [], [], 0
    for path in files:
        profile, f, w, m = check_file(path, cfg, args.profile, args.strict_money)
        if not profile:  # файл вне проверяемых пакетов
            skipped += 1
            continue
        all_fails += f
        all_warns += w
        all_money += m

    def show(items, title, stream=sys.stdout):
        if not items:
            return
        print(f"\n{title}: {len(items)}")
        for path, n, ident, msg, line in items[:40]:
            rel = os.path.relpath(path, ROOT)
            print(f"  {rel}:{n}  [{ident}] {msg}")
            if line and not args.quiet:
                print(f"      │ {line}")

    print(f"Профиль: {args.profile}. Проверено файлов: {len(files)}"
          + (f" (пропущено {skipped} — вне пакетов)" if skipped else ""))
    show(all_fails, "НАРУШЕНИЯ (блокируют публикацию)", sys.stderr)
    show(all_warns, "Предупреждения", sys.stderr)

    if all_money:
        print(f"\nЦифры к проверке: {len(all_money)} (сверить с каноном; "
              f"{'--strict-money: считаются нарушением' if args.strict_money else 'предупреждение'})")
        seen = set()
        for path, n, token, msg, _line in all_money:
            key = norm_money(token)
            if key in seen:
                continue
            seen.add(key)
            rel = os.path.relpath(path, ROOT)
            print(f"  {token:>12}  ← {rel}:{n}")

    problems = len(all_fails) + (len(all_money) if args.strict_money else 0)
    if problems:
        print(f"\nИтог: {problems} проблем(ы) → публиковать нельзя.")
        return 1
    print("\nИтог: нарушений нет ✓" + (f" (цифр к проверке: {len(all_money)})" if all_money else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
