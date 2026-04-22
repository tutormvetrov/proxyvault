from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.help.microcopy_en import MICROCOPY_EN
from app.help.microcopy_ru import MICROCOPY_RU
from app.i18n import (
    SupportedLocale,
    describe_human_error,
    format_route_owner,
    format_runtime_state,
    format_ui_error,
    normalize_human_error_code,
    tr,
)
from app.i18n.service import get_service
from app.i18n.translator import Translator
from app.runtime.enums import RuntimeEngineKind, RuntimeState
from app.runtime.models import RunningSession, RuntimeHumanStatus, RuntimeSnapshot


@dataclass(slots=True)
class RuntimePresentation:
    status_label: str
    tone: str
    hint: str
    title: str
    summary: str
    action: str
    route_label: str


EXTRA_UI_CATALOGS: dict[SupportedLocale, dict[str, str]] = {
    SupportedLocale.RU: {
        "action.help_center": "Открыть справку",
        "action.copy_local_http": "Скопировать локальный HTTP-адрес",
        "action.copy_local_socks": "Скопировать локальный SOCKS-адрес",
        "action.connect_selected": "Подключить выбранный",
        "action.disconnect_selected": "Отключить выбранный",
        "action.make_selected_primary": "Сделать выбранный основным",
        "action.refresh_runtime": "Обновить состояние подключения",
        "common.field.engine": "Движок",
        "common.field.primary_session": "Основной профиль",
        "common.field.log_path": "Путь к журналу",
        "common.field.primary_flag": "Основной",
        "common.field.entry": "Профиль",
        "common.field.result": "Результат",
        "common.field.started": "Старт",
        "common.field.stopped": "Остановка",
        "common.field.route_owner": "Владелец маршрута",
        "common.field.local_address": "Локальный адрес",
        "common.field.current_profile": "Текущий профиль",
        "common.field.session_count": "Активные сессии",
        "common.field.history_state": "Статус",
        "common.field.system_proxy_state": "Системный proxy",
        "common.value.yes": "Да",
        "common.value.no": "Нет",
        "common.value.none": "Нет",
        "common.value.none_long": "Пока нет данных",
        "common.value.not_running": "Не запущено",
        "common.value.primary_current": "Этот профиль",
        "common.value.primary_unknown": "Другой активный профиль",
        "common.value.no_log": "Журнал пока не собран.",
        "common.value.no_sessions": "История запусков пока пуста.",
        "common.value.language_saved": "Язык интерфейса обновлён.",
        "ui.error.with_detail": "{summary}\n\nДетали: {detail}",
        "ui.error.auth_failed": "Не удалось выполнить действие с мастер-паролем.",
        "ui.error.unlock_failed": "Не удалось разблокировать хранилище.",
        "ui.error.add_entry_failed": "Не удалось добавить профиль.",
        "ui.error.save_qr_failed": "Не удалось сохранить QR-код.",
        "ui.error.export_failed": "Не удалось завершить экспорт.",
        "ui.error.import_file_failed": "Не удалось прочитать файл для импорта.",
        "ui.error.subscription_failed": "Не удалось загрузить подписку.",
        "dialog.help.title": "Справка ProxyVault",
        "dialog.help.subtitle": "Quick start, статусы подключения и подсказки по client mode собраны в одном окне.",
        "dialog.help.sections": "Разделов: {count}",
        "dialog.help.navigation": "Навигация",
        "dialog.help.current_section": "Сейчас открыто",
        "dialog.logs.title": "Журнал подключения",
        "dialog.sessions.title": "История сеансов",
        "dialog.runtime_unavailable.title": "Подключение недоступно",
        "dialog.runtime_unavailable.body": "Выберите профиль, чтобы увидеть состояние подключения.",
        "dialog.runtime_log.empty": "Для этого профиля пока нет технического журнала.",
        "dialog.runtime_log.path_missing": "Файл журнала пока не создан.",
        "dialog.runtime_log.path_unavailable": "Исходный файл журнала недоступен. Показан сохранённый фрагмент последней проверки или сеанса.",
        "dialog.sessions.empty": "Для этого профиля ещё нет сохранённых сеансов.",
        "dialog.copy_local_address.unavailable": "Локальный адрес появится после запуска подключения.",
        "startup.database_error.title": "Ошибка базы данных ProxyVault",
        "startup.database_error.recovery_prompt": (
            "ProxyVault не смог открыть локальную базу SQLite.\n\n"
            "Можно попробовать сбросить базу сейчас. Перед этим приложение попытается сделать резервную копию.\n\n"
            "Подробности: {details}"
        ),
        "startup.database_error.recovery_failed": (
            "ProxyVault не смог восстановить базу даже после сброса.\n\n"
            "Резервная копия: {backup}\n\n"
            "Подробности: {details}"
        ),
        "dialog.delete_locked.title": "Хранилище заблокировано",
        "dialog.delete_locked.body": "Разблокируйте ProxyVault, прежде чем удалять зашифрованные записи.",
        "dialog.delete.confirm_one": "Удалить этот профиль?",
        "dialog.delete.confirm_many": "Удалить выбранные профили?",
        "dialog.delete.title": "Подтвердите удаление",
        "dialog.export.no_selection": "Нет профилей для экспорта.",
        "dialog.export.select_entry": "Сначала выберите профиль.",
        "dialog.export.no_unlocked": "Нет разблокированных профилей для этого действия.",
        "dialog.runtime.unsupported.title": "Этот профиль пока не поддерживается",
        "dialog.runtime.unsupported.body": (
            "Client Mode пока не умеет запускать этот тип подключения. Профиль можно хранить в библиотеке, "
            "но кнопка «Подключить» для него недоступна."
        ),
        "dialog.runtime.client_mode_disabled.title": "Client Mode выключен",
        "dialog.runtime.client_mode_disabled.body": (
            "Включите режим клиента в настройках, чтобы запускать подключения прямо из ProxyVault."
        ),
        "dialog.runtime.no_current_entry.title": "Профиль не выбран",
        "dialog.runtime.no_current_entry.body": "Выберите профиль в центральной колонке.",
        "runtime.engine.SING_BOX": "sing-box",
        "runtime.engine.WIREGUARD_WINDOWS": "WireGuard (Windows)",
        "runtime.engine.WIREGUARD_MACOS": "WireGuard (macOS)",
        "runtime.engine.AMNEZIAWG_WINDOWS": "AmneziaWG (Windows)",
        "runtime.engine.AMNEZIAWG_MACOS": "AmneziaWG (macOS)",
        "runtime.engine.UNSUPPORTED": "Не поддерживается",
        "runtime.state.wireguard": "WireGuard активно",
        "runtime.state.amneziawg": "AmneziaWG активно",
        "runtime.summary.disconnected": "Подключение сейчас не активно.",
        "runtime.summary.running_local": "Подключение активно и готово к работе через локальные порты.",
        "runtime.summary.primary_proxy": "Этот профиль сейчас используется как основной системный proxy.",
        "runtime.summary.route_owner_wireguard": "Системный маршрут сейчас принадлежит WireGuard.",
        "runtime.summary.route_owner_amneziawg": "Системный маршрут сейчас принадлежит AmneziaWG.",
        "runtime.summary.stopping": "Подключение останавливается.",
        "runtime.error.entry_not_found": "Профиль не найден в локальной базе.",
        "runtime.error.adapter_not_found": "Для этого профиля пока нет готового runtime-адаптера.",
        "runtime.error.unsupported_entry_type": "Этот тип профиля пока нельзя запустить в Client Mode.",
        "runtime.error.launch_prepare_failed": "Не удалось подготовить запуск подключения.",
        "runtime.error.launch_start_failed": "Не удалось запустить локальную сессию.",
        "runtime.error.stop_failed": "Не удалось корректно остановить подключение.",
        "runtime.error.poll_failed": "Не удалось обновить состояние подключения.",
        "runtime.error.system_proxy_apply_failed": "Не удалось применить системный proxy.",
        "runtime.error.primary_requires_running_session": "Сначала подключите профиль, а затем делайте его основным.",
        "runtime.error.engine_crash": "Локальный движок завершился с ошибкой.",
        "runtime.present.unsupported.title": "Профиль пока не подключается",
        "runtime.present.unsupported.summary": (
            "Этот тип записи ещё не поддержан runtime-слоем. Библиотека и QR остаются доступными."
        ),
        "runtime.present.unsupported.action": "Дождитесь интеграции адаптера или используйте профиль вне Client Mode.",
        "runtime.present.disabled.title": "Client Mode выключен",
        "runtime.present.disabled.summary": "Запускать подключения из ProxyVault сейчас нельзя.",
        "runtime.present.disabled.action": "Откройте настройки и включите режим клиента.",
        "runtime.present.disconnected.title": "Подключение не запущено",
        "runtime.present.disconnected.summary": "Профиль хранится в библиотеке, но локальная сессия сейчас не работает.",
        "runtime.present.disconnected.action": "Нажмите «Подключить», когда будете готовы запустить профиль.",
        "runtime.present.no_log": "Технический журнал появится после первого запуска.",
        "runtime.present.copy_http_ready": "HTTP: {address}",
        "runtime.present.copy_socks_ready": "SOCKS: {address}",
        "runtime.route.this_entry": "Этот профиль",
        "runtime.route.other_entry": "Основной сейчас: {name}",
        "runtime.route.proxy_pending": "Основной маршрут пока не назначен",
        "runtime.route.wireguard_active": "Маршрут удерживает WireGuard",
        "runtime.route.amneziawg_active": "Маршрут удерживает AmneziaWG",
        "runtime.route.clear": "Системный proxy очищен",
        "runtime.route.error": "Не удалось обновить системный proxy",
        "settings.section.runtime": "Runtime и Client Mode",
        "settings.client_mode.label": "Включить режим клиента",
        "settings.restore_sessions_on_launch.label": "Восстанавливать подключения при запуске",
        "settings.clear_system_proxy_on_exit.label": "Очищать системный proxy при выходе",
        "settings.minimize_to_tray.label": "Сворачивать в трей",
        "settings.auto_reconnect_enabled.label": "Автопереподключение",
        "settings.log_retention_lines.label": "Сколько строк хранить в журнале",
        "settings.engine_root_dir.label": "Папка движков",
        "settings.client_mode.tooltip": "Разрешает запускать подключения прямо из ProxyVault.",
        "settings.restore_sessions_on_launch.tooltip": (
            "Если включено, ProxyVault попробует вернуть профили с флагом автозапуска."
        ),
        "settings.clear_system_proxy_on_exit.tooltip": (
            "Очищает системный proxy, который был установлен ProxyVault, при закрытии приложения."
        ),
        "settings.minimize_to_tray.tooltip": (
            "Сохраняет предпочтение сворачивать окно вместо полного закрытия, когда этот сценарий доступен."
        ),
        "settings.auto_reconnect_enabled.tooltip": (
            "Разрешает автоматическое переподключение для профилей и сценариев, где оно поддерживается."
        ),
        "settings.log_retention_lines.tooltip": "Сколько последних строк runtime-журнала показывать в интерфейсе.",
        "settings.engine_root_dir.tooltip": "Папка с bundled runtime-компонентами и helper-утилитами.",
        "dialog.welcome.subtitle": "Сначала соберите один рабочий профиль, потом уже расширяйте библиотеку и сценарии запуска.",
        "dialog.welcome.quick_start_steps": "Шагов: {count}",
        "sidebar.filters.title": "Фильтры",
        "sidebar.filters.favorites_only": "Только избранное",
        "sidebar.filters.types": "Типы",
        "sidebar.filters.tags": "Теги",
        "sidebar.filters.clear_tags": "Сбросить теги",
        "sidebar.filters.reset": "Сбросить фильтры",
        "sidebar.filters.no_tags": "Тегов пока нет",
        "sidebar.summary.title": "Срез библиотеки",
        "sidebar.summary.all_entries": "Сейчас видна вся библиотека профилей.",
        "sidebar.summary.filtered": "Фильтры сузили список и помогают держать фокус.",
        "sidebar.summary.favorites": "Показываются только избранные профили.",
        "sidebar.summary.meta": "Типы: {types} из {total} · Теги: {tags}",
        "card.runtime.hint.disconnected": "Локальная сессия не запущена",
        "card.runtime.hint.primary": "Этот профиль сейчас основной",
        "card.runtime.hint.wireguard": "Маршрут удерживает WireGuard",
        "card.runtime.hint.amneziawg": "Маршрут удерживает AmneziaWG",
        "card.runtime.hint.error": "Есть ошибка запуска",
        "card.runtime.hint.running": "Локальные порты готовы",
        "card.meta.port": "Порт {value}",
        "card.meta.host": "Хост {value}",
        "card.meta.transport_unknown": "транспорт не указан",
        "card.meta.expires_soon": "Скоро истекает: {value}",
        "card.meta.expiry": "Срок действия: {value}",
        "detail.runtime.summary.title": "Что происходит",
        "detail.runtime.next_step.title": "Что можно сделать дальше",
        "detail.runtime.log_placeholder": "Технический журнал появится после запуска профиля.",
        "detail.runtime.unsupported_note": "Этот тип записи пока не поддержан runtime-движком.",
        "detail.runtime.local_address.copied": "Локальный адрес скопирован: {address}",
        "detail.runtime.local_address.unavailable": "Сначала запустите профиль, чтобы появился локальный адрес.",
        "detail.runtime.log.opened": "Открываю журнал подключения.",
        "detail.runtime.route.none": "Маршрут не назначен",
        "detail.runtime.system_proxy.clear": "Очищен",
        "detail.runtime.system_proxy.applied": "Применён",
        "detail.runtime.system_proxy.error": "Ошибка",
        "detail.runtime.system_proxy.unknown": "Неизвестно",
        "detail.clear.title": "Выберите профиль",
        "main.runtime.active_sessions": "Подключения: {count}",
        "main.runtime.client_mode_off": "Client Mode выключен",
        "main.runtime.logs_button": "Журнал",
        "main.runtime.sessions_button": "Сеансы",
        "main.runtime.help_button": "Справка",
        "main.hero.eyebrow": "ProxyVault",
        "main.hero.title": "Личная библиотека профилей",
        "main.hero.subtitle": (
            "Собирайте конфиги в одном месте, быстро фильтруйте библиотеку и запускайте поддерживаемые подключения "
            "прямо из клиента."
        ),
        "main.hero.scope.all": "Профилей: {count}",
        "main.hero.scope.filtered": "Показано: {visible} из {total}",
        "main.hero.selection.none": "Ничего не выбрано",
        "main.hero.selection.single": "Выбран 1 профиль",
        "main.hero.selection.multiple": "Выбрано: {count}",
        "main.hero.mode.ready": "Client Mode готов",
        "main.hero.mode.active": "Активно подключений: {count}",
        "main.hero.mode.off": "Client Mode выключен",
        "settings.hero.subtitle": "Проверьте язык интерфейса, тему и ключевые runtime-параметры перед повседневной работой.",
        "settings.hero.client_mode.on": "Client Mode включён",
        "settings.hero.client_mode.off": "Client Mode выключен",
        "main.search.reason.add_import": "добавить или импортировать профили",
        "main.search.reason.import_subscription": "импортировать профили из подписки",
        "main.search.reason.export_booklet": "экспортировать PDF-буклет",
        "main.search.reason.export_clash": "экспортировать Clash YAML",
        "main.search.reason.regenerate_qr": "пересоздать QR-коды",
        "main.search.reason.unlock_vault": "разблокировать хранилище",
        "main.search.reason.import_dropped": "импортировать перетаскиваемые профили",
        "status.reachability.running_single": "Проверяю соединение для «{name}».",
        "status.reachability.running_batch": "Проверяю {index}/{total}: «{name}».",
        "status.subscription.refreshing": "Обновляю {index}/{total}: {url}",
        "toast.delete_undone": "Удалённые профили восстановлены.",
        "toast.entries_deleted": "Удалено профилей: {count}.",
        "toast.exported_entry": "Экспорт готов для «{name}».",
        "toast.qr_saved": "QR-код сохранён: {path}",
        "toast.reachability.batch_finished": "Проверка завершена: всего {total}, успешно {reachable}, с ошибкой {failed}.",
        "toast.reachability.batch_finished_with_skipped": (
            "Проверка завершена: всего {total}, успешно {reachable}, с ошибкой {failed}, пропущено {skipped}."
        ),
        "toast.reachability.batch_running": "Пакетная проверка уже идёт.",
        "toast.reachability.entry_finished": "Проверка «{name}»: {result}",
        "toast.reachability.entry_running": "Для этого профиля проверка уже выполняется.",
        "toast.reachability.failed": "Не удалось выполнить проверку: {error}",
        "toast.reachability.missing_endpoint": "У профиля «{name}» не указан endpoint ({endpoint}).",
        "toast.reachability.network_error_details": (
            "TCP-подключение к {endpoint} для «{name}» завершилось сетевой ошибкой за {duration}: {error}"
        ),
        "toast.reachability.no_filtered": "Нет профилей, подходящих под текущие фильтры.",
        "toast.reachability.reachable_with_latency": "Доступно, задержка {latency}",
        "toast.reachability.refused": "Соединение отклонено",
        "toast.reachability.refused_details": (
            "Удалённый узел {endpoint} отклонил TCP-подключение для «{name}» за {duration}."
        ),
        "toast.reachability.success_details": (
            "TCP-подключение к {endpoint} для «{name}» прошло успешно за {duration}."
        ),
        "toast.reachability.timeout": "Таймаут подключения",
        "toast.reachability.timeout_details": (
            "TCP-подключение к {endpoint} для «{name}» превысило лимит ожидания ({duration})."
        ),
        "toast.reachability.visible_busy": "Сначала дождитесь завершения текущей пакетной проверки.",
    }
    | MICROCOPY_RU,
    SupportedLocale.EN: {
        "action.help_center": "Open Help",
        "action.copy_local_http": "Copy Local HTTP Address",
        "action.copy_local_socks": "Copy Local SOCKS Address",
        "action.connect_selected": "Connect Selected",
        "action.disconnect_selected": "Disconnect Selected",
        "action.make_selected_primary": "Make Selected Primary",
        "action.refresh_runtime": "Refresh Runtime State",
        "common.field.engine": "Engine",
        "common.field.primary_session": "Primary entry",
        "common.field.log_path": "Log path",
        "common.field.primary_flag": "Primary",
        "common.field.entry": "Entry",
        "common.field.result": "Result",
        "common.field.started": "Started",
        "common.field.stopped": "Stopped",
        "common.field.route_owner": "Route owner",
        "common.field.local_address": "Local address",
        "common.field.current_profile": "Current entry",
        "common.field.session_count": "Active sessions",
        "common.field.history_state": "Status",
        "common.field.system_proxy_state": "System proxy",
        "common.value.yes": "Yes",
        "common.value.no": "No",
        "common.value.none": "None",
        "common.value.none_long": "No details yet",
        "common.value.not_running": "Not running",
        "common.value.primary_current": "This entry",
        "common.value.primary_unknown": "Another active entry",
        "common.value.no_log": "No log has been collected yet.",
        "common.value.no_sessions": "No saved runtime sessions yet.",
        "common.value.language_saved": "The interface language has been updated.",
        "ui.error.with_detail": "{summary}\n\nDetails: {detail}",
        "ui.error.auth_failed": "The master password action could not be completed.",
        "ui.error.unlock_failed": "The vault could not be unlocked.",
        "ui.error.add_entry_failed": "The entry could not be added.",
        "ui.error.save_qr_failed": "The QR code could not be saved.",
        "ui.error.export_failed": "The export could not be completed.",
        "ui.error.import_file_failed": "The file could not be read for import.",
        "ui.error.subscription_failed": "The subscription could not be loaded.",
        "dialog.help.title": "ProxyVault Help",
        "dialog.help.subtitle": "Quick start, connection states, and Client Mode guidance are collected in one place.",
        "dialog.help.sections": "Sections: {count}",
        "dialog.help.navigation": "Navigation",
        "dialog.help.current_section": "Currently open",
        "dialog.logs.title": "Connection Log",
        "dialog.sessions.title": "Session History",
        "dialog.runtime_unavailable.title": "Connection Unavailable",
        "dialog.runtime_unavailable.body": "Select an entry to inspect its runtime state.",
        "dialog.runtime_log.empty": "No technical log is available for this entry yet.",
        "dialog.runtime_log.path_missing": "The log file has not been created yet.",
        "dialog.runtime_log.path_unavailable": "The original log file is unavailable. Showing the saved excerpt from the latest check or session.",
        "dialog.sessions.empty": "This entry does not have any saved sessions yet.",
        "dialog.copy_local_address.unavailable": "A local address will appear after the connection starts.",
        "startup.database_error.title": "ProxyVault Database Error",
        "startup.database_error.recovery_prompt": (
            "ProxyVault could not open its local SQLite database.\n\n"
            "You can reset the database now. The app will try to create a backup first.\n\n"
            "Details: {details}"
        ),
        "startup.database_error.recovery_failed": (
            "ProxyVault still could not recover the database after a reset.\n\n"
            "Backup: {backup}\n\n"
            "Details: {details}"
        ),
        "dialog.delete_locked.title": "Vault Locked",
        "dialog.delete_locked.body": "Unlock ProxyVault before deleting encrypted entries.",
        "dialog.delete.confirm_one": "Delete this entry?",
        "dialog.delete.confirm_many": "Delete the selected entries?",
        "dialog.delete.title": "Confirm Delete",
        "dialog.export.no_selection": "No entries are available to export.",
        "dialog.export.select_entry": "Select an entry first.",
        "dialog.export.no_unlocked": "No unlocked entries are available for this action.",
        "dialog.runtime.unsupported.title": "This entry is not supported yet",
        "dialog.runtime.unsupported.body": (
            "Client Mode cannot launch this connection type yet. You can still keep the entry in the library, "
            "but Connect is unavailable for it."
        ),
        "dialog.runtime.client_mode_disabled.title": "Client Mode Is Disabled",
        "dialog.runtime.client_mode_disabled.body": (
            "Enable client mode in Settings to start connections directly from ProxyVault."
        ),
        "dialog.runtime.no_current_entry.title": "No Entry Selected",
        "dialog.runtime.no_current_entry.body": "Choose an entry in the center column first.",
        "runtime.engine.SING_BOX": "sing-box",
        "runtime.engine.WIREGUARD_WINDOWS": "WireGuard (Windows)",
        "runtime.engine.WIREGUARD_MACOS": "WireGuard (macOS)",
        "runtime.engine.AMNEZIAWG_WINDOWS": "AmneziaWG (Windows)",
        "runtime.engine.AMNEZIAWG_MACOS": "AmneziaWG (macOS)",
        "runtime.engine.UNSUPPORTED": "Unsupported",
        "runtime.state.wireguard": "WireGuard Active",
        "runtime.state.amneziawg": "AmneziaWG Active",
        "runtime.summary.disconnected": "The connection is not active right now.",
        "runtime.summary.running_local": "The connection is active and ready through its local ports.",
        "runtime.summary.primary_proxy": "This entry is currently used as the primary system proxy.",
        "runtime.summary.route_owner_wireguard": "The system route currently belongs to WireGuard.",
        "runtime.summary.route_owner_amneziawg": "The system route currently belongs to AmneziaWG.",
        "runtime.summary.stopping": "The connection is stopping.",
        "runtime.error.entry_not_found": "The entry was not found in the local database.",
        "runtime.error.adapter_not_found": "No runtime adapter is available for this entry yet.",
        "runtime.error.unsupported_entry_type": "This entry type cannot be launched in Client Mode yet.",
        "runtime.error.launch_prepare_failed": "Could not prepare the connection launch.",
        "runtime.error.launch_start_failed": "Could not start the local session.",
        "runtime.error.stop_failed": "Could not stop the connection cleanly.",
        "runtime.error.poll_failed": "Could not refresh the connection state.",
        "runtime.error.system_proxy_apply_failed": "Could not apply the system proxy.",
        "runtime.error.primary_requires_running_session": "Connect the entry before making it primary.",
        "runtime.error.engine_crash": "The local engine exited with an error.",
        "runtime.present.unsupported.title": "This entry cannot connect yet",
        "runtime.present.unsupported.summary": (
            "The runtime layer does not support this entry type yet. The library entry and QR assets remain available."
        ),
        "runtime.present.unsupported.action": "Wait for the adapter integration or use the profile outside Client Mode.",
        "runtime.present.disabled.title": "Client Mode Is Disabled",
        "runtime.present.disabled.summary": "Connections cannot be started from ProxyVault right now.",
        "runtime.present.disabled.action": "Open Settings and enable client mode.",
        "runtime.present.disconnected.title": "The connection is not running",
        "runtime.present.disconnected.summary": "The entry is saved in the library, but no live local session is running.",
        "runtime.present.disconnected.action": "Click Connect when you want to start the profile.",
        "runtime.present.no_log": "The technical log will appear after the first launch.",
        "runtime.present.copy_http_ready": "HTTP: {address}",
        "runtime.present.copy_socks_ready": "SOCKS: {address}",
        "runtime.route.this_entry": "This entry",
        "runtime.route.other_entry": "Primary right now: {name}",
        "runtime.route.proxy_pending": "No primary route has been assigned yet",
        "runtime.route.wireguard_active": "WireGuard owns the route",
        "runtime.route.amneziawg_active": "AmneziaWG owns the route",
        "runtime.route.clear": "System proxy cleared",
        "runtime.route.error": "The system proxy could not be updated",
        "settings.section.runtime": "Runtime and Client Mode",
        "settings.client_mode.label": "Enable client mode",
        "settings.restore_sessions_on_launch.label": "Restore connections on launch",
        "settings.clear_system_proxy_on_exit.label": "Clear the system proxy on exit",
        "settings.minimize_to_tray.label": "Minimize to tray",
        "settings.auto_reconnect_enabled.label": "Auto-reconnect",
        "settings.log_retention_lines.label": "Log lines to keep",
        "settings.engine_root_dir.label": "Engine folder",
        "settings.client_mode.tooltip": "Allows ProxyVault to launch connections directly.",
        "settings.restore_sessions_on_launch.tooltip": (
            "If enabled, ProxyVault will try to restore entries marked for auto-launch."
        ),
        "settings.clear_system_proxy_on_exit.tooltip": (
            "Clears the system proxy managed by ProxyVault when the app closes."
        ),
        "settings.minimize_to_tray.tooltip": (
            "Stores the preference to minimize to the tray instead of fully closing when that flow is available."
        ),
        "settings.auto_reconnect_enabled.tooltip": (
            "Allows automatic reconnect for profiles and scenarios that support it."
        ),
        "settings.log_retention_lines.tooltip": "Controls how many runtime log lines stay visible in the UI.",
        "settings.engine_root_dir.tooltip": "Folder with bundled runtime binaries and helper utilities.",
        "dialog.welcome.subtitle": "Start with one working profile first, then expand the library and launch workflows.",
        "dialog.welcome.quick_start_steps": "Steps: {count}",
        "sidebar.filters.title": "Filters",
        "sidebar.filters.favorites_only": "Favorites only",
        "sidebar.filters.types": "Types",
        "sidebar.filters.tags": "Tags",
        "sidebar.filters.clear_tags": "Clear Tags",
        "sidebar.filters.reset": "Reset Filters",
        "sidebar.filters.no_tags": "No tags yet",
        "sidebar.summary.title": "Library Slice",
        "sidebar.summary.all_entries": "The full profile library is visible right now.",
        "sidebar.summary.filtered": "Filters are narrowing the list and keeping the workspace focused.",
        "sidebar.summary.favorites": "Only favorite profiles are shown right now.",
        "sidebar.summary.meta": "Types: {types} of {total} · Tags: {tags}",
        "card.runtime.hint.disconnected": "No live local session",
        "card.runtime.hint.primary": "This entry is currently primary",
        "card.runtime.hint.wireguard": "WireGuard owns the route",
        "card.runtime.hint.amneziawg": "AmneziaWG owns the route",
        "card.runtime.hint.error": "There is a launch error",
        "card.runtime.hint.running": "Local ports are ready",
        "card.meta.port": "Port {value}",
        "card.meta.host": "Host {value}",
        "card.meta.transport_unknown": "transport not specified",
        "card.meta.expires_soon": "Expires soon: {value}",
        "card.meta.expiry": "Expiry: {value}",
        "detail.runtime.summary.title": "What is happening",
        "detail.runtime.next_step.title": "What to do next",
        "detail.runtime.log_placeholder": "The technical log will appear after the entry starts.",
        "detail.runtime.unsupported_note": "This entry type is not supported by the runtime engine yet.",
        "detail.runtime.local_address.copied": "Copied local address: {address}",
        "detail.runtime.local_address.unavailable": "Start the entry first to get a local address.",
        "detail.runtime.log.opened": "Opening the connection log.",
        "detail.runtime.route.none": "No route selected",
        "detail.runtime.system_proxy.clear": "Clear",
        "detail.runtime.system_proxy.applied": "Applied",
        "detail.runtime.system_proxy.error": "Error",
        "detail.runtime.system_proxy.unknown": "Unknown",
        "detail.clear.title": "Choose a Profile",
        "main.runtime.active_sessions": "Connections: {count}",
        "main.runtime.client_mode_off": "Client Mode off",
        "main.runtime.logs_button": "Log",
        "main.runtime.sessions_button": "Sessions",
        "main.runtime.help_button": "Help",
        "main.hero.eyebrow": "ProxyVault",
        "main.hero.title": "Personal Profile Library",
        "main.hero.subtitle": (
            "Keep configs in one place, filter the library quickly, and launch supported connections right from the client."
        ),
        "main.hero.scope.all": "Profiles: {count}",
        "main.hero.scope.filtered": "Showing: {visible} of {total}",
        "main.hero.selection.none": "Nothing selected",
        "main.hero.selection.single": "1 profile selected",
        "main.hero.selection.multiple": "Selected: {count}",
        "main.hero.mode.ready": "Client Mode Ready",
        "main.hero.mode.active": "Active connections: {count}",
        "main.hero.mode.off": "Client Mode Off",
        "settings.hero.subtitle": "Review the interface language, theme, and key runtime preferences before daily use.",
        "settings.hero.client_mode.on": "Client Mode On",
        "settings.hero.client_mode.off": "Client Mode Off",
        "main.search.reason.add_import": "add or import entries",
        "main.search.reason.import_subscription": "import subscription entries",
        "main.search.reason.export_booklet": "export a PDF booklet",
        "main.search.reason.export_clash": "export Clash YAML",
        "main.search.reason.regenerate_qr": "regenerate QR codes",
        "main.search.reason.unlock_vault": "unlock the vault",
        "main.search.reason.import_dropped": "import dropped entries",
        "status.reachability.running_single": "Checking connectivity for \"{name}\".",
        "status.reachability.running_batch": "Checking {index}/{total}: \"{name}\".",
        "status.subscription.refreshing": "Refreshing {index}/{total}: {url}",
        "toast.delete_undone": "The deleted entries were restored.",
        "toast.entries_deleted": "Deleted entries: {count}.",
        "toast.exported_entry": "Export completed for \"{name}\".",
        "toast.qr_saved": "QR code saved to {path}",
        "toast.reachability.batch_finished": (
            "Reachability checks finished: {total} total, {reachable} reachable, {failed} failed."
        ),
        "toast.reachability.batch_finished_with_skipped": (
            "Reachability checks finished: {total} total, {reachable} reachable, {failed} failed, {skipped} skipped."
        ),
        "toast.reachability.batch_running": "A batch reachability check is already running.",
        "toast.reachability.entry_finished": "Reachability for \"{name}\": {result}",
        "toast.reachability.entry_running": "A reachability check is already running for this entry.",
        "toast.reachability.failed": "The reachability check failed: {error}",
        "toast.reachability.missing_endpoint": "The entry \"{name}\" does not have a usable endpoint ({endpoint}).",
        "toast.reachability.network_error_details": (
            "The TCP connection to {endpoint} for \"{name}\" ended with a network error after {duration}: {error}"
        ),
        "toast.reachability.no_filtered": "There are no entries in the current filtered view.",
        "toast.reachability.reachable_with_latency": "Reachable in {latency}",
        "toast.reachability.refused": "Connection refused",
        "toast.reachability.refused_details": (
            "The remote endpoint {endpoint} refused the TCP connection for \"{name}\" after {duration}."
        ),
        "toast.reachability.success_details": (
            "The TCP connection to {endpoint} for \"{name}\" succeeded in {duration}."
        ),
        "toast.reachability.timeout": "Connection timed out",
        "toast.reachability.timeout_details": (
            "The TCP connection to {endpoint} for \"{name}\" exceeded the timeout window ({duration})."
        ),
        "toast.reachability.visible_busy": "Wait for the current batch reachability check to finish first.",
    }
    | MICROCOPY_EN,
}

