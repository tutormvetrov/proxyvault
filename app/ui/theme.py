from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QAction, QColor, QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QAbstractButton, QWidget

from app.ui.icons import icon


LIGHT_TOKENS: dict[str, str] = {
    "canvas": "#F7F2EA",
    "canvas_glow": "#FCF8F2",
    "panel_base": "#F2EADF",
    "panel_raised": "#FFFCF7",
    "surface": "#FFF8F0",
    "surface_hover": "#FFF3E7",
    "surface_pressed": "#F7EBDD",
    "surface_inset": "#F6EEE3",
    "surface_alt": "#EEE4D7",
    "border_soft": "#DED1C3",
    "border_strong": "#CDB9A6",
    "border_warm": "#E6D6C4",
    "text_primary": "#3B322B",
    "text_secondary": "#695D53",
    "text_muted": "#8D7E71",
    "accent": "#E0A14A",
    "accent_hover": "#D48F34",
    "accent_soft": "#F7E5C6",
    "accent_cool": "#9EC7BE",
    "accent_cool_soft": "#E6F1EE",
    "success": "#769B73",
    "success_soft": "#EAF3E8",
    "warning": "#C79542",
    "warning_soft": "#FAF1DF",
    "destructive": "#BE6B5C",
    "destructive_soft": "#F5E2DE",
    "shadow": "rgba(86, 58, 30, 0.10)",
    "shadow_soft": "rgba(86, 58, 30, 0.06)",
    "focus_ring": "rgba(231, 181, 102, 0.95)",
    "focus_glow": "rgba(224, 161, 74, 0.24)",
    "menu_hover": "rgba(226, 162, 74, 0.12)",
    "selection_soft": "rgba(243, 221, 183, 0.90)",
    "selection_line": "rgba(212, 143, 52, 0.65)",
    "disabled_fill": "#EFE4D7",
    "disabled_text": "#A49588",
    "toolbar_glow": "#FFFDF9",
    "secondary_hover_fill": "#F3DEBC",
    "card_hover_fill": "#FFF6EC",
    "card_selected_fill": "#FFF5E7",
    "qr_well_glow": "#FFF9F2",
    "qr_canvas_fill": "#FFFEFC",
    "reachability_panel_fill": "rgba(255, 252, 247, 0.92)",
    "summary_card_glow": "#FFFAF3",
    "status_muted_fill": "#FBF3E8",
    "table_row_hover": "#FCF4E7",
    "splitter_hover": "rgba(202, 184, 166, 0.35)",
    "warm_border_soft": "rgba(205, 185, 166, 0.75)",
    "warm_border_faint": "rgba(205, 185, 166, 0.55)",
    "accent_border_soft": "rgba(212, 143, 52, 0.30)",
    "accent_border_faint": "rgba(212, 143, 52, 0.24)",
    "accent_border_tint": "rgba(212, 143, 52, 0.26)",
    "warning_border_soft": "rgba(199, 149, 66, 0.42)",
    "destructive_border_soft": "rgba(199, 119, 104, 0.38)",
    "validation_border": "rgba(199, 119, 104, 0.35)",
    "line_soft": "rgba(202, 184, 166, 0.55)",
}


