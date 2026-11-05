# Индекс документации Fonotext

> **Файл сгенерирован** `tools/docs-registry.py --index`. Руками не правится: правка — в `governance/docs.yml` (реестр) или в шапке артефакта.
> Правила, по которым этот индекс живёт, — [DOCS.md](DOCS.md).

**Реестр:** `governance/docs.yml`, версия 1, обновлён 2026-11-04 · **контур:** public

| Всего | Актуально | Устарело | Просрочили ревизию | Артефактов |
|---|---|---|---|---|
| 43 | 14 | 29 | 0 | 0 |

## Как этим пользоваться

| Вопрос | Ответ |
|---|---|
| Где правила? | [DOCS.md](DOCS.md) — типы документов, жизненный цикл, что где живёт |
| Что актуально сейчас? | таблицы ниже: статус «актуален» и дата последней правки |
| Чем заменён устаревший документ? | раздел «Устарело и заменено» — там указана замена |
| Куда положить ресёрч или аудит? | [artifacts/](../artifacts/README.md) + шапка из `templates/ARTIFACT.md` |
| Что делать регулярно? | [recurring/docs-review.md](recurring/docs-review.md) и задача с меткой `docs-review` |

## Точка входа

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [README — карта продукта и документации](../README.md) | актуален | 2026-11-05 | 2027-02-03 | product |

## Страницы сайта

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [Страница 404](../docs/404.html) | актуален | 2026-11-05 | 2027-11-05 | tech |
| [Демо-панель продукта](../docs/demo/index.html) | актуален | 2026-10-29 | 2027-01-27 | product |
| [Лендинг fonotext.ru](../docs/index.html) | актуален | 2026-11-05 | 2027-02-03 | product |

## Правила и регламенты

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [Правила для агентов](../AGENTS.md) | актуален | 2026-11-04 | 2027-02-02 | governance |
| [CLAUDE.md — указатель на правила](../CLAUDE.md) | актуален | 2026-11-04 | 2027-02-02 | governance |
| [Документооборот: правила](../governance/DOCS.md) | актуален | 2026-11-02 | 2027-05-01 | governance |

## Регулярные проверки

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [Регулярная ревизия документации](../governance/recurring/docs-review.md) | актуален | 2026-11-04 | 2027-05-03 | governance |

## Шаблоны

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [Шаблон артефакта (ресёрч, аудит, отчёт)](../governance/templates/ARTIFACT.md) | актуален | 2026-11-02 | 2027-11-02 | governance |
| [Заявка на решение (REQUEST)](../governance/templates/REQUEST.md) | актуален | 2026-10-03 | 2027-10-03 | governance |
| [Отчёт по задаче (TASK-REPORT)](../governance/templates/TASK-REPORT.md) | актуален | 2026-10-03 | 2027-10-03 | governance |

## Инструкции

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [Артефакты публичного контура — как заводить](../artifacts/README.md) | актуален | 2026-11-04 | 2027-05-03 | governance |
| [Локальный стенд local-poc](../local-poc/README.md) | актуален | 2026-10-03 | 2027-04-01 | tech |

## Юридическое

| Документ | Статус | Обновлён | Ревизия до | Владелец |
|---|---|---|---|---|
| [Лицензия](../LICENSE.md) | актуален | 2026-10-03 | 2028-10-02 | governance |

## Артефакты: ресёрч, аудит, выводы

Актуальных артефактов нет.

## Устарело и заменено