EXTRA_UI_KEY_REGISTRY = frozenset(EXTRA_UI_CATALOGS[SupportedLocale.RU].keys())


def ensure_ui_translations(translator: Translator | None = None) -> Translator:
    tx = translator or get_service()
    applied_key = "_proxyvault_ui_extra_catalogs_applied"
    if getattr(tx, applied_key, False):
        return tx
    for locale, payload in EXTRA_UI_CATALOGS.items():
        tx.catalog_for(locale).update(payload)
    setattr(tx, applied_key, True)
    return tx


def extra_ui_catalog_parity_report() -> dict[str, set[str]]:
    ru_catalog = EXTRA_UI_CATALOGS[SupportedLocale.RU]
    en_catalog = EXTRA_UI_CATALOGS[SupportedLocale.EN]
    return {
        "missing_in_en": set(ru_catalog.keys()) - set(en_catalog.keys()),
        "missing_in_ru": set(en_catalog.keys()) - set(ru_catalog.keys()),
        "unexpected_in_en": set(en_catalog.keys()) - set(ru_catalog.keys()),
        "unexpected_in_ru": set(ru_catalog.keys()) - set(en_catalog.keys()),
    }


def current_locale() -> SupportedLocale:
    return ensure_ui_translations().locale


def help_markdown_path(kind: str, locale: SupportedLocale | str | None = None) -> Path:
    resolved = SupportedLocale.coerce(locale or current_locale())
    file_name = f"{kind}_{resolved.value}.md"
    return Path(__file__).resolve().parents[1] / "help" / file_name


