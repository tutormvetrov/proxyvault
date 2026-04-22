# Parallel workstreams для GPT-5.4 (max effort)

## Назначение

Этот документ режет реализацию на параллельные потоки так, чтобы несколько агентов могли работать независимо и с минимальным количеством конфликтов.

Перед стартом любого потока агент обязан прочитать:

1. `docs/client-mode-ru-rollout/00-master-spec.md`
2. свой собственный prompt-файл

## Общие правила для всех потоков

- не откатывать чужие изменения
- не переименовывать существующие модули без сильной причины
- не менять продуктовый scope из мастер-спеки
- не оставлять новые пользовательские строки вне i18n-слоя
- писать код и тексты так, чтобы интегратор мог объединить ветки без архитектурных сюрпризов
- если поток зависит от ещё не смёрженного кода, нужно создавать тонкий адаптационный слой, а не ломать контракт

## Поток A. Runtime core и persistence

Цель:

- создать ядро `app/runtime/`
- зафиксировать enums/models/contracts
- расширить `AppSettings`
- добавить таблицы `entry_runtime_prefs` и `session_history`
- реализовать `RuntimeManager` и persistence API

Основные зоны владения:

- `app/runtime/*`
- `app/models.py`
- `app/db.py`

Не владеть:

- `app/ui/*`
- `README.md`
- build scripts, кроме редких точечных правок по путям runtime

Зависимости:

- работает первым и создаёт контракты для остальных потоков

## Поток B. Proxy runtime через sing-box и system proxy

Цель:

- реализовать `SingBoxAdapter`
- генерацию runtime-конфигов
- управление локальными портами
- системный proxy для proxy-сессий
- обработку падения primary
- bundle/runtime paths для `sing-box`

Основные зоны владения:

- `app/runtime/adapters/sing_box.py`
- `app/runtime/ports.py`
- `app/runtime/logs.py`
- `app/runtime/health.py`
- `app/runtime/routing/*`
- `app/runtime/paths.py`
- build/spec scripts, связанные с упаковкой bundled `sing-box`

Не владеть:

- `app/ui/*`
- `README.md`, кроме узких справочных правок о путях runtime

Зависимости:

- использует контракты потока A

## Поток C. WireGuard adapters и privileged flows

Цель:

- реализовать Windows/macOS WireGuard-подключение отдельным путём
- встроить WG в общую runtime-модель
- обеспечить корректное route ownership и UX-предупреждения

Основные зоны владения:

- `app/runtime/adapters/wireguard_windows.py`
- `app/runtime/adapters/wireguard_macos.py`
- дополнительные helper-модули внутри `app/runtime/`
- platform-specific runtime assets, связанные с WireGuard

Не владеть:

- `app/ui/*`, кроме минимально необходимого контракта предупреждений, если интегратор так решит
- `README.md`

Зависимости:

- использует контракты потока A
- взаимодействует с routing-контрактами потока B

## Поток D. i18n-платформа и словари

Цель:

- создать `app/i18n/`
- зафиксировать `Translator` / `LocalizationService`
- определить supported locales
- создать полные каталоги ключей для `ru` и `en`

Основные зоны владения:

- `app/i18n/*`
- при необходимости отдельные каталоги локализованного help-content

Не владеть:

- крупные правки `app/ui/*`
- runtime-слой

Зависимости:

- может стартовать параллельно с потоком A
- UI-поток потом интегрирует эти словари в виджеты

## Поток E. UI runtime surfaces и локализованный UX

Цель:

- встроить runtime-статус в карточки, detail panel, toolbar, меню, settings
- перевести UI на `tr(...)`
- добавить help window shell, runtime actions, human summaries и session/history views

Основные зоны владения:

- `app/ui/main_window.py`
- `app/ui/detail_panel.py`
- `app/ui/card_view.py`
- `app/ui/sidebar.py`
- `app/ui/dialogs.py`
- `app/ui/settings.py`
- `app/ui/theme.py`, если потребуются небольшие правки для новых блоков
- `main.py` для инициализации manager/i18n/shutdown hooks

Не владеть:

- `app/runtime/adapters/*`
- `README.md`

Зависимости:

- требует контрактов потока A
- использует словари потока D
- интегрируется с адаптерами потоков B и C через `RuntimeManager`

## Поток F. README, welcome/help content и продуктовый copywriting

Цель:

- переписать README на понятный русский
- подготовить встроенную справку для `ru` и `en`
- подготовить тексты welcome/quick start, tooltips, human error dictionary

Основные зоны владения:

- `README.md`
- `README.en.md`, если создаётся
- `app/help/*`
- отдельные markdown/content resources

Не владеть:

- runtime-слой
- системную логику UI, кроме мест, где help content подгружается из файлов/ресурсов

Зависимости:

- может стартовать параллельно
- UI-поток подхватывает эти материалы в окно справки и welcome flow

## Поток G. Тесты, QA и acceptance

Цель:

- расширить unit/integration tests
- добавить проверки локализации
- зафиксировать ручной acceptance checklist
- прогнать связность после слияния потоков

Основные зоны владения:

- `tests/runtime/*`
- `tests/i18n/*`
- `tests/ui/*`
- при необходимости существующие `tests/test_*.py`
- `docs/client-mode-ru-rollout/*acceptance*` или аналогичные QA-артефакты

Не владеть:

- продуктовый UI copy
- engine adapters, кроме мелких тест-хуков

Зависимости:

- может начать со scaffolding и fixtures сразу после стабилизации контрактов из потока A
- финальный прогон делает после интеграции всех остальных потоков

## Рекомендуемый порядок выполнения

1. Поток A создаёт контракты и persistence.
2. Потоки D и F идут параллельно почти сразу.
3. Потоки B и C реализуют реальные движки поверх контрактов A.
4. Поток E интегрирует runtime и i18n в UI.
5. Поток G делает финальную тестовую стыковку и acceptance.

## Границы конфликтов по файлам

Минимизировать одновременные правки здесь:

- `app/models.py`
- `app/db.py`
- `main.py`
- `app/ui/main_window.py`
- `app/ui/dialogs.py`
- `app/ui/settings.py`
- build scripts

Если конфликт неизбежен, объединять через интегратора, а не через неявные параллельные переписывания.

## Интеграционные checkpoints

### Checkpoint 1

После потока A должны существовать:

- runtime enums/models/contracts
- DB migration layer
- расширенный `AppSettings`
- базовый `RuntimeManager`, который пока может работать даже с фейковыми адаптерами

### Checkpoint 2

После потоков B и C:

- реальные адаптеры запускаются отдельно от UI
- есть нормализованные состояния, логи и route ownership
- system proxy logic работает по контракту

### Checkpoint 3

После потоков D, E, F:

- UI переведён на i18n
- новые runtime-поверхности видны пользователю
- welcome/help/README согласованы по смыслу

### Checkpoint 4

После потока G:

- тесты проходят
- acceptance checklist закрыт
- релизные артефакты и документация согласованы

## Формат отчёта каждого потока

Каждый агент в финальном ответе должен сообщать:

- что именно реализовано
- какие файлы добавлены/изменены
- какие тесты добавлены/обновлены
- что осталось на интеграцию
- какие допущения были приняты
- какие риски остались
