"""
VideoForge dark theme.
Kept intentionally simple so it works reliably on Windows with PySide6.
Avoids unsupported CSS properties (text-shadow, etc.).
"""

COLORS = {
    "bg_primary":    "#12121e",
    "bg_secondary":  "#1a1a2e",
    "bg_tertiary":   "#16213e",
    "bg_card":       "#1e1e32",
    "bg_hover":      "#252540",
    "bg_selected":   "#2a2a50",
    "border":        "#2d2d4e",
    "border_light":  "#3d3d6e",

    "accent":        "#6c63ff",
    "accent_hover":  "#7c73ff",
    "accent_dim":    "#3d3a99",
    "accent_text":   "#a89fff",

    "success":       "#27ae60",
    "success_bg":    "#1a3d2a",
    "warning":       "#e67e22",
    "warning_bg":    "#3d2e00",
    "error":         "#e74c3c",
    "error_bg":      "#3d1a18",
    "info":          "#3498db",
    "info_bg":       "#1a2d3d",

    "text_primary":  "#e8e8f0",
    "text_secondary":"#9898b8",
    "text_muted":    "#5a5a7a",
    "text_disabled": "#3d3d5a",

    # Aliases used by dashboard/widgets (maps old names to current values)
    "status_valid":      "#27ae60",
    "status_invalid":    "#e74c3c",
    "status_queued":     "#3498db",
    "status_processing": "#e67e22",
    "status_completed":  "#27ae60",
    "status_failed":     "#e74c3c",
    "status_cancelled":  "#9898b8",
}

STATUS_COLORS = {
    "discovered":  "#9898b8",
    "valid":       "#27ae60",
    "invalid":     "#e74c3c",
    "queued":      "#3498db",
    "processing":  "#e67e22",
    "completed":   "#27ae60",
    "failed":      "#e74c3c",
    "cancelled":   "#9898b8",
    "skipped":     "#5a5a7a",
}