def load_help_markdown(kind: str, locale: SupportedLocale | str | None = None) -> str:
    path = help_markdown_path(kind, locale)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def runtime_engine_label(engine_kind: RuntimeEngineKind | str | None) -> str:
    if isinstance(engine_kind, RuntimeEngineKind):
        key = engine_kind.value
    else:
        key = str(engine_kind or RuntimeEngineKind.UNSUPPORTED.value)
    return tr(f"runtime.engine.{key}")


def _is_amneziawg_engine(engine_kind: RuntimeEngineKind | str | None) -> bool:
    key = engine_kind.value if isinstance(engine_kind, RuntimeEngineKind) else str(engine_kind or "")
    return key in {
        RuntimeEngineKind.AMNEZIAWG_WINDOWS.value,
        RuntimeEngineKind.AMNEZIAWG_MACOS.value,
    }


def _wire_route_session(snapshot: RuntimeSnapshot | None) -> RunningSession | None:
    if snapshot is None or not snapshot.wireguard_session_id:
        return None
    return next(
        (item for item in snapshot.sessions if item.session_id == snapshot.wireguard_session_id),
        None,
    )


def _wireguard_hint_key(session: RunningSession | None) -> str:
    return "card.runtime.hint.amneziawg" if _is_amneziawg_engine(getattr(session, "engine_kind", None)) else "card.runtime.hint.wireguard"


