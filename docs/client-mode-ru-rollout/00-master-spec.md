# ProxyVault Client Mode + Полная русификация

## Назначение документа

Этот документ фиксирует целевое состояние продукта и служит главным архитектурным контрактом для параллельной реализации.

Исходная база репозитория на момент подготовки спеки:

- стек: Python 3.11+, PyQt6, SQLite, unittest
- текущее позиционирование: локальный каталог прокси/VPN-конфигов, QR-генерация, reachability-проверки
- текущая структура: `app/models.py`, `app/db.py`, `app/parser.py`, `app/paths.py`, `app/ui/*.py`, `tests/*.py`
- пользовательские строки сейчас в основном захардкожены прямо в PyQt-виджетах
- отдельного runtime-слоя, i18n-слоя, help-центра и системной логики подключения пока нет

Главная цель версии: превратить ProxyVault из каталога QR-кодов в настольный клиент-менеджер подключений с реальными сессиями, системным маршрутом, историей, логами, понятной диагностикой и полной двуязычной локализацией, где русский язык является основным.

## Продуктовый результат

После реализации пользователь должен уметь:

- импортировать или вручную добавить профиль
- выбрать профиль в карточках
- нажать `Подключить`
- увидеть реальное состояние подключения, а не только TCP reachability
- при необходимости сделать подключение основным системным proxy-маршрутом
- увидеть локальные порты, последнее рукопожатие, последнюю активность, краткую человеческую диагностику и технический лог
- быстро отключиться или переключиться на другой профиль
- использовать интерфейс, onboarding, help и README на понятном русском языке
- в любой момент переключить интерфейс на полноценный English locale

## Что не входит в v1

- редактирование сырого runtime-конфига движка пользователем
- машинный перевод строк сырых логов движков
- автоматическое восстановление старого proxy после отключения WireGuard
- подключение профилей типа `OTHER`
- смена общей трёхколоночной архитектуры приложения
- полноценная notarization/signing-полировка для macOS

## Архитектурные принципы

1. `ProxyEntry` остаётся библиотечной сущностью.
2. Runtime-состояние живёт отдельно и не смешивается с полями каталога.
3. Reachability и runtime-статус не подменяют друг друга.
4. Весь UI использует строки только через локализационный слой.
5. Русский текст пишется заново как продуктовый copywriting, а не как буквальный перевод с английского.
6. Любой системный proxy, которым управляет ProxyVault, должен гарантированно очищаться при падении основной proxy-сессии и при выходе приложения, если это разрешено настройкой.
7. WireGuard является отдельным маршрутизирующим путём и не должен притворяться обычным proxy-движком.

## Целевая структура каталогов

Ниже рекомендуемая структура. Допускаются эквивалентные переименования, если они последовательны и не ломают границы ответственности.

```text
app/
  runtime/
    __init__.py
    enums.py
    models.py
    manager.py
    ports.py
    logs.py
    paths.py
    health.py
    adapters/
      __init__.py
      base.py
      sing_box.py
      wireguard_windows.py
      wireguard_macos.py
    routing/
      __init__.py
      system_proxy.py
      windows.py
      macos.py
  i18n/
    __init__.py
    service.py
    translator.py
    locales.py
    keys.py
    catalog_ru.py
    catalog_en.py
  help/
    __init__.py
    content_ru.md
    content_en.md
    glossary_ru.py
    glossary_en.py
tests/
  runtime/
  i18n/
  ui/
docs/
  client-mode-ru-rollout/
```

Если часть модулей логичнее слить, это допустимо, но итог должен остаться читаемым и тестируемым.

## Новые runtime-сущности

Ниже указаны обязательные сущности v1. Они не должны быть спрятаны внутри UI-виджетов.

### Enums

Минимальный набор:

- `RuntimeState`: `DISCONNECTED`, `STARTING`, `RUNNING`, `STOPPING`, `ERROR`
- `RuntimeEngineKind`: `SING_BOX`, `WIREGUARD_WINDOWS`, `WIREGUARD_MACOS`, `UNSUPPORTED`
- `RouteOwnerKind`: `NONE`, `PROXY`, `WIREGUARD`
- `SystemProxyState`: `CLEAR`, `APPLIED`, `ERROR`
- `SessionStopReason`: `USER_REQUEST`, `ENGINE_EXIT`, `ENGINE_CRASH`, `APP_EXIT`, `ROUTE_TAKEN_BY_WIREGUARD`, `PRIMARY_SWITCH`, `UNSUPPORTED`