def get_stylesheet() -> str:
    c = COLORS
    return f"""

/* ── Global ─────────────────────────────────────────── */
* {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: {c['text_primary']};
    selection-background-color: {c['accent']};
    selection-color: #ffffff;
    outline: none;
}}

QWidget {{
    background-color: {c['bg_primary']};
}}

QMainWindow {{
    background-color: {c['bg_primary']};
}}

/* ── Labels ─────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {c['text_primary']};
}}

/* ── Buttons ─────────────────────────────────────────── */
QPushButton {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border_light']};
    border-radius: 5px;
    padding: 5px 14px;
    min-height: 28px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {c['bg_hover']};
    border-color: {c['accent']};
}}
QPushButton:pressed {{
    background-color: {c['bg_selected']};
}}
QPushButton:disabled {{
    background-color: {c['bg_tertiary']};
    color: {c['text_muted']};
    border-color: {c['border']};
}}
QPushButton#primary {{
    background-color: {c['accent']};
    color: #ffffff;
    border: none;
    font-weight: bold;
}}
QPushButton#primary:hover {{
    background-color: {c['accent_hover']};
}}
QPushButton#primary:disabled {{
    background-color: {c['accent_dim']};
    color: {c['text_muted']};
}}
QPushButton#success {{
    background-color: {c['success_bg']};
    color: {c['success']};
    border-color: {c['success']};
}}
QPushButton#success:hover {{
    background-color: {c['success']};
    color: #ffffff;
}}
QPushButton#danger {{
    background-color: {c['error_bg']};
    color: {c['error']};
    border-color: {c['error']};
}}
QPushButton#danger:hover {{
    background-color: {c['error']};
    color: #ffffff;
}}
QPushButton#icon_btn {{
    background: transparent;
    border: none;
    padding: 3px;
    min-height: 24px;
    min-width: 24px;
}}
QPushButton#icon_btn:hover {{
    background-color: {c['bg_hover']};
    border-radius: 4px;
}}

/* ── Inputs ─────────────────────────────────────────── */
QLineEdit {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 5px 8px;
    min-height: 26px;
}}
QLineEdit:focus {{
    border-color: {c['accent']};
}}
QLineEdit:disabled {{
    color: {c['text_muted']};
    background-color: {c['bg_tertiary']};
}}

QTextEdit, QPlainTextEdit {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 4px;
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c['accent']};
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 4px 6px;
    min-height: 26px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c['accent']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {c['bg_hover']};
    border: none;
    width: 18px;
}}

/* ── ComboBox ─────────────────────────────────────────── */
QComboBox {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 5px 8px;
    min-height: 26px;
}}
QComboBox:focus {{
    border-color: {c['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border_light']};
    selection-background-color: {c['accent']};
    selection-color: #ffffff;
    padding: 2px;
}}

/* ── CheckBox ─────────────────────────────────────────── */
QCheckBox {{
    color: {c['text_primary']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 2px solid {c['border_light']};
    border-radius: 3px;
    background: {c['bg_secondary']};
}}
QCheckBox::indicator:checked {{
    background-color: {c['accent']};
    border-color: {c['accent']};
}}

/* ── Sliders ─────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c['border']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c['accent']};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']};
    border-radius: 2px;
}}

/* ── Progress Bar ─────────────────────────────────────── */
QProgressBar {{
    background-color: {c['bg_secondary']};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: {c['text_secondary']};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 4px;
}}

/* ── Tables ─────────────────────────────────────────── */
QTableWidget, QTableView {{
    background-color: {c['bg_secondary']};
    alternate-background-color: {c['bg_card']};
    gridline-color: transparent;
    border: 1px solid {c['border']};
    border-radius: 6px;
    color: {c['text_primary']};
}}
QTableWidget::item, QTableView::item {{
    padding: 6px 8px;
    color: {c['text_primary']};
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {c['bg_selected']};
    color: {c['text_primary']};
}}
QHeaderView::section {{
    background-color: {c['bg_tertiary']};
    color: {c['text_secondary']};
    padding: 7px 8px;
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 1px solid {c['border']};
    font-size: 11px;
    font-weight: bold;
}}

/* ── Tabs ─────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {c['border']};
    background-color: {c['bg_secondary']};
    border-radius: 0px 6px 6px 6px;
}}
QTabBar::tab {{
    background-color: {c['bg_tertiary']};
    color: {c['text_secondary']};
    padding: 8px 18px;
    border: 1px solid {c['border']};
    border-bottom: none;
    margin-right: 2px;
    font-size: 13px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background-color: {c['bg_secondary']};
    color: #ffffff;
    border-bottom: 2px solid {c['accent']};
    font-weight: 700;
}}
QTabBar::tab:hover {{
    background-color: {c['bg_hover']};
    color: {c['text_primary']};
}}

/* ── Scrollbars ─────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['border_light']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['text_muted']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {c['border_light']};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Lists ─────────────────────────────────────────────── */
QListWidget {{
    background-color: {c['bg_secondary']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    color: {c['text_primary']};
}}
QListWidget::item {{
    padding: 5px 8px;
    color: {c['text_primary']};
}}
QListWidget::item:hover {{
    background-color: {c['bg_hover']};
}}
QListWidget::item:selected {{
    background-color: {c['bg_selected']};
    color: {c['text_primary']};
}}

/* ── Splitter ─────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {c['border']};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}

/* ── GroupBox ─────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {c['border_light']};
    border-radius: 6px;
    margin-top: 16px;
    padding: 12px 8px 8px 8px;
    color: {c['text_primary']};
    font-weight: 600;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    top: -9px;
    padding: 0 6px;
    background-color: {c['bg_primary']};
    color: {c['text_primary']};
    font-size: 12px;
    font-weight: 700;
}}

/* ── Dialog button boxes ─────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 80px;
    font-weight: 600;
}}
QDialogButtonBox QPushButton[text="OK"],
QDialogButtonBox QPushButton[text="Save"] {{
    background-color: {c['accent']};
    color: #ffffff;
    border: none;
    font-weight: 700;
}}
QDialogButtonBox QPushButton[text="OK"]:hover,
QDialogButtonBox QPushButton[text="Save"]:hover {{
    background-color: {c['accent_hover']};
}}

/* ── Tooltips ─────────────────────────────────────────── */
QToolTip {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border_light']};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}}

/* ── Menus ─────────────────────────────────────────────── */
QMenuBar {{
    background-color: {c['bg_tertiary']};
    color: {c['text_primary']};
    border-bottom: 1px solid {c['border']};
}}
QMenuBar::item {{
    padding: 6px 12px;
    background: transparent;
    color: {c['text_primary']};
}}
QMenuBar::item:selected {{
    background-color: {c['bg_hover']};
}}
QMenu {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border_light']};
    border-radius: 5px;
    padding: 3px;
    color: {c['text_primary']};
}}
QMenu::item {{
    padding: 7px 18px;
    color: {c['text_primary']};
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {c['accent']};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 3px 6px;
}}

/* ── Section headers & metric cards ──────────────────────── */
QLabel#section_header {{
    color: {c['text_secondary']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
    padding: 4px 0 2px 0;
}}
QLabel#metric_value {{
    background: transparent;
}}
QLabel#metric_label {{
    color: {c['text_secondary']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: transparent;
}}

/* ── Status bar ─────────────────────────────────────────── */
QStatusBar {{
    background-color: {c['bg_tertiary']};
    color: {c['text_secondary']};
    border-top: 1px solid {c['border']};
    font-size: 12px;
}}
QStatusBar QLabel {{
    color: {c['text_secondary']};
    padding: 0 6px;
}}

/* ── Dialog ─────────────────────────────────────────────── */
QDialog {{
    background-color: {c['bg_secondary']};
}}

/* ── Frame cards / panels ─────────────────────────────── */
QFrame#card {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 8px;
}}
QFrame#panel {{
    background-color: {c['bg_secondary']};
    border: 1px solid {c['border']};
    border-radius: 6px;
}}

/* ── Dock ─────────────────────────────────────────────── */
QDockWidget::title {{
    background-color: {c['bg_tertiary']};
    padding: 7px 10px;
    font-weight: bold;
    border-bottom: 1px solid {c['border']};
    color: {c['text_primary']};
}}
"""


def status_badge_style(status: str) -> str:
    color = STATUS_COLORS.get(status, COLORS["text_muted"])
    # Derive dark background by mixing color with near-black
    h = color.lstrip("#")
    if len(h) == 6:
        r = max(0, int(int(h[0:2], 16) * 0.15))
        g = max(0, int(int(h[2:4], 16) * 0.15))
        b = max(0, int(int(h[4:6], 16) * 0.15))
        bg = f"#{r:02x}{g:02x}{b:02x}"
    else:
        bg = COLORS["bg_card"]
    return (
        f"color: {color}; background-color: {bg}; "
        f"border: 1px solid {color}; border-radius: 8px; "
        f"padding: 2px 8px; font-size: 11px; font-weight: bold;"
    )