def _wireguard_route_label(snapshot: RuntimeSnapshot | None, session: RunningSession | None = None) -> str:
    target_session = session or _wire_route_session(snapshot)
    return tr("runtime.route.amneziawg_active" if _is_amneziawg_engine(getattr(target_session, "engine_kind", None)) else "runtime.route.wireguard_active")


def system_proxy_state_label(value: str | None) -> str:
    mapping = {
        "CLEAR": "detail.runtime.system_proxy.clear",
        "APPLIED": "detail.runtime.system_proxy.applied",
        "ERROR": "detail.runtime.system_proxy.error",
    }
    return tr(mapping.get(str(value or "").upper(), "detail.runtime.system_proxy.unknown"))


def tooltip_text(key: str) -> str:
    return tr(key)


def runtime_error_copy(failure_reason: str = "", technical_detail: str = ""):
    return describe_human_error(failure_reason, detail=technical_detail)


def runtime_error_title(failure_reason: str = "", technical_detail: str = "") -> str:
    detail = runtime_error_copy(failure_reason, technical_detail)
    return detail.title


def runtime_error_summary(failure_reason: str = "", technical_detail: str = "") -> str:
    detail = runtime_error_copy(failure_reason, technical_detail)
    return detail.summary


def runtime_error_action(failure_reason: str = "", technical_detail: str = "") -> str:
    detail = runtime_error_copy(failure_reason, technical_detail)
    return detail.action


