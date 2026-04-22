# Prompt B. `sing-box`, локальные порты и system proxy

## Для кого

Этот prompt предназначен для отдельного агента GPT-5.4 с максимальным effort. Агент отвечает за реальный proxy-runtime для поддерживаемых протоколов и за системный proxy для основной proxy-сессии.

## Обязательный контекст перед стартом

Прочитай:

1. `docs/client-mode-ru-rollout/00-master-spec.md`
2. `docs/client-mode-ru-rollout/01-parallel-workstreams.md`
3. контракты, добавленные потоком A в `app/runtime/*`

Нельзя перепридумывать контракты менеджера и dataclass-моделей, если поток A их уже создал. Нужно аккуратно встроиться в них.

## Твоя зона владения

Можно свободно менять:

- `app/runtime/adapters/sing_box.py`
- `app/runtime/ports.py`
- `app/runtime/logs.py`
- `app/runtime/health.py`
- `app/runtime/paths.py`
- `app/runtime/routing/*`
- build scripts и packaging files, если это нужно для bundled `sing-box`

Можно точечно менять:

- `app/paths.py`
- `app/runtime/manager.py`, если нужны интеграционные hook-методы и это делается бережно

Не трогай без крайней необходимости:

- `app/ui/*`
- `README.md`
- WireGuard-адаптеры

## Главная цель

Реализовать production-ready v1 путь для proxy-сессий:

- `VLESS Reality`
- `VLESS WS`
- `VLESS XHTTP`
- `Hysteria2`
- `Shadowsocks`
- `Trojan`
- `NaiveProxy`

через bundled `sing-box`, с локальными HTTP/SOCKS inbound, журналом, health/status extraction и system proxy routing.

## Жёсткие требования

- `OTHER` не должен запускаться
- у каждой сессии отдельный config file и отдельный log file
- HTTP и SOCKS обязаны подниматься на `127.0.0.1`
- системный proxy ОС всегда привязывается только к HTTP inbound основной proxy-сессии
- при падении primary system proxy очищается сразу
- при смене primary сначала очистить старый proxy, потом применить новый
- логика system proxy не должна вмешиваться в WireGuard flow сильнее, чем требует контракт route ownership

## Что конкретно нужно реализовать

### 1. `SingBoxAdapter`

Адаптер обязан:

- проверять поддержку `ProxyEntry.type`
- строить `LaunchSpec`
- генерировать конфиг `sing-box`
- запускать `sing-box` как subprocess
- отслеживать PID/exit/status
- читать живой log excerpt
- корректно останавливать процесс

Поддержка типов должна быть явной, а не через `try/except всё подряд`.

### 2. Генерация runtime-конфига

Нужен чистый builder, который из `ProxyEntry` создаёт валидный JSON-конфиг `sing-box`.

Для каждого профиля:

- один outbound по выбранному профилю
- локальный HTTP inbound
- локальный SOCKS inbound
- понятный tag naming
- включённый лог в файл

Не давай пользователю редактировать raw config.

### 3. Mapping по протоколам

Поддержи по отдельности:

- `VLESS Reality`
- `VLESS WS`
- `VLESS XHTTP`
- `Hysteria2`
- `Shadowsocks`
- `Trojan`
- `NaiveProxy`

Для каждого типа:

- аккуратно распарсь нужные поля из `entry.uri` и/или `parse_proxy_text(...)`
- не теряй security/transport-детали
- если конфиг формально есть в библиотеке, но недостаточен для реального запуска, верни нормализованную ошибку

Нельзя ограничиться “best effort” JSON без валидации обязательных полей.

### 4. Local port strategy

Сделай отдельный helper для выделения портов.

Правила:

- если в `RuntimePrefs` есть override, попытаться использовать его
- если override занят, дать явную ошибку
- если override нет, выбрать свободный loopback-порт
- HTTP и SOCKS порты не должны совпадать
- алгоритм должен быть тестируемым

### 5. Runtime paths

Нужны стандартизированные пути:

- папка для generated configs
- папка для runtime logs
- папка для bundled engines

Не разбрасывай временные файлы по случайным местам.

### 6. Health / handshake / activity extraction

Из raw log нужно вытащить максимально полезные runtime-сигналы:

- старт успешен или нет
- последнее рукопожатие
- последняя активность
- возможную latency/handshake-метрику, если она доступна
- краткий excerpt последних строк

Если конкретный протокол не даёт явного handshake в логе, это допустимо, но нужно:

- оставить поле пустым
- не выдумывать фальшивые значения

### 7. System proxy routing

Сделай изолированный слой, который умеет:

- применить system proxy на HTTP inbound основной сессии
- очистить system proxy
- переключить primary proxy safely
- вернуть structured result/error

Нужно разделить:

- cross-platform facade
- platform-specific implementations

Если macOS и Windows делаются разными командами/утилитами, заверни это в единый интерфейс.

### 8. Поведение при crash/exit

Обязательно реализуй:

- если `sing-box` primary-сессии завершается аварийно, system proxy очищается
- если primary переводится на другую proxy-сессию, старая системная привязка снимается
- если приложение уходит в shutdown и настройка разрешает очистку, proxy убирается

## Packaging и runtime assets

Обнови релизную упаковку так, чтобы bundled `sing-box` мог быть найден приложением в portable/release layout.

Ожидания:

- чёткий путь поиска движка
- понятная ошибка, если бинарник отсутствует
- build/release структура не ломает текущее приложение

Если в репозитории ещё нет самих бинарников, подготовь:

- directory contract
- код поиска
- build-time checks
- внятное сообщение об отсутствии нужного runtime asset

## Что не нужно делать здесь

- полноценный UI для логов и кнопок
- WireGuard connect/disconnect
- перевод строк интерфейса

## Тесты, которые нужно добавить

Минимум:

- config builder для каждого поддерживаемого proxy-типа
- отказ сборки для `OTHER`
- выбор override ports
- ошибка при занятом override port
- автоподбор свободных портов
- parser/health extraction из representative log lines
- crash primary -> очистка system proxy
- switch primary -> clear then apply order
- запуск subprocess через фейковый process runner
- корректная остановка `sing-box` session

Если platform-specific команды тяжело тестировать напрямую, используй абстракцию runner и мокай subprocess.

## Acceptance criteria

Работа считается готовой, если:

- `SingBoxAdapter` реально готов к запуску сессий
- все поддерживаемые proxy-типы конвертируются в runtime config
- system proxy routing выделен в отдельный слой
- падение primary очищает system proxy
- build/runtime path к bundled `sing-box` определён
- тесты на config builder и routing проходят

## Формат финального ответа агента

В финале сообщи:

1. Какие протоколы реально поддержаны
2. Какие файлы и модули созданы
3. Как устроен path discovery для `sing-box`
4. Какие edge cases покрыты тестами
5. Какие ограничения остались до полной интеграции с UI
