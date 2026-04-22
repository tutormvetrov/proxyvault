# Manual Acceptance Checklist for ProxyVault Client Mode

Этот чеклист нужен перед релизом Client Mode и полной русификации. Он покрывает то, что нельзя надёжно закрыть детерминированными unit/smoke-тестами в текущей среде.

## Как использовать

- Проверяйте сценарии на чистой установке и на обновлении поверх существующей библиотеки.
- Отдельно фиксируйте, был ли артефакт собран как clean release без подтягивания локальных данных разработчика.
- Для каждого сценария фиксируйте: `PASS`, `FAIL`, `N/A`, дату, платформу и короткое примечание.
- Если проблема связана с локализацией, приложите скриншот экрана целиком, а не только проблемной строки.
- Если проблема связана с runtime, приложите короткий human summary и хвост технического журнала.

## Preflight

- Убедиться, что в релизном архиве есть `README.md`.
- Убедиться, что в релизном архиве есть `THIRD_PARTY_NOTICES.md` и `LICENSES/README.md`.
- Убедиться, что release собран из `portable-seed` или без локальных данных вообще, а не из неявной пользовательской домашней директории.
- Убедиться, что portable/layout или первый запуск создаёт `runtime/generated`, `runtime/logs` и `engines` либо их эквиваленты.
- Убедиться, что язык по умолчанию после первого запуска — `ru`.
- Убедиться, что встроенная справка открывается без missing-key маркеров.
- Убедиться, что приложение стартует без реального `sing-box` только если пользователь не пытается подключаться.

## Windows Manual Acceptance

### Первичный сценарий proxy

- Добавить профиль `VLESS WS` или `Trojan` из валидного URI.
- Выбрать профиль в библиотеке.
- Нажать `Подключить`.
- Проверить, что статус меняется через `Запуск...` к `Подключено`.
- Проверить, что в правой панели появились локальные HTTP и SOCKS порты.
- Нажать `Сделать основным`.
- Убедиться, что статус и summary явно показывают основной маршрут.
- Проверить в настройках Windows, что системный proxy реально обновился.
- Нажать `Отключить`.
- Убедиться, что системный proxy очищен.

### Падение primary

- Поднять профиль как основной.
- Имитировать аварийное завершение движка или принудительно завершить процесс.
- Убедиться, что UI показывает ошибку, а системный proxy очищается автоматически.
- Проверить, что history/session log содержит запись о завершении.

### Несколько параллельных proxy-сессий

- Запустить два поддерживаемых proxy-профиля подряд.
- Убедиться, что одновременно основным остаётся только один.
- Переключить основной маршрут на второй профиль.
- Проверить, что старая системная привязка снята до применения новой.

### WireGuard

- До запуска открыть release layout и убедиться, что рядом лежат `engines/wireguard/windows/proxyvault-wireguard-windows.exe`, `engines/wireguard/windows/wireguard-bootstrap.json` и `engines/wireguard/windows/wireguard-amd64-0.6.1.msi`.
- Добавить валидный WireGuard-конфиг.
- На чистой Windows-машине не устанавливать WireGuard вручную: первый запуск должен потребовать только системное подтверждение/UAC, а не отдельный поход на сайт и не ручной запуск MSI пользователем.
- Запустить WireGuard после активного primary proxy.
- Если всплыло системное подтверждение, убедиться, что UI не маскирует его и что после одобрения компонент ставится/используется автоматически.
- Убедиться, что системный proxy очищается, а route owner становится WireGuard.
- Остановить WireGuard.
- Проверить, что старый primary proxy автоматически не восстанавливается как системный маршрут.

### AmneziaWG

- До запуска открыть release layout и убедиться, что helper лежит по ожидаемому пути `engines/amneziawg/windows/proxyvault-amneziawg-windows.exe`, а bundled runtime содержит `engines/amneziawg/windows/AmneziaWG/amneziawg.exe`, `engines/amneziawg/windows/AmneziaWG/awg.exe` и `engines/amneziawg/windows/AmneziaWG/wintun.dll`.
- Добавить валидный AmneziaWG-конфиг с obfuscation-параметрами (`Jc`, `Jmin`, `Jmax`, `H1-H4`, `I1` и похожими).
- На чистой Windows-машине не ставить отдельный AmneziaWG-клиент вручную: если bundled runtime не хватает, это считается `FAIL` релизного артефакта, а не пользовательским шагом.
- Запустить AmneziaWG после активного primary proxy.
- Убедиться, что системный proxy очищается, а route owner становится AmneziaWG.
- Остановить AmneziaWG.
- Проверить, что старый primary proxy автоматически не восстанавливается как системный маршрут.
- Если требовалось elevation/подтверждение, убедиться, что UI предупреждал об этом заранее.

## macOS Manual Acceptance

### Базовый запуск

- Запустить `.app` из релизного архива на чистой машине или свежем профиле пользователя.
- Если сборка неподписанная, проверить сценарий `right click -> Open`.
- Убедиться, что приложение стартует и не теряет локальные пути после распаковки.

### Proxy route и clear-on-exit

- Запустить обычный proxy-профиль.
- Сделать его основным.
- Проверить системные сетевые настройки macOS: proxy действительно применён.
- Закрыть приложение обычным способом.
- Убедиться, что ProxyVault-managed proxy очищен, если это разрешено настройкой.