DARK_TOKENS: dict[str, str] = {
    "canvas": "#211C18",
    "canvas_glow": "#28221D",
    "panel_base": "#2A241F",
    "panel_raised": "#342C25",
    "surface": "#3A3029",
    "surface_hover": "#44372F",
    "surface_pressed": "#4C3E35",
    "surface_inset": "#302822",
    "surface_alt": "#3A3028",
    "border_soft": "#5E4E42",
    "border_strong": "#756252",
    "border_warm": "#7D6856",
    "text_primary": "#F4EADF",
    "text_secondary": "#D1C2B2",
    "text_muted": "#A89483",
    "accent": "#E2A24A",
    "accent_hover": "#EAB35C",
    "accent_soft": "#5A4630",
    "accent_cool": "#8FBAB0",
    "accent_cool_soft": "#3A4A46",
    "success": "#8FB98A",
    "success_soft": "#334235",
    "warning": "#D7AE57",
    "warning_soft": "#4A3D27",
    "destructive": "#D48B7E",
    "destructive_soft": "#4E352F",
    "shadow": "rgba(0, 0, 0, 0.34)",
    "shadow_soft": "rgba(0, 0, 0, 0.22)",
    "focus_ring": "rgba(231, 181, 102, 0.95)",
    "focus_glow": "rgba(226, 162, 74, 0.28)",
    "menu_hover": "rgba(226, 162, 74, 0.14)",
    "selection_soft": "rgba(226, 162, 74, 0.24)",
    "selection_line": "rgba(226, 162, 74, 0.72)",
    "disabled_fill": "#43372F",
    "disabled_text": "#8B786A",
    "toolbar_glow": "#3A3029",
    "secondary_hover_fill": "#6A5137",
    "card_hover_fill": "#493C33",
    "card_selected_fill": "#4C3B2B",
    "qr_well_glow": "#40352D",
    "qr_canvas_fill": "#332B25",
    "reachability_panel_fill": "rgba(53, 45, 39, 0.94)",
    "summary_card_glow": "#43372F",
    "status_muted_fill": "#4A3D33",
    "table_row_hover": "#4A3E34",
    "splitter_hover": "rgba(143, 186, 176, 0.18)",
    "warm_border_soft": "rgba(125, 104, 86, 0.72)",
    "warm_border_faint": "rgba(117, 98, 82, 0.55)",
    "accent_border_soft": "rgba(226, 162, 74, 0.38)",
    "accent_border_faint": "rgba(226, 162, 74, 0.28)",
    "accent_border_tint": "rgba(226, 162, 74, 0.30)",
    "warning_border_soft": "rgba(215, 174, 87, 0.42)",
    "destructive_border_soft": "rgba(212, 139, 126, 0.38)",
    "validation_border": "rgba(212, 139, 126, 0.35)",
    "line_soft": "rgba(117, 98, 82, 0.55)",
}


def tokens_for_theme(theme: str) -> dict[str, str]:
    return DARK_TOKENS if theme == "dark" else LIGHT_TOKENS


