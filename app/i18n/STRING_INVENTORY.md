# i18n Inventory for UI Integration

This file maps the current hardcoded UI surfaces to the new translation namespaces so the UI workstream can switch to `tr(...)` mechanically.

## File Mapping

- `app/ui/main_window.py`
  Replace menu, toolbar, status bar, export/import, lock, theme, about, and toast strings with `menu.*`, `toolbar.*`, `action.*`, `app.*`, and `toast.*`.
- `app/ui/detail_panel.py`
  Replace section headers, reachability copy, button labels, QR placeholders, and validation messages with `section.*`, `reachability.*`, `action.*`, and `detail.*`.
- `app/ui/dialogs.py`
  Replace add-entry, subscription, password, welcome, and full-screen QR strings with `dialog.*`, `common.field.*`, `section.*`, and `action.*`.
- `app/ui/settings.py`
  Replace settings labels, theme/refresh options, password status, and validation with `settings.*`, `common.field.*`, `section.*`, and `action.*`.
- `main.py`
  Replace fatal database startup prompts with `app.database_error.*`.
- `app/models.py`
  Stop using `TYPE_LABELS`, `ReachabilityCheck.status_label`, `ProxyEntry.reachability_*label`, and `format_relative_time()` for UI copy once the UI flow switches to `app.i18n.formatters`.

## Suggested Mechanical Replacements

- `TYPE_LABELS.get(entry.type, entry.type.value)` -> `format_proxy_type(entry.type, translator=...)`
- `entry.reachability_status_label` -> `build_reachability_copy(entry, translator=...).status_label`
- `entry.reachability_freshness_label` -> `build_reachability_copy(entry, translator=...).freshness_label`
- `entry.reachability_last_checked_label` -> `build_reachability_copy(entry, translator=...).last_checked_label`
- `entry.reachability_card_hint` -> `build_reachability_copy(entry, translator=...).card_hint`
- `entry.reachability_card_label` -> `build_reachability_copy(entry, translator=...).card_label`
- `entry.reachability_detail_summary` -> `build_reachability_copy(entry, translator=...).detail_summary`
- normalized runtime enums/strings -> `format_runtime_state(...)` and `format_route_owner(...)`
- human-readable runtime failures -> `describe_human_error(code, translator=...)`

## Missing-Key Policy

- `Translator.tr(...)` returns `!!missing:key!!` when the key does not exist anywhere.
- If the active locale misses a key but another locale has it, the result stays visible as `!!missing:key!! <fallback text>`.
- Missing format params return `!!format:key:param!!`.
- Tests should treat any `!!missing:` or `!!format:` marker as a failure.
