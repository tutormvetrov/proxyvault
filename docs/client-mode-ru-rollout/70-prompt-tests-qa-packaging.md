# Prompt G. Тесты, QA, acceptance и интеграционная доводка

## Для кого

Этот prompt предназначен для отдельного агента GPT-5.4 с максимальным effort. Агент отвечает за то, чтобы итоговая система была не только написана, но и проверяема, воспроизводима и пригодна к выпуску.

## Обязательный контекст перед стартом

Прочитай:

1. `docs/client-mode-ru-rollout/00-master-spec.md`
2. `docs/client-mode-ru-rollout/01-parallel-workstreams.md`
3. результаты потоков A-F после их появления в кодовой базе

Текущая тестовая база:

- проект использует `unittest`
- уже есть `tests/test_db.py`, `tests/test_parser.py`, `tests/test_paths.py`, `tests/test_qr_gen.py`, `tests/test_reachability.py`, `tests/test_subscription_security.py`

## Твоя зона владения

Можно свободно менять:

- `tests/*`
- новые подпапки `tests/runtime/`, `tests/i18n/`, `tests/ui/`
- acceptance/QA docs внутри `docs/client-mode-ru-rollout/`

Можно точечно менять:

- build scripts только если для проверки/упаковки не хватает тестового hook-а или smoke-step

Не трогай без крайней необходимости:

- продуктовый copy
- UI-модули, кроме мелких testability hooks
- runtime adapters, кроме мелких dependency injection правок ради тестируемости

## Главная цель

Создать полноценный тестовый и acceptance-контур для новой версии:

- runtime correctness
- localization completeness
- UX smoke confidence
- release/readme sanity

## Жёсткие требования

- тесты должны быть детерминированными
- нельзя полагаться на наличие реального `sing-box` или реального WireGuard в CI
- platform-specific вещи тестировать через mocks/fakes/abstractions
- существующие тесты не должны ломаться без причины

## Что именно нужно реализовать

### 1. Runtime unit tests

Добавь тесты на:

- build runtime-конфига для `VLESS Reality`
- build runtime-конфига для `VLESS WS`
- build runtime-конфига для `VLESS XHTTP`
- build runtime-конфига для `Hysteria2`
- build runtime-конфига для `Shadowsocks`
- build runtime-конфига для `Trojan`
- build runtime-конфига для `NaiveProxy`
- запрет запуска `OTHER`
- старт/стоп одиночной сессии
- несколько параллельных proxy-сессий
- смену primary
- crash primary -> clear system proxy
- WireGuard connect/disconnect route ownership
- отсутствие auto-restore старого proxy после WireGuard
- сохранение `session_history`

### 2. Localization tests

Добавь проверки на:

- наличие ключей для `ru` и `en`
- отсутствие missing keys на основных экранах
- корректное переключение языка
- наличие двуязычных критических системных сообщений
- отсутствие hardcoded English в UI вне допустимой raw-log зоны

Если нужно, можно написать helper, который ищет подозрительные строковые литералы в `app/ui/*.py`, но делай это аккуратно, чтобы не ловить false positives на file paths, enum values и технические ключи.

### 3. UI smoke coverage

Нужны хотя бы smoke tests или проверяемые сценарии на:

- main window открывается с новыми действиями
- detail panel показывает runtime block
- settings показывает language/client-mode controls
- unsupported `OTHER` entry не предлагает фиктивное подключение

### 4. README/help consistency checks

Добавь проверки или хотя бы QA checklist на то, что:

- русский README покрывает обязательные разделы
- help content существует в `ru` и `en`
- quick start шаги совпадают по смыслу

### 5. Manual acceptance checklist

Создай отдельный QA-документ, в котором будут проверочные сценарии.

Обязательные блоки:

- Windows manual acceptance
- macOS manual acceptance
- UX/copy review для нетехнического пользователя
- release artifact review

Хороший вариант имени:

- `docs/client-mode-ru-rollout/80-manual-acceptance-checklist.md`

### 6. Release sanity

Если сборка обновилась под bundled engines/helpers, проверь:

- release layout ожидаемый
- README попадает в релиз
- пути к runtime assets не разваливаются в portable mode

Если полная реальная сборка недоступна в текущей среде, зафиксируй это честно и проверь максимум из того, что возможно локально.

## Что не нужно делать здесь

- переписывать продуктовые тексты по своему вкусу
- проектировать UI заново
- переизобретать runtime architecture

## Сигналы качества, которых я ожидаю

- много small deterministic tests вместо пары интеграционных “монстров”
- явные fakes для adapters/process runners/system proxy appliers
- понятные имена тестов
- QA checklist, который реально может пройти человек перед релизом

## Acceptance criteria

Работа считается готовой, если:

- новая функциональность закрыта unit/smoke/QA checks
- localization покрыта тестами на полноту и отсутствие missing keys
- manual acceptance checklist создан
- ограничения среды честно описаны

## Формат финального ответа агента

В конце сообщи:

1. Какие тестовые файлы добавлены или изменены
2. Какие сценарии теперь покрыты автоматически
3. Что осталось только на ручную проверку
4. Какие ограничения среды не дали проверить всё до конца
5. Где лежит manual acceptance checklist
