# 08. Спецификация API v1

Статус: **контракт /v1 стабилен**. Обратная совместимость гарантируется 12 месяцев с момента
релиза. Доступ к API — через пилот и корпоративные поставки.

Базовый URL: `https://api.fonotext.ru`.

API — асинхронный: вы передаёте запись, получаете `call_id`, результат забираете вебхуком или
опросом. SLA готовности результата — ≤ 24 часа (фактически — минуты).

**Что доступно по API:** транскрибация (транскрипт, спикеры, таймкоды, метрики) — сразу;
поля `classification.*` (тип соединения, результат, теги, скрипты, тональность) — в поставке
с аналитикой, в коробке on-prem входят всегда.

## Аутентификация

`Authorization: Bearer <API-ключ>`. Ключи выпускаются в личном кабинете, ротация — без простоя
(два активных ключа). Все запросы — TLS.

## Отправка звонка

```
POST /v1/calls
Content-Type: multipart/form-data

file          — аудиофайл (wav/mp3/opus, до 500 МБ)  [или url=… — ссылка на файл/S3]
external_id   — ваш идентификатор звонка (опционально)
direction     — in | out
operator_id   — идентификатор оператора (опционально)
campaign      — кампания/очередь (опционально)
channel_map   — left=client,right=operator (по умолчанию) | mono
callback_url  — куда прислать результат (опционально)
```

```json
200 OK
{
  "call_id": "c7f3e1a2…",
  "status": "queued",
  "duration_planned_sec": 0,
  "charged_sec": 282
}
```

Учитывается длительность записи: оба канала суммарно один раз, округление до 6 секунд
в большую сторону.

## Статусы и результат

Статусы: `queued → processing → completed | failed` (причины отказа: битый файл, нет речи,
неверный формат — с кодом и описанием).

```
GET /v1/calls/{call_id}
```

```json
200 OK
{
  "call_id": "c7f3e1a2…",
  "status": "completed",
  "audio": {"duration_sec": 282, "channels": "stereo"},
  "classification": {
    "connection_type": "live_talk | answering_machine | spam_block | robot | no_answer | failed",
    "outcome": "sale | appointment | consult | refusal | complaint | callback | other",
    "script_compliance": [
      {"rule": "greeting", "passed": true,  "evidence": "Добрый день, компания…"},
      {"rule": "no_profanity", "passed": true, "evidence": null}
    ],
    "tags": ["интерес", "следующий шаг"],
    "sentiment": "neutral | positive | negative | conflict",
    "confidence": 0.9
  },
  "metrics": {
    "talk_ratio_client": 0.48,
    "interruptions": 3,
    "silence_sec": 21.4
  },
  "transcript": {
    "format": "segments",
    "segments": [
      {"start": 0.0, "end": 3.6, "speaker": "operator",
       "text": "Добрый день! Меня зовут Алексей, компания Стройдом."}
    ]
  },
  "web_url": "https://app.fonotext.ru/calls/c7f3e1a2"
}
```

Набор классов `connection_type`/`outcome` и правила скрипта настраиваются таксономией
заказчика; выдача всегда в стабильном формате.

**Без подписки** блок `classification` возвращается как `null` (транскрипт и метрики — всегда);
явный запрос `GET /v1/calls/{id}?include=classification` без подписки вернёт
`402 payment_required` с приглашением подключить «Аналитику». В период теста классификация
открыта на пробных объёмах.

## Список звонков и выгрузки

```
GET /v1/calls?from=2026-11-01&to=2026-11-30&operator_id=…&connection_type=answering_machine&limit=100&cursor=…
GET /v1/reports/{report_id}/export?format=xlsx     — отчёты по расписанию/по требованию
GET /v1/balance                                    — остаток пакета минут
```

## Вебхуки

Подписка: `POST /v1/webhooks` (`url`, `events`, `secret`). События: `call.completed`,
`call.failed`. Доставка с повторами (экспоненциально, 24 ч), подпись HMAC-SHA256 в заголовке.

```json
{"event": "call.completed", "call_id": "c7f3e1a2…", "external_id": "crm-88113"}
```

## Лимиты и ошибки

- 100 запросов/с на ключ; пиковая загрузка файлов — по договорённости (батч-импорт архива
  отдельным процессом, см. [07-deployment.md](07-deployment.md)).
- Ошибки — JSON: `401` (ключ), `404` (нет звонка), `422` (формат аудио), `429` (лимит),
  `5xx` (повторите с backoff). Идемпотентность: повторный `POST /v1/calls` с тем же
  `external_id` не создаёт дубликат и не тарифицируется повторно.

## SDK и примеры

- `curl -F file=@call.wav -F direction=out -H "Authorization: Bearer $KEY" https://api.fonotext.ru/v1/calls`
- SDK: Python (позже), шаблон интеграции с АТС — по запросу.

Формат результата совпадает с тем, что показывает [демо-панель](demo/index.html)
(out/*.json) — можно разрабатывать интеграцию уже на пилоте.
