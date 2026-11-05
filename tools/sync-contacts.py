#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизация контактов в рукописных публичных файлах (#6/#7).

Сгенерированные страницы документации читают contacts.yml прямо при сборке
(tools/build-docs-html.py). Рукописные файлы — docs/index.html, docs/404.html,
docs/rechevaya-analitika/index.html и README.md — приводятся к конфигу этим
скриптом: любой непубличный alias (например, канон из contacts.yml, #7) заменяется
на канонический email из contacts.yml, где бы он ни встретился (текст,
mailto:href, JSON-LD, mailto с subject).

Скрипт идемпотентен. После правок запустите python3 tools/check-contacts.py.

    python3 tools/sync-contacts.py          # применить contacts.yml к рукописным файлам
    python3 tools/sync-contacts.py --check  # только проверить расхождения (CI-режим)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contacts import CONTACTS_YML, ROOT, load_contacts

# рукописные публичные файлы, не проходящие через build-docs-html.py
HANDWRITTEN = [
    os.path.join(ROOT, "README.md"),
    os.path.join(ROOT, "docs", "index.html"),
    os.path.join(ROOT, "docs", "404.html"),
    os.path.join(ROOT, "docs", "rechevaya-analitika", "index.html"),
    os.path.join(ROOT, "docs", "we-vs-market-2026.html"),
    os.path.join(ROOT, "docs", "09-competitive-landscape.html"),
    os.path.join(ROOT, "docs", "06-pricing.html"),
    os.path.join(ROOT, "docs", "12-kak-ustroena-nasha-cena.html"),
    os.path.join(ROOT, "docs", "00-product-presentation.md"),
    os.path.join(ROOT, "docs", "llms.txt"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="не менять файлы, только сообщить о расхождениях")
    args = ap.parse_args()

    cfg = load_contacts(CONTACTS_YML)
    canonical = cfg["contact"]["email"]
    # непубличные alias: в публичных текстах им место не в цепочке (их берём из конфига,
    # включая расширяемые секции offices/representatives без email_public)
    stale: set[str] = set()
    for alias in cfg.get("aliases") or []:
        if not alias.get("public", False):
            stale.add(alias["email"].lower())
    for group in ("offices", "representatives"):
        for item in cfg.get(group) or []:
            if item.get("email") and not item.get("email_public", False):
                stale.add(item["email"].lower())
    stale.discard(canonical)

    if not stale:
        print("OK: непубличных alias нет, заменять нечего.")
        return 0

    changed = []
    for path in HANDWRITTEN:
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        new = text
        for bad in sorted(stale):
            new = new.replace(bad, canonical).replace(
                bad.replace("@", "%40"), canonical.replace("@", "%40"))
        if new != text:
            if args.check:
                changed.append(os.path.relpath(path, ROOT))
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new)
                changed.append(os.path.relpath(path, ROOT))

    verb = "расходуется с contacts.yml" if args.check else "обновлён"
    if changed:
        for name in changed:
            print(f"  {verb}: {name}")
        if args.check:
            print("Запустите: python3 tools/sync-contacts.py", file=sys.stderr)
            return 1
        print(f"Готово: канонический email — {canonical}. "
              "Проверка: python3 tools/check-contacts.py")
    else:
        print(f"OK: рукописные файлы уже соответствуют contacts.yml ({canonical}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
