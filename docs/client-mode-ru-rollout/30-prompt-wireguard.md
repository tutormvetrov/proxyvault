# Prompt C. WireGuard для Windows и macOS

## Для кого

Этот prompt предназначен для отдельного агента GPT-5.4 с максимальным effort. Агент отвечает за отдельный WireGuard-путь, который не притворяется обычным proxy-движком.

## Обязательный контекст перед стартом

Прочитай:

1. `docs/client-mode-ru-rollout/00-master-spec.md`
2. `docs/client-mode-ru-rollout/01-parallel-workstreams.md`
3. runtime-контракты из потока A
4. routing-контракты из потока B

## Твоя зона владения

Можно свободно менять:

- `app/runtime/adapters/wireguard_windows.py`
- `app/runtime/adapters/wireguard_macos.py`
- связанные helper-модули в `app/runtime/`
- platform-specific runtime asset helpers

Можно точечно менять:

- `app/runtime/manager.py`
- `app/runtime/models.py`

Не трогай без крайней необходимости:

- `app/ui/*`
- `README.md`
- `app/runtime/adapters/sing_box.py`

## Главная цель

Сделать отдельный системный путь подключения WireGuard, который:

- использует общую runtime-модель и history
- захватывает route ownership как `WIREGUARD`
- при старте очищает ProxyVault-managed system proxy
- при отключении ничего автоматически не восстанавливает
- корректно сообщает о system prompts/elevation flows

## Жёсткие требования

- WireGuard не должен маскироваться под proxy-сессию `sing-box`
- в runtime/history он должен выглядеть отдельным engine kind
- после старта WireGuard старый primary proxy не восстанавливается автоматически
- disconnect должен быть корректным и явным
- ошибки привилегий и системных prompt-ов должны нормализоваться в человеческие причины

## Что именно нужно реализовать

### 1. `WireGuardAdapterWindows`

Ожидаемое поведение:

- подключение отдельным Windows-specific path
- допускается elevation
- session/status/history интегрированы с `RuntimeManager`
- если для управления нужен helper executable или вызов системного CLI, это должно быть абстрагировано и тестируемо

Сильное требование:

- не зашивать логику в UI
- не держать неявный глобальный state

### 2. `WireGuardAdapterMacOS`

Ожидаемое поведение:

- отдельный macOS-specific helper path
- допускаются system prompts/elevation
- unsigned build допустим, но ошибки/предупреждения должны быть нормализованы

Нужно предусмотреть:

- понятную реакцию на отсутствие разрешений
- понятную реакцию на недоступность helper/runtime asset
- structured warnings, которые потом можно показать в UI

### 3. Route ownership

Убедись, что WireGuard-flow соблюдает контракт:

- при connect очищается ProxyVault-managed system proxy
- route owner становится `WIREGUARD`
- при disconnect route owner возвращается в `NONE`, если ничего другого явно не выбрано
- никакой старый proxy не включается автоматически

### 4. Lifecycle и history

Для WireGuard тоже должны писаться:

- `started_at`
- `stopped_at`
- `engine kind`
- `state`
- `route_owner_kind`
- `exit_code`, если уместно
- `failure_reason`
- `short_log_excerpt`

### 5. Diagnostic normalization

Создай нормализованные причины для типовых WireGuard-проблем:

- отсутствуют привилегии
- helper/runtime asset не найден
- системный prompt отклонён
- конфигурация невалидна
- handshake не установлен
- туннель завершился сразу после старта

Можно ввести внутренние error codes или classification helpers, если это упростит UI и тесты.

## Что не нужно делать здесь

- UI-окна и кнопки
- полную локализацию текста интерфейса
- `sing-box` runtime

## Тесты, которые нужно добавить

Минимум:

- Windows adapter создаёт корректный launch/connect flow через mocked runner
- macOS adapter создаёт корректный launch/connect flow через mocked runner
- при connect очищается proxy route ownership
- disconnect не восстанавливает старый proxy
- ошибки elevation/permission нормализуются
- history record сохраняет WireGuard-specific engine/state

Если реальные системные вызовы трудно тестировать, сделай command-runner abstraction и мокай её.

## Acceptance criteria

Работа считается готовой, если:

- существуют отдельные Windows и macOS WireGuard adapters
- они встраиваются в общий runtime manager
- route ownership для WireGuard соблюдает мастер-спеку
- ошибки и статус нормализуются для UI
- тесты покрывают connect/disconnect и failure flows

## Формат финального ответа агента

В конце сообщи:

1. Как устроен Windows path
2. Как устроен macOS path
3. Какие helper abstractions созданы
4. Какие failure modes покрыты
5. Что нужно от UI-потока для красивого показа предупреждений
