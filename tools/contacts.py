#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Загрузчик contacts.yml — единого источника контактов Fonotext (#6).

Используется tools/build-docs-html.py (реквизиты в футере/JSON-LD/CTA) и
tools/check-contacts.py (валидация email в публичном контуре). Отдельный
модуль нужен, чтобы сборка и проверка не разъезжались в толковании схемы.

Использование из других скриптов tools/:
    from contacts import load_contacts
    c = load_contacts()          # raises ContactsError при невалидном конфиге
    c["contact"]["email"]        # канонический email

Запуск напрямую — самопроверка схемы:
    python3 tools/contacts.py
"""

from __future__ import annotations

import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTACTS_YML = os.path.join(ROOT, "contacts.yml")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class ContactsError(Exception):
    """Конфиг контактов отсутствует или не соответствует схеме."""


def _require_email(value, where: str) -> str:
    if not isinstance(value, str) or not EMAIL_RE.fullmatch(value.strip()):
        raise ContactsError(f"{where}: ожидается корректный email, получено {value!r}")
    return value.strip().lower()


def _check_entry(item, where: str, with_name: bool) -> None:
    if not isinstance(item, dict):
        raise ContactsError(f"{where}: элемент должен быть словарём")
    if with_name and not isinstance(item.get("name"), str):
        raise ContactsError(f"{where}: обязательно поле name")
    if "email" in item:
        _require_email(item["email"], f"{where}.email")


def load_contacts(path: str = CONTACTS_YML) -> dict:
    """Читает и валидирует contacts.yml. Падает с ContactsError при проблемах."""
    if yaml is None:
        raise ContactsError("Не установлен pyyaml (pip install pyyaml)")
    if not os.path.exists(path):
        raise ContactsError(f"Файл не найден: {path}")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ContactsError(f"{path}: верхний уровень должен быть словарём")

    org = data.get("organization")
    if not isinstance(org, dict) or not org.get("name"):
        raise ContactsError("organization.name обязателен")

    contact = data.get("contact")
    if not isinstance(contact, dict):
        raise ContactsError("Секция contact обязательна (email, phone)")
    contact["email"] = _require_email(contact.get("email"), "contact.email")
    if not isinstance(contact.get("phone", ""), str):
        raise ContactsError("contact.phone должен быть строкой")

    public_emails = data.get("public_emails")
    if not isinstance(public_emails, list) or not public_emails:
        raise ContactsError("public_emails обязателен: непустой список публичных email")
    data["public_emails"] = [_require_email(e, "public_emails[]") for e in public_emails]
    if contact["email"] not in data["public_emails"]:
        raise ContactsError("Канонический contact.email должен входить в public_emails")

    for i, alias in enumerate(data.get("aliases") or []):
        if not isinstance(alias, dict):
            raise ContactsError(f"aliases[{i}]: элемент должен быть словарём")
        _require_email(alias.get("email"), f"aliases[{i}].email")
        if alias.get("public", False):
            # публичный alias обязан быть разрешён и в public_emails
            if _require_email(alias["email"], f"aliases[{i}].email") not in data["public_emails"]:
                raise ContactsError(
                    f"aliases[{i}]: public: true, но адрес отсутствует в public_emails")

    for i, office in enumerate(data.get("offices") or []):
        _check_entry(office, f"offices[{i}]", with_name=False)
        if not isinstance(office.get("city", ""), str):
            raise ContactsError(f"offices[{i}].city должен быть строкой")
        if office.get("email_public") and not office.get("email"):
            raise ContactsError(f"offices[{i}]: email_public без email")

    for i, rep in enumerate(data.get("representatives") or []):
        _check_entry(rep, f"representatives[{i}]", with_name=True)
        if rep.get("email_public") and not rep.get("email"):
            raise ContactsError(f"representatives[{i}]: email_public без email")

    return data


def allowed_public_emails(data: dict) -> set[str]:
    """Все email, которые checker разрешает в публичных файлах.

    Сюда входят: public_emails (безусловно) и контакты офисов/представителей
    с флагом email_public: true (расширяемость схемы без правки checker'а).
    """
    allowed = set(data.get("public_emails", []))
    for group in ("offices", "representatives"):
        for item in data.get(group) or []:
            if item.get("email_public") and "email" in item:
                allowed.add(_require_email(item["email"], f"{group}.email"))
    return allowed


def selftest() -> int:
    data = load_contacts()
    print(f"OK: contacts.yml валиден; канонический email: {data['contact']['email']}")
    print(f"    разрешённые публичные email: {sorted(allowed_public_emails(data))}")
    return 0


if __name__ == "__main__":
    sys.exit(selftest())
