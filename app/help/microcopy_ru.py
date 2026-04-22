"""Russian onboarding and tooltip microcopy."""

MICROCOPY_RU: dict[str, str] = {
    "onboarding.welcome.title": "Добро пожаловать в ProxyVault",
    "onboarding.welcome.body": (
        "Храните свои подключения локально, запускайте нужный профиль и проверяйте его состояние "
        "в одной правой панели без лишней путаницы."
    ),
    "onboarding.welcome.primary_cta": "Добавить первое подключение",
    "onboarding.welcome.secondary_cta": "Позже",
    "onboarding.quick_start.title": "С чего начать",
    "onboarding.quick_start.body": (
        "Добавьте подключение, выберите его в списке, нажмите `Подключить`, а при необходимости "
        "сделайте его основным."
    ),
    "action.connect.tooltip": "Запустить выбранный профиль и показать его живое состояние.",
    "action.disconnect.tooltip": "Остановить выбранное подключение и снять основной маршрут, если он был активен.",
    "action.make_primary.tooltip": "Сделать это активное подключение основным системным proxy-маршрутом.",
    "settings.language.tooltip": "Переключить язык интерфейса между русским и английским.",
    "reachability.tooltip": (
        "TCP-проверка показывает, отвечает ли сервер по сети. Это отдельная диагностика, а не статус запуска."
    ),
    "runtime.human_summary.tooltip": "Короткое человеческое объяснение текущего состояния или ошибки.",
    "runtime.technical_log.tooltip": "Технический журнал для подробной диагностики, если короткого объяснения недостаточно.",
    "runtime.status.hint": "Сначала смотрите на статус подключения, затем на TCP-проверку и журнал.",
}