| Документ | Статус | Замена |
|---|---|---|
| [Презентация продукта](../docs/00-product-presentation.md) | устарел | https://axiiom.ru/fonotext/00-product-presentation/ |
| [Интеграция и анкета подключения](../docs/01-integration.md) | устарел | https://axiiom.ru/fonotext/01-integration/ |
| [Архитектура системы](../docs/02-architecture.md) | устарел | https://axiiom.ru/fonotext/02-architecture/ |
| [Модели распознавания и методика оценки](../docs/03-models.md) | устарел | https://axiiom.ru/fonotext/03-models/ |
| [Мощности и пропускная способность](../docs/04-hardware.md) | устарел | https://axiiom.ru/fonotext/04-hardware/ |
| [План пилота](../docs/05-poc-plan.md) | устарел | https://axiiom.ru/fonotext/05-poc-plan/ |
| [Прайс (снят с публикации)](../docs/06-pricing.html) | снят с публикации | https://axiiom.ru/fonotext/ |
| [Поставка и развёртывание](../docs/07-deployment.md) | устарел | https://axiiom.ru/fonotext/07-deployment/ |
| [Спецификация API v1](../docs/08-api.md) | устарел | https://axiiom.ru/fonotext/08-api/ |
| [Сравнение с рынком (снято с публикации)](../docs/09-competitive-landscape.html) | снят с публикации | https://axiiom.ru/fonotext/ |
| [Аудит 100 % звонков без повторного ASR](../docs/10-feature-specs/01-full-coverage.md) | устарел | https://axiiom.ru/fonotext/specs/01-full-coverage/ |
| [Конструктор таксономии и правил](../docs/10-feature-specs/02-taxonomy-builder.md) | устарел | https://axiiom.ru/fonotext/specs/02-taxonomy-builder/ |
| [Контроль скриптов с доказательствами](../docs/10-feature-specs/03-script-evidence.md) | устарел | https://axiiom.ru/fonotext/specs/03-script-evidence/ |
| [Архив под ключ](../docs/10-feature-specs/04-archive.md) | устарел | https://axiiom.ru/fonotext/specs/04-archive/ |
| [Приватный контур на аренде](../docs/10-feature-specs/05-private-shard.md) | устарел | https://axiiom.ru/fonotext/specs/05-private-shard/ |
| [LLM-аналитик по разговорам](../docs/10-feature-specs/06-ask-your-calls.md) | устарел | https://axiiom.ru/fonotext/specs/06-ask-your-calls/ |
| [Мониторинг качества и дрейфа моделей](../docs/10-feature-specs/07-quality-drift.md) | устарел | https://axiiom.ru/fonotext/specs/07-quality-drift/ |
| [Алерты и автодействия](../docs/10-feature-specs/08-alerts-actions.md) | устарел | https://axiiom.ru/fonotext/specs/08-alerts-actions/ |
| [Интеграции: CRM, АТС, мессенджеры](../docs/10-feature-specs/09-integrations.md) | устарел | https://axiiom.ru/fonotext/specs/09-integrations/ |
| [Конструктор дашбордов](../docs/10-feature-specs/10-dashboards.md) | устарел | https://axiiom.ru/fonotext/specs/10-dashboards/ |
| [QA-модуль и чек-листы](../docs/10-feature-specs/11-qa-checklists.md) | устарел | https://axiiom.ru/fonotext/specs/11-qa-checklists/ |
| [Fonotext Copilot](../docs/10-feature-specs/12-copilot.md) | устарел | https://axiiom.ru/fonotext/specs/12-copilot/ |
| [Спецификации функций — обзор](../docs/10-feature-specs/README.md) | устарел | https://axiiom.ru/fonotext/ |
| [Как устроена цена (снято с публикации)](../docs/12-kak-ustroena-nasha-cena.html) | снят с публикации | https://axiiom.ru/fonotext/ |
| [Безопасность и 152-ФЗ](../docs/13-bezopasnost-i-152-fz.md) | устарел | https://axiiom.ru/fonotext/13-bezopasnost-i-152-fz/ |
| [Релиз v1.1 — что нового](../docs/14-chto-novogo-v1-1.md) | устарел | https://axiiom.ru/fonotext/14-chto-novogo-v1-1/ |
| [Каталог документации](../docs/dokumentaciya/index.html) | устарел | https://axiiom.ru/fonotext/ |
| [Что такое речевая аналитика](../docs/rechevaya-analitika/index.html) | устарел | https://axiiom.ru/fonotext/ |
| [Мы и рынок 2026 (снято с публикации)](../docs/we-vs-market-2026.html) | снят с публикации | https://axiiom.ru/fonotext/ |

---

Индекс пересобирается командой `python3 tools/docs-registry.py --index`; CI проверяет, что он не разъехался с реестром (`--check-index`).
