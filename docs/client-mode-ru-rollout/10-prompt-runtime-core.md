# Prompt A. Runtime core, модели и persistence

## Для кого

Этот prompt предназначен для отдельного агента GPT-5.4 с максимальным effort. Агент работает как senior Python/PyQt engineer и реализует базовый runtime-контур, на который потом опираются остальные потоки.

## Обязательный контекст перед стартом

Прочитай:

1. `docs/client-mode-ru-rollout/00-master-spec.md`
2. `docs/client-mode-ru-rollout/01-parallel-workstreams.md`

Исходная база кода:

- текущие доменные модели лежат в `app/models.py`
- SQLite и миграции лежат в `app/db.py`
- UI живёт в `app/ui/*`
- runtime-слоя пока нет
- приложение стартует из `main.py`

## Твоя зона владения

Можно свободно менять:

- `app/runtime/*`
- `app/models.py`
- `app/db.py`

Можно точечно менять, только если действительно нужно:

- `app/paths.py`
- `main.py`

Не трогай без крайней необходимости:

- `app/ui/*`
- `README.md`
- build scripts

## Цель потока

Создать новый runtime foundation layer, который:

- отделяет библиотечные записи от состояния реальных клиентских сессий
- расширяет `AppSettings`
- добавляет runtime persistence в SQLite
- вводит `RuntimeManager` и стабильные контракты адаптеров
- не зависит от конкретной UI-реализации
- покрывается unit-тестами

## Жёсткие требования

- не смешивать runtime state с `ProxyEntry`
- не добавлять пользовательские hardcoded English-строки в новые публичные API
- сохранить обратную совместимость существующей БД через идемпотентные миграции
- не встраивать в `RuntimeManager` реализацию конкретного движка; только orchestration
- все новые сущности должны быть тестируемыми без реального `sing-box` и без реального WireGuard
- код должен быть понятным и модульным, а не одним гигантским классом

## Что именно нужно реализовать

### 1. Новый пакет `app/runtime/`

Создай базовый runtime package с читаемым разбиением. Минимум ожидаются:

- enums
- dataclass-модели
- manager
- contracts/protocols для adapters
- опционально helpers для time/log/snapshot normalization

Если решишь иначе назвать файлы, структура должна остаться прозрачной.

### 2. Новые enums и dataclasses

Реализуй из мастер-спеки:

- `RuntimeState`
- `RuntimeEngineKind`
- `RouteOwnerKind`
- `SystemProxyState`
- `SessionStopReason`
- `RuntimePrefs`
- `LaunchSpec`
- `RunningSession`
- `RuntimeSnapshot`
- `SessionHistoryRecord`

Требования к моделям:

- использовать dataclass/slotted dataclass, где это уместно
- иметь безопасные default values
- иметь `to_dict()` / `from_dict()` там, где это нужно для persistence/tests
- иметь компактные helper-свойства для UI, но без UI-зависимостей

### 3. Расширение `AppSettings`

Обнови `AppSettings.default()`, `to_dict()`, `from_dict()` и всё, что связано с нормализацией настроек в `DatabaseManager`.

Добавить поля:

- `client_mode_enabled`
- `restore_sessions_on_launch`
- `clear_system_proxy_on_exit`
- `minimize_to_tray`
- `auto_reconnect_enabled`
- `log_retention_lines`
- `engine_root_dir`
- `ui_language`

Дополнительно:

- задать безопасные defaults из мастер-спеки
- не сломать portable-path normalization
- учесть миграцию со старых сохранённых JSON settings

### 4. Миграции SQLite и repository methods

В `DatabaseManager`:

- создать таблицы `entry_runtime_prefs` и `session_history`
- добавить индексы
- добавить методы CRUD/queries для runtime prefs/history
- убедиться, что миграции идемпотентны и не ломают старые БД

Поддержи сценарии:

