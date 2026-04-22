"""English onboarding and tooltip microcopy."""

MICROCOPY_EN: dict[str, str] = {
    "onboarding.welcome.title": "Welcome to ProxyVault",
    "onboarding.welcome.body": (
        "Keep your connections local, start the profile you need, and read its status in one clear "
        "right-side panel."
    ),
    "onboarding.welcome.primary_cta": "Add your first connection",
    "onboarding.welcome.secondary_cta": "Maybe later",
    "onboarding.quick_start.title": "How to begin",
    "onboarding.quick_start.body": (
        "Add a connection, select it in the list, click `Connect`, and make it primary if you want "
        "system traffic to use it."
    ),
    "action.connect.tooltip": "Start the selected profile and show its live runtime state.",
    "action.disconnect.tooltip": "Stop the selected connection and clear the primary route if it was active.",
    "action.make_primary.tooltip": "Make this active connection the main system proxy route.",
    "settings.language.tooltip": "Switch the interface language between Russian and English.",
    "reachability.tooltip": (
        "The TCP check shows whether the server responds on the network. It is separate from the launch status."
    ),
    "runtime.human_summary.tooltip": "A short plain-language explanation of the current state or error.",
    "runtime.technical_log.tooltip": "Technical log output for deeper troubleshooting when the short explanation is not enough.",
    "runtime.status.hint": "Read the connection status first, then the TCP check and the log.",
}