def runtime_error_display(failure_reason: str = "", technical_detail: str = "") -> str:
    normalized = normalize_human_error_code(failure_reason, detail=technical_detail)
    if normalized == "unknown" and technical_detail.strip():
        return technical_detail.strip()
    return runtime_error_title(failure_reason, technical_detail)


def runtime_technical_detail(failure_reason: str = "", technical_detail: str = "", log_excerpt: str = "") -> str:
    raw = str(log_excerpt or technical_detail or "").strip()
    if raw:
        return raw
    if str(failure_reason or "").startswith("runtime.") or "." in str(failure_reason or ""):
        return runtime_error_summary(failure_reason, technical_detail)
    return str(failure_reason or "").strip()


def ui_error_message(summary_key: str, detail: object = "") -> str:
    return format_ui_error(summary_key, detail=detail)


def present_runtime_state(
    *,
    session: RunningSession | None,
    snapshot: RuntimeSnapshot | None,
    human_status: RuntimeHumanStatus | None,
    failure_reason: str = "",
    client_mode_enabled: bool = True,
    unsupported: bool = False,
) -> RuntimePresentation:
    ensure_ui_translations()
    if not client_mode_enabled:
        return RuntimePresentation(
            status_label=tr("runtime.state.disconnected"),
            tone="muted",
            hint=tr("main.runtime.client_mode_off"),
            title=tr("runtime.present.disabled.title"),
            summary=tr("runtime.present.disabled.summary"),
            action=tr("runtime.present.disabled.action"),
            route_label=tr("runtime.route.none"),
        )

    if unsupported:
        return RuntimePresentation(
            status_label=tr("runtime.state.disconnected"),
            tone="muted",
            hint=tr("card.runtime.hint.disconnected"),
            title=tr("runtime.present.unsupported.title"),
            summary=tr("runtime.present.unsupported.summary"),
            action=tr("runtime.present.unsupported.action"),
            route_label=tr("runtime.route.none"),
        )

    if session is None:
        error_key = failure_reason.strip()
        title = tr("runtime.present.disconnected.title")
        summary = tr("runtime.present.disconnected.summary")
        action = tr("runtime.present.disconnected.action")
        hint = tr("card.runtime.hint.disconnected")
        tone = "muted"
        if error_key:
            error_copy = runtime_error_copy(error_key)
            title = tr("runtime.state.error")
            summary = error_copy.summary
            action = error_copy.action
            hint = tr("card.runtime.hint.error")
            tone = "danger"
        return RuntimePresentation(
            status_label=tr("runtime.state.error") if error_key else tr("runtime.state.disconnected"),
            tone=tone,
            hint=hint,
            title=title,
            summary=summary,
            action=action,
            route_label=tr("runtime.route.none"),
        )

    title = tr(human_status.title_key, **human_status.params) if human_status else format_runtime_state(session.runtime_state.value)
    summary = tr(human_status.summary_key, **human_status.params) if human_status else tr("runtime.summary.disconnected")
    tone = human_status.tone if human_status else "muted"
    hint = {
        "danger": tr("card.runtime.hint.error"),
        "success": tr("card.runtime.hint.primary" if session.is_primary else "card.runtime.hint.running"),
        "info": tr(_wireguard_hint_key(session)),
        "warning": title,
        "muted": tr("card.runtime.hint.disconnected"),
    }.get(tone, title)

    action = tr("runtime.status.hint")
    if session.last_error or failure_reason:
        action = runtime_error_action(failure_reason or session.failure_reason, session.last_error)

    if session.runtime_state == RuntimeState.ERROR:
        error_copy = runtime_error_copy(failure_reason or session.failure_reason, session.last_error)
        tone = "danger"
        title = error_copy.title
        summary = error_copy.summary
    elif session.runtime_state == RuntimeState.STOPPING:
        tone = "warning"
    elif session.is_primary:
        tone = "success"
    elif session.route_owner_kind.value == "WIREGUARD":
        tone = "info"
        hint = tr(_wireguard_hint_key(session))

    route_label = tr("runtime.route.none")
    if snapshot is not None:
        if session.is_primary:
            route_label = tr("runtime.route.this_entry")
        elif snapshot.route_owner_kind.value == "WIREGUARD":
            route_label = _wireguard_route_label(snapshot, session)
        elif snapshot.primary_session_id:
            primary_name = next(
                (item.entry_name for item in snapshot.sessions if item.session_id == snapshot.primary_session_id),
                "",
            )
            route_label = (
                tr("runtime.route.other_entry", name=primary_name)
                if primary_name
                else tr("runtime.route.proxy_pending")
            )

    return RuntimePresentation(
        status_label=title,
        tone=tone,
        hint=hint,
        title=title,
        summary=summary,
        action=action,
        route_label=route_label,
    )


