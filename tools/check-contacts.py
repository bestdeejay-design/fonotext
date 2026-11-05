#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Валидатор контактов (#6): в публичном контуре разрешены только email из contacts.yml.

Проверяет docs/ и README.md: любой email-адрес, встреченный в текстовых файлах,
должен входить в список разрешённых (public_emails + контакты офисов/представителей
с email_public: true — см. tools/contacts.py). Иначе — ненулевой код возврата,
публикация запрещена.

    python3 tools/check-contacts.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contacts import EMAIL_RE, ROOT, allowed_public_emails, load_contacts

# публичный контур: сайт + README
SCAN_ROOTS = [os.path.join(ROOT, "docs"), os.path.join(ROOT, "README.md")]
# текстовые расширения, где может встретиться email (бинарные и картинки пропускаем)
TEXT_EXT = {".html", ".md", ".txt", ".xml", ".js", ".json", ".webmanifest", ".svg",
            ".css", ".yml", ".yaml", ".csv", ".py"}
SKIP_DIRS = {"social", "og"}  # сгенерированные ассеты без текстовых email-контрактов


def iter_files():
    for root in SCAN_ROOTS:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if os.path.splitext(name)[1].lower() in TEXT_EXT:
                    yield os.path.join(dirpath, name)


def main() -> int:
    try:
        data = load_contacts()
    except Exception as exc:
        print(f"ОШИБКА: contacts.yml невалиден: {exc}", file=sys.stderr)
        return 2
    allowed = allowed_public_emails(data)
    canonical = data["contact"]["email"]

    violations: list[str] = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        rel = os.path.relpath(path, ROOT)
        try:
            text = open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        for m in EMAIL_RE.finditer(text):
            email = m.group(0).lower()
            if email not in allowed:
                line = text[:m.start()].count("\n") + 1
                violations.append(f"{rel}:{line}: {email} (разрешены: {', '.join(sorted(allowed))})")

    if violations:
        print(f"НАРУШЕНИЯ ({len(violations)}): email вне contacts.yml в публичном контуре:")
        for v in violations:
            print(f"  {v}")
        print("Публикация запрещена. Добавьте адрес в contacts.yml (public_emails) "
              "или устраните из текста; канонический email — "
              f"{canonical} (#7).")
        return 1
    print(f"OK: {scanned} файлов, все email в публичном контуре разрешены contacts.yml "
          f"(канонический: {canonical}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