### `RuntimePrefs`

Привязана к `entry_id`, хранится в БД отдельно.

Обязательные поля:

- `entry_id: str`
- `auto_launch: bool`
- `preferred_primary: bool`
- `http_port_override: int | None`
- `socks_port_override: int | None`
- `last_used_at: str`
- `last_error: str`

### `LaunchSpec`

Описывает уже рассчитанный запуск, а не пользовательское намерение.

Обязательные поля:

- `session_id: str`
- `entry_id: str`
- `engine_kind: RuntimeEngineKind`
- `route_owner_kind: RouteOwnerKind`
- `requested_primary: bool`
- `resolved_primary: bool`
- `http_port: int | None`
- `socks_port: int | None`
- `config_path: str`
- `log_path: str`
- `working_dir: str`
- `display_name: str`
- `created_at: str`

### `RunningSession`

Хранится в памяти и сериализуемо попадает в snapshot/history.

Обязательные поля:

- `session_id: str`
- `entry_id: str`
- `entry_name: str`
- `engine_kind: RuntimeEngineKind`
- `runtime_state: RuntimeState`
- `route_owner_kind: RouteOwnerKind`
- `is_primary: bool`
- `http_port: int | None`
- `socks_port: int | None`
- `pid: int | None`
- `handle: str`
- `started_at: str`
- `stopped_at: str`
- `last_activity_at: str`
- `last_handshake_at: str`
- `latency_ms: int | None`
- `exit_code: int | None`
- `failure_reason: str`
- `last_error: str`
- `log_excerpt: str`

### `RuntimeSnapshot`

Используется UI и тестами как единый снимок состояния.

Обязательные поля:

- `sessions: list[RunningSession]`
- `primary_session_id: str`
- `route_owner_kind: RouteOwnerKind`
- `system_proxy_state: SystemProxyState`
- `system_proxy_entry_id: str`
- `wireguard_session_id: str`
- `updated_at: str`

### `SessionHistoryRecord`

Сохраняется в БД.

Обязательные поля:

- `session_id: str`
- `entry_id: str`
- `entry_name: str`
- `engine_kind: str`
- `state: str`
- `primary_flag: bool`
- `route_owner_kind: str`
- `http_port: int | None`
- `socks_port: int | None`
- `pid_or_handle: str`
- `started_at: str`
- `stopped_at: str`
- `latency_ms: int | None`
- `last_handshake_at: str`
- `last_activity_at: str`
- `exit_code: int | None`
- `failure_reason: str`
- `short_log_excerpt: str`

## Контракт `RuntimeManager`

Это главный координационный слой. Рекомендуемый формат для PyQt6: `QObject` с сигналами, чтобы UI мог получать обновления без знания внутренностей движков.

Обязанные функции менеджера:

- хранить словарь активных сессий по `session_id`
- уметь разрешать `entry_id -> EngineAdapter`
- запускать и останавливать движки
- выбирать и переключать основную proxy-сессию
- снимать системный proxy при сбоях, крашах, выходе приложения и захвате маршрута WireGuard
- собирать короткие живые логи и метаданные активности
- создавать `RuntimeSnapshot`
- сохранять `SessionHistoryRecord`
- поддерживать восстановление ранее активных сессий только если это разрешено `restore_sessions_on_launch`

Минимальные публичные методы:

```python
class RuntimeManager(QObject):
    snapshotChanged = pyqtSignal(object)
    sessionUpdated = pyqtSignal(str, object)
    sessionLogUpdated = pyqtSignal(str, str)
    humanStatusUpdated = pyqtSignal(str, object)
    operationFailed = pyqtSignal(str, str)

    def start_entry(self, entry_id: str, *, make_primary: bool = False) -> None: ...
    def stop_entry(self, entry_id: str) -> None: ...
    def stop_all(self) -> None: ...
    def make_primary(self, entry_id: str) -> None: ...
    def snapshot(self) -> RuntimeSnapshot: ...
    def history_for_entry(self, entry_id: str, limit: int = 50) -> list[SessionHistoryRecord]: ...
    def shutdown(self) -> None: ...
```