def build_palette(theme: str) -> QPalette:
    tokens = tokens_for_theme(theme)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens["canvas"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens["text_primary"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["surface_inset"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens["panel_raised"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(tokens["text_primary"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens["text_primary"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(tokens["panel_raised"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens["text_primary"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tokens["panel_raised"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["text_primary"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens["text_muted"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(tokens["accent"]))
    return palette


def build_stylesheet(theme: str) -> str:
    t = tokens_for_theme(theme)
    return f"""
    QWidget {{
        color: {t["text_primary"]};
        font-family: "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", sans-serif;
        font-size: 13px;
        background: transparent;
        selection-background-color: {t["accent_soft"]};
        selection-color: {t["text_primary"]};
    }}

    QMainWindow#mainWindow {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {t["canvas_glow"]},
            stop: 0.22 {t["canvas"]},
            stop: 1 {t["canvas"]}
        );
    }}

    QWidget#workspaceCanvas {{
        background: transparent;
    }}

    QWidget#workspaceHero {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {t["toolbar_glow"]},
            stop: 1 {t["panel_raised"]}
        );
        border: 1px solid {t["border_soft"]};
        border-radius: 18px;
    }}

    QLabel#workspaceEyebrow {{
        color: {t["accent_hover"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }}

    QLabel#workspaceTitle {{
        color: {t["text_primary"]};
        font-size: 24px;
        font-weight: 700;
    }}

    QLabel#workspaceSubtitle {{
        color: {t["text_secondary"]};
        font-size: 13px;
    }}

    QLabel#workspaceHeroPill {{
        background: {t["surface_inset"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 999px;
        padding: 5px 11px;
        color: {t["text_secondary"]};
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel#workspaceHeroPill[statusTone="warning"] {{
        background: {t["warning_soft"]};
        color: {t["warning"]};
        border-color: {t["warning_border_soft"]};
    }}

    QLabel#workspaceHeroPill[statusTone="success"] {{
        background: {t["success_soft"]};
        color: {t["success"]};
        border-color: {t["success"]};
    }}

    QLabel#workspaceHeroPill[statusTone="danger"] {{
        background: {t["destructive_soft"]};
        color: {t["destructive"]};
        border-color: {t["destructive_border_soft"]};
    }}

    QMenuBar {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 {t["canvas_glow"]},
            stop: 1 {t["canvas"]}
        );
        border-bottom: 1px solid {t["border_soft"]};
        padding: 5px 10px 6px 10px;
        spacing: 4px;
    }}

    QMenuBar::item {{
        background: transparent;
        border-radius: 8px;
        padding: 6px 10px;
        margin: 0 1px;
        color: {t["text_secondary"]};
    }}

    QMenuBar::item:selected {{
        background: {t["menu_hover"]};
        color: {t["text_primary"]};
    }}

    QMenu {{
        background: {t["panel_raised"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 12px;
        padding: 8px;
    }}

    QMenu::item {{
        padding: 8px 12px;
        border-radius: 8px;
        color: {t["text_primary"]};
    }}

    QMenu::item:selected {{
        background: {t["menu_hover"]};
    }}

    QMenu::separator {{
        height: 1px;
        margin: 6px 8px;
        background: {t["border_soft"]};
    }}

    QToolBar#mainToolbar {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {t["toolbar_glow"]},
            stop: 1 {t["panel_raised"]}
        );
        border: 1px solid {t["border_soft"]};
        border-radius: 14px;
        spacing: 8px;
        padding: 10px 12px 9px 12px;
    }}

    QToolBar#mainToolbar::separator {{
        width: 10px;
        background: transparent;
    }}

    QToolBar#mainToolbar QToolButton {{
        min-height: 34px;
        padding: 0 12px;
        border-radius: 8px;
        border: 1px solid {t["border_soft"]};
        background: {t["panel_raised"]};
        color: {t["text_primary"]};
    }}

    QToolBar#mainToolbar QToolButton:hover {{
        background: {t["surface_hover"]};
        border-color: {t["border_strong"]};
    }}

    QToolBar#mainToolbar QToolButton:pressed,
    QToolBar#mainToolbar QToolButton:checked {{
        background: {t["surface_pressed"]};
    }}

    QToolBar#mainToolbar QToolButton[variant="primary"] {{
        background: {t["accent"]};
        border-color: {t["accent_hover"]};
        color: #3A2B1C;
        font-weight: 600;
    }}

    QToolBar#mainToolbar QToolButton[variant="primary"]:hover {{
        background: {t["accent_hover"]};
    }}

    QToolBar#mainToolbar QToolButton[variant="secondary"] {{
        background: {t["accent_soft"]};
        color: {t["accent_hover"]};
        border-color: {t["accent_border_soft"]};
        font-weight: 600;
    }}

    QToolBar#mainToolbar QToolButton[variant="secondary"]:hover {{
        background: {t["secondary_hover_fill"]};
        border-color: {t["accent_hover"]};
    }}

    QToolBar#mainToolbar QToolButton[variant="subtle"] {{
        background: {t["surface_inset"]};
        color: {t["text_secondary"]};
    }}

    QLabel[role="windowTitle"] {{
        font-size: 18px;
        font-weight: 600;
        color: {t["text_primary"]};
    }}

    QLabel[role="sectionTitle"] {{
        font-size: 16px;
        font-weight: 600;
        color: {t["text_primary"]};
    }}

    QLabel[role="subSectionTitle"] {{
        font-size: 13px;
        font-weight: 600;
        color: {t["text_secondary"]};
    }}

    QLabel[role="caption"] {{
        font-size: 11px;
        font-weight: 600;
        color: {t["text_secondary"]};
    }}

    QLabel[role="muted"] {{
        color: {t["text_muted"]};
    }}

    QLabel#statusPill {{
        background: {t["panel_raised"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 999px;
        padding: 4px 10px;
        color: {t["text_secondary"]};
    }}

    QLabel#statusPill[statusTone="warning"] {{
        background: {t["warning_soft"]};
        color: {t["warning"]};
        border-color: {t["warning"]};
    }}

    QLabel#statusPill[statusTone="success"] {{
        background: {t["success_soft"]};
        color: {t["success"]};
        border-color: {t["success"]};
    }}

    QLabel#statusPill[statusTone="danger"] {{
        background: {t["destructive_soft"]};
        color: {t["destructive"]};
        border-color: {t["destructive"]};
    }}

    QWidget#sidebarPanel,
    QWidget#detailPanel,
    QDialog,
    QMessageBox,
    QFrame#dialogShell {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {t["toolbar_glow"]},
            stop: 1 {t["panel_raised"]}
        );
        border: 1px solid {t["border_soft"]};
        border-radius: 16px;
    }}

    QWidget#sidebarPanel {{
        background: {t["panel_base"]};
    }}

    QFrame#sidebarSummaryCard,
    QFrame#detailHeaderCard {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {t["toolbar_glow"]},
            stop: 1 {t["surface_inset"]}
        );
        border: 1px solid {t["accent_border_faint"]};
        border-radius: 14px;
    }}

    QFrame#dialogHeroCard {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {t["toolbar_glow"]},
            stop: 1 {t["accent_soft"]}
        );
        border: 1px solid {t["accent_border_faint"]};
        border-radius: 16px;
    }}

    QLabel#dialogHeroSummary {{
        color: {t["text_secondary"]};
        font-size: 13px;
    }}

    QLabel#dialogHeroPill {{
        background: {t["panel_raised"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 999px;
        padding: 5px 11px;
        color: {t["text_secondary"]};
        font-size: 11px;
        font-weight: 700;
    }}

    QFrame#dialogSectionCard {{
        background: {t["surface_inset"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 14px;
    }}

    QLabel#dialogSectionTitle {{
        color: {t["accent_hover"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.04em;
    }}

    QLabel#dialogCurrentSection {{
        color: {t["text_primary"]};
        font-size: 18px;
        font-weight: 700;
    }}

    QLabel#sidebarSummaryTitle,
    QLabel#runtimeMetricLabel {{
        color: {t["accent_hover"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.03em;
    }}

    QLabel#sidebarSummaryBody,
    QLabel#detailHeaderBody {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}

    QLabel#sidebarSummaryMeta {{
        color: {t["text_muted"]};
        font-size: 11px;
    }}

    QLabel#detailHeaderPill {{
        background: {t["panel_raised"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 999px;
        padding: 3px 9px;
        color: {t["text_secondary"]};
        font-size: 11px;
        font-weight: 600;
    }}

    QFrame#runtimeMetricCard {{
        background: {t["surface"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 12px;
    }}

    QLabel#runtimeMetricValue {{
        color: {t["text_primary"]};
        font-size: 12px;
        font-weight: 600;
    }}

    QLabel#runtimeMetricValue[statusTone="success"] {{
        color: {t["success"]};
    }}

    QLabel#runtimeMetricValue[statusTone="warning"] {{
        color: {t["warning"]};
    }}

    QLabel#runtimeMetricValue[statusTone="muted"] {{
        color: {t["text_secondary"]};
    }}

    QFrame#sidebarGroup,
    QFrame#detailGroup,
    QFrame#qrBlock,
    QFrame#tableBlock,
    QFrame#actionGroup,
    QFrame#formGroup,
    QFrame#previewGroup,
    QFrame#subscriptionInfoGroup {{
        background: {t["surface_inset"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 12px;
    }}

    QWidget#cardViewRoot {{
        background: transparent;
    }}

    QListWidget#cardList {{
        background: transparent;
        border: none;
        outline: none;
        padding: 4px 2px 8px 2px;
    }}

    QListWidget#cardList::item {{
        background: transparent;
        border: none;
        margin: 3px;
        padding: 2px;
    }}

    QFrame#entryCard {{
        background: {t["surface"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 14px;
    }}

    QFrame#entryCard:hover {{
        background: {t["card_hover_fill"]};
        border-color: {t["border_strong"]};
    }}

    QFrame#entryCard[selected="true"] {{
        background: {t["card_selected_fill"]};
        border: 1px solid {t["accent_hover"]};
    }}

    QFrame#entryCard[problem="true"] {{
        border-color: {t["warning"]};
    }}

    QFrame#entryCard[muted="true"] {{
        background: {t["surface_inset"]};
    }}

    QFrame#cardQrWell {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {t["qr_well_glow"]},
            stop: 1 {t["surface_inset"]}
        );
        border: 1px solid {t["warm_border_soft"]};
        border-radius: 12px;
    }}

    QLabel#cardTitle {{
        font-size: 15px;
        font-weight: 700;
        color: {t["text_primary"]};
    }}

    QLabel#cardEndpoint {{
        color: {t["text_primary"]};
        font-weight: 600;
    }}

    QLabel#cardMetaPrimary {{
        color: {t["text_secondary"]};
        font-weight: 500;
    }}

    QLabel#cardMetaSecondary,
    QLabel#cardTags {{
        color: {t["text_secondary"]};
    }}

    QLabel#cardStatusHint {{
        color: {t["text_muted"]};
        font-size: 12px;
    }}

    QLabel#favoritePill {{
        min-width: 22px;
        min-height: 22px;
        max-width: 22px;
        max-height: 22px;
        border-radius: 11px;
        background: {t["accent_soft"]};
        color: {t["accent_hover"]};
        font-size: 13px;
        font-weight: 700;
    }}

    QLabel#warningPill {{
        background: {t["warning_soft"]};
        color: {t["warning"]};
        border: 1px solid {t["warning_border_soft"]};
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel#emptyQrState {{
        color: {t["text_muted"]};
        font-size: 12px;
    }}

    QLabel#qrCanvas {{
        background: {t["qr_canvas_fill"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 12px;
        color: {t["text_muted"]};
    }}

    QLineEdit,
    QPlainTextEdit,
    QComboBox,
    QSpinBox,
    QTableWidget,
    QScrollArea,
    QListWidget,
    QTextEdit,
    QTextBrowser {{
        background: {t["surface"]};
        border: 1px solid {t["border_soft"]};
        color: {t["text_primary"]};
    }}

    QLineEdit,
    QComboBox,
    QSpinBox {{
        min-height: 34px;
        padding: 0 10px;
        border-radius: 8px;
    }}

    QPlainTextEdit,
    QTextEdit {{
        padding: 10px 12px;
        border-radius: 10px;
    }}

    QLineEdit:hover,
    QPlainTextEdit:hover,
    QComboBox:hover,
    QSpinBox:hover {{
        background: {t["surface_hover"]};
        border-color: {t["border_strong"]};
    }}

    QLineEdit:focus,
    QPlainTextEdit:focus,
    QComboBox:focus,
    QSpinBox:focus,
    QListWidget:focus,
    QTableWidget:focus {{
        border: 1px solid {t["accent_hover"]};
        outline: none;
    }}

    QLineEdit#searchField {{
        min-height: 36px;
        padding: 0 14px;
        border-radius: 10px;
        background: {t["panel_raised"]};
        border: 1px solid {t["border_soft"]};
        color: {t["text_primary"]};
        font-size: 13px;
    }}

    QLineEdit#searchField:hover {{
        background: {t["surface"]};
    }}

    QLineEdit#searchField:focus {{
        border: 1px solid {t["accent_hover"]};
        background: {t["surface"]};
    }}

    QLineEdit#expiryField[invalid="true"] {{
        border-color: {t["destructive"]};
        background: {t["destructive_soft"]};
    }}

    QLineEdit[invalid="true"],
    QPlainTextEdit[invalid="true"],
    QComboBox[invalid="true"],
    QSpinBox[invalid="true"] {{
        border-color: {t["destructive"]};
        background: {t["destructive_soft"]};
    }}

    QComboBox::drop-down,
    QSpinBox::up-button,
    QSpinBox::down-button {{
        border: none;
        width: 26px;
        background: transparent;
    }}

    QComboBox::down-arrow {{
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {t["text_secondary"]};
        margin-right: 10px;
    }}

    QPushButton {{
        min-height: 34px;
        padding: 0 12px;
        border-radius: 8px;
        border: 1px solid {t["border_soft"]};
        background: {t["panel_raised"]};
        color: {t["text_primary"]};
    }}

    QPushButton:hover {{
        background: {t["surface_hover"]};
        border-color: {t["border_strong"]};
    }}

    QPushButton:pressed {{
        background: {t["surface_pressed"]};
    }}

    QPushButton:disabled {{
        background: {t["disabled_fill"]};
        color: {t["disabled_text"]};
        border-color: {t["border_soft"]};
    }}

    QPushButton[variant="primary"] {{
        background: {t["accent"]};
        color: #3A2B1C;
        border-color: {t["accent_hover"]};
        font-weight: 600;
    }}

    QPushButton[variant="primary"]:hover {{
        background: {t["accent_hover"]};
    }}

    QPushButton[variant="secondary"] {{
        background: {t["accent_soft"]};
        color: {t["accent_hover"]};
        border-color: {t["accent_border_soft"]};
        font-weight: 600;
    }}

    QPushButton[variant="secondary"]:hover {{
        background: {t["secondary_hover_fill"]};
        border-color: {t["accent_hover"]};
    }}

    QPushButton[variant="subtle"] {{
        background: {t["surface_inset"]};
        color: {t["text_secondary"]};
    }}

    QPushButton[variant="destructive"] {{
        background: {t["destructive_soft"]};
        color: {t["destructive"]};
        border-color: {t["destructive_border_soft"]};
        font-weight: 600;
    }}

    QPushButton[variant="destructive"]:hover {{
        background: {t["surface_pressed"]};
        border-color: {t["destructive"]};
    }}

    QCheckBox {{
        spacing: 8px;
        color: {t["text_secondary"]};
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 6px;
        border: 1px solid {t["border_strong"]};
        background: {t["surface"]};
    }}

    QCheckBox::indicator:hover {{
        border-color: {t["accent_hover"]};
        background: {t["surface_hover"]};
    }}

    QCheckBox::indicator:checked {{
        background: {t["accent_soft"]};
        border-color: {t["accent_hover"]};
    }}

    QFrame#typeFilterRow {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
    }}

    QFrame#typeFilterRow:hover {{
        background: {t["surface_hover"]};
        border-color: {t["warm_border_faint"]};
    }}

    QFrame#typeFilterRow[checked="true"] {{
        background: {t["selection_soft"]};
        border-color: {t["accent_border_tint"]};
    }}

    QLabel#typeDot {{
        border-radius: 4px;
        min-width: 8px;
        max-width: 8px;
        min-height: 8px;
        max-height: 8px;
    }}

    QToolButton#tagChip {{
        min-height: 22px;
        padding: 0 10px;
        border-radius: 999px;
        border: 1px solid {t["border_soft"]};
        background: {t["surface"]};
        color: {t["text_secondary"]};
        text-align: left;
    }}

    QToolButton#tagChip:hover {{
        background: {t["surface_hover"]};
    }}

    QToolButton#tagChip:checked {{
        background: {t["accent_soft"]};
        color: {t["accent_hover"]};
        border-color: {t["accent_hover"]};
        font-weight: 600;
    }}

    QLabel#reachabilityMeta {{
        color: {t["text_muted"]};
        font-size: 12px;
    }}

    QLabel#reachabilitySummary {{
        color: {t["text_secondary"]};
        line-height: 1.25em;
    }}

    QLabel#reachabilityValue {{
        color: {t["text_primary"]};
    }}

    QFrame#reachabilityDetails {{
        background: {t["reachability_panel_fill"]};
        border: 1px solid {t["warm_border_faint"]};
        border-radius: 10px;
    }}

    QFrame#runtimeSummaryCard {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {t["summary_card_glow"]},
            stop: 1 {t["surface_inset"]}
        );
        border: 1px solid {t["accent_border_faint"]};
        border-radius: 12px;
    }}

    QPlainTextEdit#reachabilityLog {{
        background: {t["surface"]};
        border: 1px solid {t["border_soft"]};
        color: {t["text_secondary"]};
        border-radius: 10px;
    }}

    QPlainTextEdit#runtimeLog {{
        background: {t["surface"]};
        border: 1px solid {t["border_soft"]};
        color: {t["text_secondary"]};
        border-radius: 10px;
    }}

    QTextBrowser#helpContentView,
    QTextBrowser#welcomeBodyView {{
        background: transparent;
        border: none;
        color: {t["text_secondary"]};
    }}

    QListWidget#helpSectionList {{
        background: transparent;
        border: none;
    }}

    QTableWidget#sessionHistoryTable {{
        background: {t["surface_inset"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 12px;
    }}

    QListWidget#helpSectionList::item {{
        border-radius: 10px;
        margin: 2px 4px;
        padding: 8px 10px;
        color: {t["text_secondary"]};
    }}

    QListWidget#helpSectionList::item:selected {{
        background: {t["accent_soft"]};
        color: {t["accent_hover"]};
        border: 1px solid {t["accent_border_soft"]};
    }}

    QListWidget#helpSectionList::item:hover {{
        background: {t["surface_hover"]};
        color: {t["text_primary"]};
    }}

    QLabel#inlineValidation {{
        color: {t["destructive"]};
        background: {t["destructive_soft"]};
        border: 1px solid {t["validation_border"]};
        border-radius: 10px;
        padding: 8px 10px;
    }}

    QLabel#dialogSourceLabel {{
        color: {t["text_muted"]};
        font-size: 11px;
    }}

    QLabel#typeBadge {{
        border-radius: 999px;
        min-height: 20px;
        padding: 1px 8px;
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel#cardStatusPill {{
        border-radius: 999px;
        min-height: 20px;
        padding: 1px 8px;
        font-size: 11px;
        font-weight: 700;
        background: {t["surface_inset"]};
        color: {t["text_secondary"]};
        border: 1px solid {t["border_soft"]};
    }}

    QLabel#cardStatusPill[statusTone="muted"] {{
        background: {t["status_muted_fill"]};
        color: {t["text_secondary"]};
        border-color: {t["warm_border_soft"]};
    }}

    QLabel#cardStatusPill[statusTone="success"] {{
        background: {t["success_soft"]};
        color: {t["success"]};
        border-color: rgba(118, 155, 115, 0.42);
    }}

    QLabel#cardStatusPill[statusTone="warning"] {{
        background: {t["warning_soft"]};
        color: {t["warning"]};
        border-color: {t["warning_border_soft"]};
    }}

    QLabel#cardStatusPill[statusTone="danger"] {{
        background: {t["destructive_soft"]};
        color: {t["destructive"]};
        border-color: {t["destructive_border_soft"]};
    }}

    QTableWidget {{
        border-radius: 12px;
        gridline-color: {t["border_soft"]};
        padding: 0;
        selection-background-color: {t["accent_cool_soft"]};
        selection-color: {t["text_primary"]};
    }}

    QTableWidget#parsedTable,
    QTableWidget#subscriptionPreviewTable,
    QTableWidget#reachabilityHistoryTable {{
        background: {t["surface_inset"]};
    }}

    QHeaderView::section {{
        background: {t["surface_alt"]};
        color: {t["text_secondary"]};
        padding: 6px 10px;
        border: none;
        border-bottom: 1px solid {t["border_soft"]};
        font-size: 11px;
        font-weight: 600;
    }}

    QTableCornerButton::section {{
        background: {t["surface_alt"]};
        border: none;
        border-bottom: 1px solid {t["border_soft"]};
    }}

    QTableWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid {t["line_soft"]};
        color: {t["text_primary"]};
    }}

    QTableWidget::item:hover {{
        background: {t["table_row_hover"]};
    }}

    QSlider::groove:horizontal {{
        height: 6px;
        border-radius: 3px;
        background: {t["surface_alt"]};
    }}

    QSlider::sub-page:horizontal {{
        background: {t["accent"]};
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        width: 16px;
        margin: -5px 0;
        border-radius: 8px;
        border: 1px solid {t["border_soft"]};
        background: {t["panel_raised"]};
    }}

    QSlider::handle:horizontal:hover {{
        border-color: {t["accent_hover"]};
        background: {t["surface_hover"]};
    }}

    QScrollArea {{
        border: none;
        background: transparent;
    }}

    QScrollBar:vertical,
    QScrollBar:horizontal {{
        background: transparent;
        border: none;
        margin: 2px;
    }}

    QScrollBar:vertical {{
        width: 12px;
    }}

    QScrollBar:horizontal {{
        height: 12px;
    }}

    QScrollBar::handle {{
        background: {t["border_strong"]};
        border-radius: 6px;
        min-height: 28px;
        min-width: 28px;
    }}

    QScrollBar::handle:hover {{
        background: {t["accent"]};
    }}

    QScrollBar::add-line,
    QScrollBar::sub-line,
    QScrollBar::add-page,
    QScrollBar::sub-page {{
        border: none;
        background: transparent;
    }}

    QSplitter::handle {{
        background: transparent;
    }}

    QSplitter::handle:horizontal {{
        width: 10px;
    }}

    QSplitter::handle:horizontal:hover {{
        background: {t["splitter_hover"]};
        border-radius: 5px;
    }}

    QStatusBar {{
        background: transparent;
        border-top: 1px solid {t["border_soft"]};
        padding: 6px 8px 8px 8px;
    }}

    QToolTip {{
        background: {t["panel_raised"]};
        color: {t["text_primary"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 10px;
        padding: 8px 10px;
    }}
    """


def apply_app_theme(app: QApplication, theme: str) -> None:
    app.setPalette(build_palette(theme))
    app.setStyleSheet(build_stylesheet(theme))


def refresh_widget_style(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_widget_status(widget: QWidget, property_name: str, value: Any) -> None:
    widget.setProperty(property_name, value)
    refresh_widget_style(widget)


def make_form_label(text: str, min_width: int = 78) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "caption")
    label.setMinimumWidth(min_width)
    return label


def apply_button_icon(button: QAbstractButton, icon_name: str, color: str = "#6E6258", size: int = 16) -> None:
    button.setIcon(icon(icon_name, color=color, size=size))
    button.setIconSize(QSize(size, size))


def apply_action_icon(action: QAction, icon_name: str, color: str = "#6E6258", size: int = 18) -> None:
    action.setIcon(icon(icon_name, color=color, size=size))