- у записи может ещё не быть `entry_runtime_prefs` в БД
- удаление `entries` должно каскадно удалять runtime prefs/history
- история читается в обратном хронологическом порядке

### 5. `RuntimeManager`

Реализуй менеджер как платформенно-нейтральный orchestration layer.

Ожидаемые обязанности:

- registry адаптеров
- выбор адаптера по `ProxyEntry.type`
- запуск сессии по `entry_id`
- остановка сессии по `entry_id`
- остановка всех сессий
- выставление primary proxy session
- формирование `RuntimeSnapshot`
- запись `SessionHistoryRecord`
- graceful shutdown hook
- очистка внутреннего state при crash/exit

Важно:

- менеджер не должен сам знать синтаксис `sing-box` или WireGuard-конфигов
- менеджер должен работать с внедрёнными adapter instances
- менеджер должен уметь обслуживать несколько сессий параллельно
- логика “только одна основная proxy-сессия” должна жить здесь, а не в UI
- логика “WireGuard перехватывает route ownership” тоже живёт здесь

### 6. Сигналы и контракт с UI

Так как проект на PyQt6, сделай `RuntimeManager` пригодным для интеграции с UI:

- либо как `QObject` с signal-ами
- либо как чистый сервис + отдельный `QObject` bridge

Предпочтительно:

- `snapshotChanged`
- `sessionUpdated`
- `sessionLogUpdated`
- `operationFailed`

Если выберешь другие имена, они должны быть однозначными и стабильными.

### 7. Session restore / shutdown rules

Реализуй каркас для:

- восстановления сессий на старте, если `restore_sessions_on_launch=True`
- очистки system proxy на shutdown, если `clear_system_proxy_on_exit=True`

Даже если реальные платформенные операции пока делегируются адаптерам/роутеру, orchestration-контракт должен уже существовать.

### 8. Ошибки и unsupported entries

Нужно явно поддержать:

- `OTHER` не запускается
- если у записи нет доступного адаптера, пользователь получает нормализованную ошибку
- history сохраняет `failure_reason`

Не делай молчаливых no-op.

## Рекомендуемая архитектура

Подход, который здесь ожидается:

- лёгкие модели данных
- менеджер координации
- отдельно repository methods в `DatabaseManager`
- адаптеры как внедряемые зависимости
- легко подменяемые fake adapters для тестов

Хорошим решением будет иметь `UnsupportedAdapter` или отдельную ветку `resolve_adapter`, которая возвращает structured error.

## Что не нужно делать в этом потоке

- реальный запуск `sing-box`
- реальный WireGuard connect/disconnect
- переделку UI
- copywriting help/README

## Тесты, которые ты обязан добавить

Минимум:

- загрузка старых настроек без новых полей
- сериализация новых `AppSettings`
- миграция создаёт `entry_runtime_prefs`
- миграция создаёт `session_history`
- сохранение/чтение `RuntimePrefs`
- сохранение/чтение `SessionHistoryRecord`
- `RuntimeManager` стартует сессию через fake adapter
- `RuntimeManager` останавливает сессию
- `RuntimeManager` запрещает вторую primary proxy без корректного switch flow
- `RuntimeManager` корректно даёт WireGuard route ownership при fake adapter
- `OTHER` не стартует и создаёт осмысленную ошибку/history record

Используй `unittest` и временные БД, чтобы остаться в стиле текущего проекта.

## Acceptance criteria

Работа считается завершённой, если:

- появился отдельный runtime package
- новые runtime-сущности не смешаны с `ProxyEntry`
- `AppSettings` расширен и совместим назад
- SQLite schema обновляется автоматически
- есть рабочий `RuntimeManager` с fake/test adapters
- новые тесты проходят локально

## Формат финального ответа агента

В конце отчитайся так:

1. Что реализовано
2. Какие файлы добавлены/изменены
3. Какие тесты добавлены
4. Какие контракты зафиксированы для потоков B/C/E/G
5. Что осталось интегрировать дальше