Допускаются дополнительные методы, но эти контракты должны быть покрыты тестами.

## Контракт `EngineAdapter`

Нужен единый интерфейс, чтобы UI и `RuntimeManager` не знали деталей конкретного движка.

Обязательный контракт:

```python
class EngineAdapter(Protocol):
    engine_kind: RuntimeEngineKind

    def supports(self, entry: ProxyEntry) -> bool: ...
    def prepare_launch(self, entry: ProxyEntry, prefs: RuntimePrefs, *, make_primary: bool) -> LaunchSpec: ...
    def start(self, launch_spec: LaunchSpec) -> RunningSession: ...
    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession: ...
    def poll(self, session: RunningSession) -> RunningSession: ...
    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str: ...
```

Правила:

- `OTHER` всегда считается `UNSUPPORTED`
- адаптер не должен напрямую обновлять UI
- адаптер не должен хранить долгоживущий глобальный state вне менеджера без крайней необходимости
- ошибки движка должны нормализоваться до короткой строки для истории и отдельного полного текста для технического журнала

## Правила запуска proxy-сессий через `sing-box`

Для `VLESS_REALITY`, `VLESS_WS`, `VLESS_XHTTP`, `HYSTERIA2`, `SHADOWSOCKS`, `TROJAN`, `NAIVE_PROXY` должен использоваться bundled `sing-box`.

Для каждого запуска:

- автоматически создаётся runtime-конфиг из `ProxyEntry`
- создаётся локальный HTTP inbound на `127.0.0.1`
- создаётся локальный SOCKS inbound на `127.0.0.1`
- создаётся ровно один outbound по выбранному профилю
- у сессии должен быть собственный log-файл
- если есть override-порт из `RuntimePrefs`, используется он
- если override-порта нет, выбирается свободный порт с устойчивой стратегией подбора

Пользователь в v1 не редактирует raw config.

## Правила WireGuard

WireGuard не реализуется как proxy-сессия через `sing-box`.

Windows:

- отдельный адаптер `WireGuardAdapterWindows`
- допускается elevation
- история, состояния, ошибки и route owner живут в общей runtime-модели

macOS:

- отдельный адаптер `WireGuardAdapterMacOS`
- допускаются elevation/system prompts
- UX обязан заранее предупреждать о системных запросах и потенциальной проверке неподписанного билда

Общие правила WireGuard:

- при подключении должен очищаться любой системный proxy, которым управляет ProxyVault
- текущий `route_owner_kind` становится `WIREGUARD`
- после отключения WireGuard старый proxy автоматически не восстанавливается

## System proxy: обязательное поведение

### Для обычных proxy-сессий

- в любой момент времени ровно одна proxy-сессия может быть основной
- системный proxy ОС привязывается только к HTTP inbound основной сессии
- при смене основной сессии сначала очищается старая привязка, затем применяется новая
- если основная сессия падает, системный proxy немедленно очищается
- если активна неосновная proxy-сессия, она остаётся рабочей как локальный endpoint, но не влияет на системный интернет

### Для WireGuard

- при старте WireGuard очищается ProxyVault-managed system proxy
- `route_owner_kind` становится `WIREGUARD`
- после stop/disconnect ничего автоматически не восстанавливается

## Изменения модели данных и БД

### `AppSettings`

Нужно расширить `AppSettings` и JSON-сериализацию новыми полями:

- `client_mode_enabled: bool = True`
- `restore_sessions_on_launch: bool = False`
- `clear_system_proxy_on_exit: bool = True`
- `minimize_to_tray: bool = False`
- `auto_reconnect_enabled: bool = False`
- `log_retention_lines: int = 400`
- `engine_root_dir: str = ""`
- `ui_language: str = "ru"`

### Новая таблица `entry_runtime_prefs`

Рекомендуемая схема:

```sql
CREATE TABLE IF NOT EXISTS entry_runtime_prefs (
    entry_id TEXT PRIMARY KEY,
    auto_launch INTEGER NOT NULL DEFAULT 0,
    preferred_primary INTEGER NOT NULL DEFAULT 0,
    http_port_override INTEGER,
    socks_port_override INTEGER,
    last_used_at TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
);
```