### WireGuard

- До запуска открыть `.app` bundle и убедиться, что helper лежит по ожидаемому пути `ProxyVault.app/Contents/Resources/engines/wireguard/macos/proxyvault-wireguard-macos`.
- На clean macOS без `wg-quick` убедиться, что UI честно показывает отсутствие platform component, а не обещает turnkey-подключение.
- Если `wg-quick` установлен отдельно, запустить WireGuard-профиль и подтвердить системные prompts, если они появляются.
- Убедиться, что после успешного подключения route owner отражает именно WireGuard.
- После отключения проверить, что старый proxy не вернулся автоматически.

### AmneziaWG

- До запуска открыть `.app` bundle и убедиться, что helper лежит по ожидаемому пути `ProxyVault.app/Contents/Resources/engines/amneziawg/macos/proxyvault-amneziawg-macos`.
- На clean macOS без `awg-quick` убедиться, что UI честно показывает отсутствие platform component, а не обещает fully automatic сценарий.
- Если `awg-quick` установлен отдельно, запустить AmneziaWG-профиль и подтвердить системные prompts, если они появляются.
- Убедиться, что после успешного подключения route owner отражает именно AmneziaWG.
- После отключения проверить, что старый proxy не вернулся автоматически.

### Mac architecture UX

- Открыть встроенную справку и README.
- Проверить, что инструкции по Apple Silicon / Intel понятны без технического бэкграунда.
- Сверить названия архивов в релизе с инструкциями документации.

## UX and Copy Review

- Нетехнический пользователь понимает, как добавить первое подключение, не читая исходники и не угадывая.
- Нетехнический пользователь понимает разницу между `Подключить` и `Сделать основным`.
- В правой панели визуально ясно различаются runtime-статус и TCP-проверка.
- При ошибке сначала видно человеческое объяснение, а потом технический журнал.
- В меню, toolbar, диалогах, settings, help и welcome нет случайных hardcoded English-строк, кроме сырых логов движка.
- Missing-key маркеры вроде `!!missing:...!!` нигде не видны в нормальном UX-сценарии.
- Русский текст звучит как продуктовый copy, а не машинный перевод.
- English locale переключается целиком и не ломает вёрстку.

## Help / README Consistency Review

- README, welcome и встроенная справка описывают один и тот же quick start из 5 шагов.
- Везде одинаково объяснено, что TCP-проверка не равна реальному подключению.
- Везде одинаково объяснено, что WireGuard живёт отдельным маршрутом.
- Везде одинаково объяснено, что AmneziaWG живёт отдельным маршрутом и использует отдельный native runtime.
- Везде есть понятное объяснение, что делать при ошибке запуска.

## Release Artifact Review

- В архиве есть основной исполняемый файл приложения.
- В архиве есть `README.md`.
- В архиве есть `THIRD_PARTY_NOTICES.md` и `LICENSES/README.md`.
- В архиве присутствуют bundled engines/helpers или корректный первый запуск создаёт нужную runtime-структуру.
- В Windows-артефакте есть `engines/sing-box/windows/sing-box.exe`, `engines/sing-box/windows/libcronet.dll`, `engines/wireguard/windows/proxyvault-wireguard-windows.exe`, `engines/wireguard/windows/wireguard-bootstrap.json`, `engines/wireguard/windows/wireguard-amd64-0.6.1.msi` и `engines/amneziawg/windows/proxyvault-amneziawg-windows.exe`.
- В macOS-артефакте есть `ProxyVault.app/Contents/Resources/engines/sing-box/macos/sing-box`, `ProxyVault.app/Contents/Resources/engines/wireguard/macos/proxyvault-wireguard-macos` и `ProxyVault.app/Contents/Resources/engines/amneziawg/macos/proxyvault-amneziawg-macos`.
- В Windows-артефакте нет macOS payloads, а в macOS bundle нет Windows-specific payloads вроде `.msi`.
- Portable-маркер и portable seed не ломают запуск на машине без пользовательских данных.
- Контрольные суммы релиза сгенерированы в `SHA256SUMS.txt` и соответствуют архивам.
- Артефакт выглядит как clean release: в нём нет случайно подтянутых пользовательских `proxyvault.db`, локальных логов или runtime state из домашней директории разработчика.
- Имя macOS-архива соответствует одной из ожидаемых схем: `arm64`, `x64`, `universal2`.
- Релиз не содержит лишних временных файлов, тестовых БД, логов разработчика и мусорных артефактов.

## Known Manual-Only Areas

- Реальный запуск `sing-box` и живое рукопожатие с удалённым сервером.
- Проверка системного proxy на Windows и macOS.
- WireGuard bootstrap/UAC на Windows и platform-specific route ownership.
- AmneziaWG native helper flow на Windows и platform-specific route ownership.
- WireGuard и AmneziaWG на macOS по-прежнему зависят от platform tools `wg-quick` / `awg-quick`, пока не появится native bundled runtime-path.
- Поведение неподписанной macOS-сборки при первом открытии.
- Финальная визуальная оценка читаемости UI на маленьких экранах и HiDPI.