def system_proxy_status_text(snapshot: RuntimeSnapshot | None) -> str:
    if snapshot is None:
        return tr("detail.runtime.system_proxy.unknown")
    return system_proxy_state_label(snapshot.system_proxy_state.value)


def local_address_text(session: RunningSession | None) -> str:
    if session is None:
        return tr("common.value.not_running")
    if session.local_http_url:
        return tr("runtime.present.copy_http_ready", address=session.local_http_url)
    if session.local_socks_url:
        return tr("runtime.present.copy_socks_ready", address=session.local_socks_url)
    return tr("common.value.none_long")


def route_owner_text(session: RunningSession | None, snapshot: RuntimeSnapshot | None) -> str:
    if session is not None and session.is_primary:
        return tr("runtime.route.this_entry")
    if snapshot is None:
        return tr("runtime.route.none")
    if snapshot.route_owner_kind.value == "WIREGUARD":
        return _wireguard_route_label(snapshot, session)
    if snapshot.primary_session_id:
        primary_name = next(
            (item.entry_name for item in snapshot.sessions if item.session_id == snapshot.primary_session_id),
            "",
        )
        if primary_name:
            return tr("runtime.route.other_entry", name=primary_name)
        return tr("runtime.route.proxy_pending")
    return format_route_owner(snapshot.route_owner_kind.value)


def bool_text(value: bool) -> str:
    return tr("common.value.yes") if value else tr("common.value.no")


def runtime_supports_entry_type(type_value: Any) -> bool:
    return str(type_value) != "ProxyType.OTHER" and str(getattr(type_value, "value", type_value)) != "OTHER"