### Новая таблица `session_history`

Рекомендуемая схема:

```sql
CREATE TABLE IF NOT EXISTS session_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    entry_name TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL,
    state TEXT NOT NULL,
    primary_flag INTEGER NOT NULL DEFAULT 0,
    route_owner_kind TEXT NOT NULL DEFAULT 'NONE',
    http_port INTEGER,
    socks_port INTEGER,
    pid_or_handle TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    stopped_at TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER,
    last_handshake_at TEXT NOT NULL DEFAULT '',
    last_activity_at TEXT NOT NULL DEFAULT '',
    exit_code INTEGER,
    failure_reason TEXT NOT NULL DEFAULT '',
    short_log_excerpt TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
);
```

Нужны индексы минимум по:

- `session_history(entry_id, started_at DESC)`
- `session_history(session_id)`

### Новые методы `DatabaseManager`

Минимально требуются:

- `load_runtime_prefs(entry_id: str) -> RuntimePrefs`
- `save_runtime_prefs(prefs: RuntimePrefs) -> None`
- `list_runtime_prefs() -> list[RuntimePrefs]`
- `record_session_history(record: SessionHistoryRecord) -> None`
- `list_session_history(entry_id: str, limit: int = 50) -> list[SessionHistoryRecord]`
- `clear_runtime_metadata_for_entry(entry_id: str) -> None`

Миграции должны быть идемпотентными и совместимыми с уже существующей БД.

## Пути и файловая организация runtime

Нужно ввести отдельные runtime-пути, предпочтительно под `resolve_app_dir()`:

- `runtime/generated/` для генерируемых конфигов
- `runtime/logs/` для логов движков
- `engines/` для bundled runtime binaries/helpers

Рекомендуемые helper-функции:

- `default_engine_root_dir()`
- `runtime_generated_dir()`
- `runtime_logs_dir()`
- `ensure_runtime_dirs()`

## UI/UX: обязательные изменения

### Карточки в центральной сетке

Нужно сохранить существующую сетку, но добавить независимый runtime-статус:

- `Не подключено`
- `Запуск…`
- `Подключено`
- `Основное`
- `WireGuard активно`
- `Ошибка`

Reachability остаётся отдельной диагностикой.

### Правая панель

Новый блок `Подключение` добавляется выше блока TCP reachability.

В блоке должны быть:

- движок
- текущее состояние
- текущий основной маршрут
- локальный HTTP-порт
- локальный SOCKS-порт
- время запуска
- последняя активность
- последнее рукопожатие
- последняя ошибка
- короткий живой лог
- человеческое резюме над техническим логом

Кнопки:

- `Подключить`
- `Отключить`
- `Сделать основным`
- `Открыть полный журнал`
- `Скопировать локальный адрес`

### Верхнее меню и toolbar

Нужно добавить действия:

- `Подключить выбранный`
- `Отключить выбранный`
- `Сделать основным`
- `Остановить все подключения`
- `Журналы`
- `Сеансы`

### Settings

Нужно добавить настройки:

- включение client mode
- восстановление сессий при старте
- очистка системного proxy при выходе
- сворачивание в tray
- auto reconnect
- хранение числа строк лога
- путь к движкам
- язык интерфейса

## Локализация

### Базовый контракт

Нужен полноценный `app/i18n/`.

Обязательные сущности:

- `SupportedLocale` enum/registry
- `Translator` или `LocalizationService`
- `tr(key: str, **params) -> str`
- словари `ru` и `en`
- централизованный каталог ключей

### Структура ключей

Ключи должны быть стабильны и иерархичны.

Примеры:

- `menu.file`
- `menu.help`
- `action.connect`
- `action.disconnect`
- `settings.language`
- `runtime.state.running`
- `runtime.summary.handshake_stale`
- `reachability.failed.title`
- `help.quick_start.step_1`

### Жёсткие правила

- никаких новых hardcoded English-строк в виджетах, диалогах и уведомлениях
- английский остаётся полноценным fallback и переключаемым locale
- русский является default locale
- при отсутствии ключа UI не должен молча падать; missing key должен быть явно заметен в тестах

## Логи и человеческие объяснения

Raw-логи внешних движков не переводятся построчно.

Но UI обязан показывать:

- короткий заголовок по-русски
- короткое объяснение по-русски
- возможное действие пользователя
- отдельную область `Технический журнал`

Нужно также иметь мини-словарь типовых ошибок, например:

- порт занят
- процесс завершился сразу после запуска
- сервер не отвечает
- ошибка аутентификации
- системный proxy не удалось применить
- WireGuard требует подтверждения/повышения прав

## Welcome, встроенная справка и README

### Welcome / quick start

Обязательный сценарий:

1. Добавьте своё подключение.
2. Выберите его в списке.
3. Нажмите `Подключить`.
4. Если нужно, нажмите `Сделать основным`.
5. Проверьте состояние в правой панели.

### Встроенная справка

Нужно отдельное окно `Справка` с разделами:

- `С чего начать`
- `Как работает подключение`
- `Что значит “Сделать основным”`
- `Что показывают статусы`
- `Что такое TCP-проверка`
- `Что делать, если соединение не запускается`
- `Как понять, что у меня Mac на Apple Silicon или Intel`

### README

Нужен полный русский `README.md` для обычного пользователя.

Рекомендуемые разделы:

- `Что это`
- `Как запустить`
- `Как добавить подключение`
- `Как подключиться`
- `Если что-то не работает`
- `Какой файл скачать для Mac`

Также рекомендуется сохранить English companion document, если проект поддерживает публичную англоязычную аудиторию.

## Тестовый минимум

### Runtime

Нужны тесты на:

- build runtime-конфига для `VLESS Reality`
- build runtime-конфига для `VLESS WS`
- build runtime-конфига для `VLESS XHTTP`
- build runtime-конфига для `Hysteria2`
- build runtime-конфига для `Shadowsocks`
- build runtime-конфига для `Trojan`
- build runtime-конфига для `NaiveProxy`
- отказ запуска для `OTHER`
- старт/стоп одиночной сессии
- несколько параллельных proxy-сессий
- смену primary
- падение primary и очистку system proxy
- WireGuard connect/disconnect и захват route ownership
- отсутствие автовосстановления старого proxy после WireGuard
- сохранение `session_history`

### Localization

Нужны тесты на:

- отсутствие missing keys для основных экранов
- переключение `Русский / English`
- наличие двуязычных критических системных сообщений
- синхронность welcome/help/README по смыслу
- отсутствие hardcoded English вне raw-log области

### UX / copy

Нужен smoke-review:

- ключевые экраны читаются без технического бэкграунда
- пользователь понимает, как добавить профиль
- пользователь понимает, как подключиться
- пользователь понимает, как отключиться
- пользователь понимает, как проверить, что соединение работает
- пользователь понимает, что делать при типовой ошибке

## Пакетирование и релизы

Текущие build-скрипты уже упаковывают приложение и README. Нужно расширить их так, чтобы релиз содержал:

- bundled `sing-box`
- bundled WireGuard helper/runtime assets
- runtime directories или инициализацию их при первом старте
- обновлённый русский README
- при необходимости companion English docs

`engine_root_dir` по умолчанию должен указывать на bundled engines внутри portable/runtime layout.

## Интеграционные решения по умолчанию

Если в ходе реализации нужна конкретизация, принимать следующие значения:

- язык по умолчанию: `ru`
- `client_mode_enabled` по умолчанию: `True`
- `restore_sessions_on_launch`: `False`
- `clear_system_proxy_on_exit`: `True`
- `minimize_to_tray`: `False`
- `auto_reconnect_enabled`: `False`
- `log_retention_lines`: `400`
- `OTHER` всегда не подключается
- при конфликте primary route выигрывает WireGuard
- после crash основной proxy системный proxy очищается немедленно

## Критерии готовности

Фича считается готовой только если одновременно выполнено всё ниже:

- runtime-слой существует отдельно от UI
- proxy-сессии реально запускаются/останавливаются через `sing-box`
- WireGuard живёт отдельным путём
- системный proxy корректно очищается при сбоях и выходе
- UI показывает runtime-статус, логи, порты и историю
- вся пользовательская оболочка локализована
- русский является default locale
- help/welcome/README переписаны понятным человеческим языком
- тесты на runtime, i18n и базовые UX-ожидания добавлены и проходят
