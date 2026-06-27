"""本地模型文章翻译器 — Desktop article translator using an LM Studio backend.

Loads PDF / Word / Markdown / plain-text documents, translates them to
Simplified Chinese block-by-block via an OpenAI-compatible local model, shows
the result side-by-side, and exports the translation to PDF.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QRectF
from PySide6.QtGui import (
    QAction, QFont, QTextDocument, QPageSize, QKeySequence, QIcon,
    QTextCursor, QTextCharFormat, QPainter, QPen, QColor,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QSplitter, QLabel, QLineEdit, QFileDialog,
    QMessageBox, QComboBox, QStatusBar, QFrame,
)

import extractors
from translator import Translator, TranslationError
from llama_backend import LlamaBackend, LlamaBackendError


def resource_path(name: str) -> str:
    """Resolve a bundled resource both in dev and inside a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# CJK UI font, resolved per-OS at startup (see resolve_cjk_font).
CJK_FONT = "Microsoft YaHei"


def resolve_cjk_font() -> str:
    """Pick an installed CJK font for the current OS."""
    from PySide6.QtGui import QFontDatabase
    if sys.platform == "win32":
        candidates = ["Microsoft YaHei", "微软雅黑", "SimHei", "SimSun"]
    elif sys.platform == "darwin":
        candidates = ["PingFang SC", "Heiti SC", "STHeiti", "Songti SC"]
    else:
        candidates = ["Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
                      "WenQuanYi Zen Hei", "WenQuanYi Micro Hei"]
    try:
        families = set(QFontDatabase.families())
    except Exception:  # noqa: BLE001
        return candidates[0]
    for c in candidates:
        if c in families:
            return c
    return candidates[0]


_QSS_TEMPLATE = """
QMainWindow, QWidget#central { background: @win_bg@; }
/* No font-size on QWidget: it would override QTextEdit.setFont(). Base font
   is set via QApplication.setFont() instead. */
QWidget { color: @text@; }

QMenuBar { background: @menu_bg@; border-bottom: 1px solid @border@; }
QMenuBar::item:selected { background: @menu_sel@; }
QMenu { background: @card_bg@; color: @text@; border: 1px solid @border2@; }
QMenu::item:selected { background: @menu_sel@; }

QFrame#card { background: @card_bg@; border: 1px solid @border@; border-radius: 12px; }

QLabel#paneTitle { font-size: 13px; font-weight: 600; color: @title@; padding: 2px 2px 6px 2px; }
QLabel#fieldLabel { color: @subtle@; font-size: 12px; }

QLineEdit, QComboBox {
    background: @input_bg@; border: 1px solid @border2@; border-radius: 8px;
    padding: 6px 10px; min-height: 18px; color: @text@; selection-background-color: @sel@;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid @primary@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    border: 1px solid @border2@; background: @card_bg@; color: @text@;
    selection-background-color: @menu_sel@; selection-color: @text@; outline: none;
}

QTextEdit {
    background: @card_bg@; border: 1px solid @border@; border-radius: 10px;
    padding: 10px; color: @text@; selection-background-color: @sel@;
}

QPushButton {
    background: @btn_bg@; border: 1px solid @border2@; border-radius: 9px;
    padding: 8px 14px; font-weight: 600; color: @btn_text@;
}
QPushButton:hover { background: @btn_hover@; border-color: @btn_hoverb@; }
QPushButton:pressed { background: @btn_press@; }
QPushButton:disabled { color: @dis_text@; background: @dis_bg@; border-color: @dis_border@; }

QPushButton#primary { background: @primary@; border: 1px solid @primary@; color: #ffffff; }
QPushButton#primary:hover { background: @primary_hover@; }
QPushButton#primary:pressed { background: @primary_press@; }
QPushButton#primary:disabled { background: @primary_dis@; border-color: @primary_dis@; color: #ffffff; }

QPushButton#accent { background: @accent@; border: 1px solid @accent@; color: #ffffff; }
QPushButton#accent:hover { background: @accent_hover@; }
QPushButton#accent:disabled { background: @accent_dis@; border-color: @accent_dis@; color: #ffffff; }

QPushButton#danger { color: @danger_text@; border-color: @danger_border@; background: @btn_bg@; }
QPushButton#danger:hover { background: @danger_hover@; }

QStatusBar { background: @statusbar_bg@; border-top: 1px solid @border@; color: @subtle@; }
QStatusBar::item { border: none; }

QSplitter::handle { background: transparent; width: 10px; }

QPushButton#toggle { background: @btn_bg@; border: 1px solid @border2@; color: @subtle@; }
QPushButton#toggle:hover { background: @btn_hover@; }
QPushButton#toggle:checked { background: @toggle_chk_bg@; border: 1px solid @primary@; color: @toggle_chk_text@; }

QPushButton#fontBtn {
    background: @fontbtn_bg@; border: 1px solid @border2@; border-radius: 7px;
    padding: 0; font-weight: 700; font-size: 13px; color: @title@;
}
QPushButton#fontBtn:hover { background: @fontbtn_hover@; border-color: @primary@; color: @toggle_chk_text@; }
QPushButton#fontBtn:pressed { background: @fontbtn_press@; }
QLabel#fontSize { color: @subtle@; font-size: 12px; font-weight: 600; }

QLabel#dropOverlay {
    background: @drop_bg@; border: 2px dashed @primary@; border-radius: 16px;
    color: @toggle_chk_text@; font-size: 22px; font-weight: 700;
}
"""

_PALETTES = {
    "light": {
        "win_bg": "#f4f5fb", "text": "#1f2330", "card_bg": "#ffffff",
        "border": "#e3e5ee", "border2": "#d4d7e3", "subtle": "#6b7280",
        "title": "#4b5563", "input_bg": "#ffffff", "sel": "#c7d2fe",
        "menu_bg": "#ffffff", "menu_sel": "#eef0fb",
        "btn_bg": "#ffffff", "btn_text": "#374151", "btn_hover": "#f0f1fa",
        "btn_hoverb": "#c2c6d6", "btn_press": "#e6e8f6",
        "dis_text": "#aab0bd", "dis_bg": "#f5f6fa", "dis_border": "#e6e8f0",
        "statusbar_bg": "#ffffff", "toggle_chk_bg": "#eef0fe",
        "toggle_chk_text": "#4338ca", "fontbtn_bg": "#f3f4fb",
        "fontbtn_hover": "#e8eafb", "fontbtn_press": "#dadcf6",
        "primary": "#6366f1", "primary_hover": "#5457e8", "primary_press": "#4a4dd6",
        "primary_dis": "#c5c7f4", "accent": "#10b981", "accent_hover": "#0ea271",
        "accent_dis": "#b7e6d5", "danger_text": "#b91c1c",
        "danger_border": "#f0c4c4", "danger_hover": "#fdeeee",
        "drop_bg": "rgba(99,102,241,0.10)",
    },
    "dark": {
        "win_bg": "#15161b", "text": "#e6e7ea", "card_bg": "#23252e",
        "border": "#343742", "border2": "#3d4150", "subtle": "#9aa0ad",
        "title": "#b8bdc8", "input_bg": "#2c2f3a", "sel": "#3b3f8f",
        "menu_bg": "#1d1f27", "menu_sel": "#2b2e3a",
        "btn_bg": "#2c2f3a", "btn_text": "#d3d6de", "btn_hover": "#353948",
        "btn_hoverb": "#474c5c", "btn_press": "#3d4252",
        "dis_text": "#5b6070", "dis_bg": "#23252e", "dis_border": "#2e313c",
        "statusbar_bg": "#1d1f27", "toggle_chk_bg": "#2f3358",
        "toggle_chk_text": "#c7caff", "fontbtn_bg": "#2c2f3a",
        "fontbtn_hover": "#353948", "fontbtn_press": "#3d4252",
        "primary": "#6366f1", "primary_hover": "#5457e8", "primary_press": "#4a4dd6",
        "primary_dis": "#3a3c6b", "accent": "#10b981", "accent_hover": "#0ea271",
        "accent_dis": "#1c5645", "danger_text": "#f08a8a",
        "danger_border": "#5e3a3a", "danger_hover": "#3a2a2a",
        "drop_bg": "rgba(99,102,241,0.18)",
    },
}

# ring colors per theme: (track, arc, text)
_RING_COLORS = {
    "light": ("#e3e5ee", "#6366f1", "#4b5563"),
    "dark": ("#343742", "#7c7ff5", "#b8bdc8"),
}


def build_stylesheet(dark: bool) -> str:
    qss = _QSS_TEMPLATE
    for key, val in _PALETTES["dark" if dark else "light"].items():
        qss = qss.replace(f"@{key}@", val)
    return qss


class CircularProgress(QWidget):
    """Small ring progress: percentage in the center when determinate, a
    spinning arc when indeterminate (e.g. while a model downloads)."""

    def __init__(self, size: int = 46, parent=None):
        super().__init__(parent)
        self._min, self._max, self._value = 0, 100, 0
        self._indeterminate = False
        self._angle = 0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._spin)
        self._track = QColor("#e3e5ee")
        self._arc = QColor("#6366f1")
        self._textcol = QColor("#4b5563")
        self.hide()  # shown only while active

    def set_colors(self, track: str, arc: str, text: str):
        self._track, self._arc, self._textcol = QColor(track), QColor(arc), QColor(text)
        self.update()

    # QProgressBar-compatible API so call sites barely change
    def setRange(self, a: int, b: int):
        self._min, self._max = a, b
        self._set_indeterminate(a == 0 and b == 0)
        self.show()

    def setMaximum(self, m: int):
        self._max = m
        self._set_indeterminate(m == 0)
        self.show()

    def setValue(self, v: int):
        self._value = v
        self.update()

    def idle(self):
        """Stop and hide the ring (no active task)."""
        self._timer.stop()
        self._indeterminate = False
        self.hide()

    def setTextVisible(self, *_):  # no-op (kept for compatibility)
        pass

    def value(self):
        return self._value

    def maximum(self):
        return self._max

    def _set_indeterminate(self, on: bool):
        self._indeterminate = on
        if on and not self._timer.isActive():
            self._timer.start()
        elif not on:
            self._timer.stop()
        self.update()

    def _spin(self):
        self._angle = (self._angle + 9) % 360
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = 5
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

        track = QPen(self._track, 4)
        track.setCapStyle(Qt.RoundCap)
        p.setPen(track)
        p.drawArc(rect, 0, 360 * 16)

        arc = QPen(self._arc, 4)
        arc.setCapStyle(Qt.RoundCap)
        p.setPen(arc)
        if self._indeterminate:
            p.drawArc(rect, -self._angle * 16, 100 * 16)
        else:
            span = 0.0
            if self._max > self._min:
                span = (self._value - self._min) / (self._max - self._min)
            span = max(0.0, min(1.0, span))
            p.drawArc(rect, 90 * 16, -int(span * 360 * 16))
            p.setPen(self._textcol)
            f = self.font()
            f.setPixelSize(int(self.height() * 0.30))
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, f"{int(span * 100)}%")


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class TranslateWorker(QObject):
    progress = Signal(int, int)          # done, total
    block_done = Signal(str, str)        # source block, translated block
    finished = Signal()
    error = Signal(str)

    def __init__(self, translator: Translator, blocks):
        super().__init__()
        self.translator = translator
        self.blocks = blocks
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.blocks)
        try:
            for i, block in enumerate(self.blocks):
                if self._cancelled:
                    break
                translated = self.translator.translate_block(block)
                self.block_done.emit(block, translated)
                self.progress.emit(i + 1, total)
        except TranslationError as e:
            self.error.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001 - surface anything to the UI
            self.error.emit(f"未知错误: {e}")
            return
        self.finished.emit()


class OcrWorker(QObject):
    """Run image OCR on a background thread (the vision model is slow)."""
    finished = Signal(str)   # recognised text
    error = Signal(str)

    def __init__(self, translator: Translator, path: str):
        super().__init__()
        self.translator = translator
        self.path = path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            text = self.translator.ocr_image(self.path)
        except TranslationError as e:
            if not self._cancelled:
                self.error.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001
            if not self._cancelled:
                self.error.emit(f"识别失败: {e}")
            return
        if not self._cancelled:
            self.finished.emit(text)


class LlamaStartWorker(QObject):
    """Start a local llama-server for a role on a background thread."""
    log = Signal(str)
    ready = Signal(str, str, str)   # role, base_url, model_id
    error = Signal(str, str)        # role, message

    def __init__(self, backend: LlamaBackend, role: str):
        super().__init__()
        self.backend = backend
        self.role = role

    def run(self):
        try:
            base_url = self.backend.start(self.role, on_log=self.log.emit)
            model_id = self.backend.served_model_id(self.role) or ""
        except LlamaBackendError as e:
            self.error.emit(self.role, str(e))
            return
        except Exception as e:  # noqa: BLE001
            self.error.emit(self.role, f"启动失败: {e}")
            return
        self.ready.emit(self.role, base_url, model_id)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("本地模型文章翻译器")
        self.resize(1200, 800)
        icon = _icon()
        if icon:
            self.setWindowIcon(icon)

        self.translator = Translator()
        self.blocks: list[str] = []
        self.translations: list[str] = []
        self.current_file: str | None = None
        self.thread: QThread | None = None
        self.worker: TranslateWorker | None = None
        self.ocr_thread: QThread | None = None
        self.ocr_worker: OcrWorker | None = None
        self.md_mode = True              # render panes as Markdown
        self.source_text = ""            # current source as markdown/plain source
        self.theme_mode = "auto"         # "auto" | "light" | "dark"
        self.dark = False                # effective theme (computed)

        # local llama.cpp backend
        self.backend_mode = "remote"     # "remote" | "local"
        self.llama = LlamaBackend()
        self.llama_thread: QThread | None = None
        self.llama_worker: LlamaStartWorker | None = None
        self.local_ready: dict[str, bool] = {"translation": False, "ocr": False}
        self._pending_ocr_path: str | None = None

        self._build_ui()
        self._refresh_models()

    # -- UI construction ------------------------------------------------

    MIN_FONT = 8
    MAX_FONT = 48

    def _build_ui(self):
        self.font_sizes = {"source": 11, "target": 13}
        self.size_labels = {}

        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)

        # --- top card: connection + actions ---
        toolbar_card = QFrame()
        toolbar_card.setObjectName("card")
        tc = QVBoxLayout(toolbar_card)
        tc.setContentsMargins(16, 14, 16, 14)
        tc.setSpacing(12)

        # connection row
        conn = QHBoxLayout()
        conn.setSpacing(8)

        lbl_backend = QLabel("后端")
        lbl_backend.setObjectName("fieldLabel")
        conn.addWidget(lbl_backend)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("远程 (LM Studio)", "remote")
        self.backend_combo.addItem("本地 (llama.cpp)", "local")
        self.backend_combo.setMinimumWidth(150)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        conn.addWidget(self.backend_combo)

        self.source_combo = QComboBox()
        self.source_combo.addItem("下载源:自动", "auto")
        self.source_combo.addItem("HuggingFace", "huggingface")
        self.source_combo.addItem("国内镜像 (hf-mirror)", "hf-mirror")
        self.source_combo.addItem("ModelScope", "modelscope")
        self.source_combo.setToolTip("本地模型的下载来源（国内建议选镜像或 ModelScope）")
        self.source_combo.setCurrentIndex(0)
        self.source_combo.setEnabled(False)  # only relevant in local mode
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        conn.addWidget(self.source_combo)

        lbl_url = QLabel("服务地址")
        lbl_url.setObjectName("fieldLabel")
        conn.addWidget(lbl_url)
        self.url_edit = QLineEdit(self.translator.base_url)
        self.url_edit.setMinimumWidth(240)
        conn.addWidget(self.url_edit)

        lbl_model = QLabel("模型")
        lbl_model.setObjectName("fieldLabel")
        conn.addWidget(lbl_model)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(200)
        self.model_combo.addItem(self.translator.model)
        conn.addWidget(self.model_combo)

        self.refresh_btn = QPushButton("⟳ 刷新模型")
        self.refresh_btn.clicked.connect(self._refresh_models)
        conn.addWidget(self.refresh_btn)
        conn.addStretch(1)
        tc.addLayout(conn)

        # action row
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.open_btn = QPushButton("📂  打开文件")
        self.open_btn.clicked.connect(self.open_file)
        actions.addWidget(self.open_btn)

        self.translate_btn = QPushButton("🌐  开始翻译")
        self.translate_btn.setObjectName("primary")
        self.translate_btn.clicked.connect(self.start_translation)
        self.translate_btn.setEnabled(False)
        actions.addWidget(self.translate_btn)

        # circular progress ring sits between 开始翻译 and 取消
        self.progress = CircularProgress()
        actions.addWidget(self.progress)

        self.cancel_btn = QPushButton("⏹  取消")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self.cancel_translation)
        self.cancel_btn.setEnabled(False)
        actions.addWidget(self.cancel_btn)

        actions.addStretch(1)

        self.md_btn = QPushButton("✨ Markdown 渲染")
        self.md_btn.setObjectName("toggle")
        self.md_btn.setCheckable(True)
        self.md_btn.setChecked(self.md_mode)
        self.md_btn.setToolTip("以 Markdown 排版显示原文与译文")
        self.md_btn.toggled.connect(self._toggle_md)
        actions.addWidget(self.md_btn)

        self.save_pdf_btn = QPushButton("💾  保存为 PDF")
        self.save_pdf_btn.setObjectName("accent")
        self.save_pdf_btn.clicked.connect(self.save_pdf)
        self.save_pdf_btn.setEnabled(False)
        actions.addWidget(self.save_pdf_btn)

        self.save_txt_btn = QPushButton("保存为文本")
        self.save_txt_btn.clicked.connect(self.save_text)
        self.save_txt_btn.setEnabled(False)
        actions.addWidget(self.save_txt_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("toggle")
        self.theme_btn.setFixedWidth(44)
        self.theme_btn.clicked.connect(self._cycle_theme)
        actions.addWidget(self.theme_btn)
        tc.addLayout(actions)

        root.addWidget(toolbar_card)

        # --- side-by-side text panes ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(10)

        left = QFrame()
        left.setObjectName("card")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 12, 14, 14)
        lv.addLayout(self._make_pane_header("原文", "source"))
        self.source_view = QTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setFont(QFont(CJK_FONT, self.font_sizes["source"]))
        self.source_view.setAcceptDrops(False)
        self.source_view.viewport().setAcceptDrops(False)
        lv.addWidget(self.source_view)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("card")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(14, 12, 14, 14)
        rv.addLayout(self._make_pane_header("译文（中文）·可编辑", "target"))
        self.target_view = QTextEdit()
        self.target_view.setReadOnly(False)  # allow light editing before export
        self.target_view.setFont(QFont(CJK_FONT, self.font_sizes["target"]))
        self.target_view.setAcceptDrops(False)
        self.target_view.viewport().setAcceptDrops(False)
        rv.addWidget(self.target_view)
        splitter.addWidget(right)

        splitter.setSizes([580, 580])
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)

        # drag-and-drop: accept files dropped anywhere on the window
        self.setAcceptDrops(True)
        self.drop_overlay = QLabel(
            "松开以打开文件\n支持 PDF · Word · Markdown · 文本 · 图片(OCR)", central)
        self.drop_overlay.setObjectName("dropOverlay")
        self.drop_overlay.setAlignment(Qt.AlignCenter)
        self.drop_overlay.hide()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪 — 打开或拖入文件")

        self._build_menu()
        app = QApplication.instance()
        if app:
            try:  # follow OS theme changes when in auto mode (Qt 6.5+)
                app.styleHints().colorSchemeChanged.connect(
                    self._on_system_theme_changed)
            except (AttributeError, RuntimeError):
                pass
        self._apply_theme()

    def _make_pane_header(self, title_text: str, which: str) -> QHBoxLayout:
        """Title on the left, [A− | size | A+] font controls on the right."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        label = QLabel(title_text)
        label.setObjectName("paneTitle")
        row.addWidget(label)
        row.addStretch(1)

        minus = QPushButton("A−")
        minus.setObjectName("fontBtn")
        minus.setFixedSize(30, 26)
        minus.setToolTip("缩小字体")
        minus.clicked.connect(lambda: self._change_font(which, -1))
        row.addWidget(minus)

        size_lbl = QLabel(str(self.font_sizes[which]))
        size_lbl.setObjectName("fontSize")
        size_lbl.setAlignment(Qt.AlignCenter)
        size_lbl.setFixedWidth(26)
        size_lbl.setToolTip("当前字号")
        self.size_labels[which] = size_lbl
        row.addWidget(size_lbl)

        plus = QPushButton("A+")
        plus.setObjectName("fontBtn")
        plus.setFixedSize(30, 26)
        plus.setToolTip("放大字体")
        plus.clicked.connect(lambda: self._change_font(which, +1))
        row.addWidget(plus)

        return row

    def _change_font(self, which: str, delta: int):
        size = self.font_sizes[which] + delta
        size = max(self.MIN_FONT, min(self.MAX_FONT, size))
        if size == self.font_sizes[which]:
            return
        self.font_sizes[which] = size
        view = self.source_view if which == "source" else self.target_view

        # update the widget/default font so newly inserted text uses the new size
        font = QFont(CJK_FONT, size)
        view.setFont(font)
        view.document().setDefaultFont(font)

        if self.md_mode:
            # re-render so headings/bold scale relative to the new base size
            md = view.toMarkdown()
            view.setMarkdown(md)
            view.document().setDefaultFont(font)
        else:
            # rescale plain text already in the document
            saved = view.textCursor()
            cursor = view.textCursor()
            cursor.select(QTextCursor.Document)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(size)
            cursor.mergeCharFormat(fmt)
            view.setTextCursor(saved)

        self.size_labels[which].setText(str(size))

    # -- markdown rendering --------------------------------------------

    def _render_view(self, view, which: str, text: str):
        """Render text into a view as Markdown or plain text per md_mode."""
        font = QFont(CJK_FONT, self.font_sizes[which])
        view.document().setDefaultFont(font)
        view.setFont(font)
        if self.md_mode:
            view.setMarkdown(text)
            view.document().setDefaultFont(font)  # reassert after setMarkdown
        else:
            view.setPlainText(text)

    def _view_text(self, view) -> str:
        """Current content of a view as Markdown source (round-trippable)."""
        return view.toMarkdown() if self.md_mode else view.toPlainText()

    def _set_source(self, text: str):
        self.source_text = text
        self._render_view(self.source_view, "source", text)

    # -- theme ----------------------------------------------------------

    def _system_is_dark(self) -> bool:
        app = QApplication.instance()
        try:
            from PySide6.QtCore import Qt as _Qt
            return app.styleHints().colorScheme() == _Qt.ColorScheme.Dark
        except (AttributeError, RuntimeError):
            return False

    def _apply_theme(self):
        if self.theme_mode == "auto":
            self.dark = self._system_is_dark()
        else:
            self.dark = self.theme_mode == "dark"
        theme = "dark" if self.dark else "light"
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(self.dark))
        self.progress.set_colors(*_RING_COLORS[theme])

        labels = {"auto": "🌓", "light": "☀", "dark": "🌙"}
        tips = {
            "auto": "主题：跟随系统（点击切到浅色）",
            "light": "主题：浅色（点击切到深色）",
            "dark": "主题：深色（点击切到跟随系统）",
        }
        self.theme_btn.setText(labels[self.theme_mode])
        self.theme_btn.setToolTip(tips[self.theme_mode])

    def _cycle_theme(self):
        order = ["auto", "light", "dark"]
        self.theme_mode = order[(order.index(self.theme_mode) + 1) % 3]
        self._apply_theme()

    def _on_system_theme_changed(self, _scheme=None):
        if self.theme_mode == "auto":
            self._apply_theme()

    def _toggle_md(self, checked: bool):
        # capture current target content so manual edits survive the switch
        target_text = self._view_text(self.target_view).strip()
        self.md_mode = checked
        self._render_view(self.source_view, "source", self.source_text)
        self._render_view(self.target_view, "target", target_text)
        cur = self.target_view.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.target_view.setTextCursor(cur)

    def _build_menu(self):
        menu = self.menuBar().addMenu("文件")
        open_act = QAction("打开...", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self.open_file)
        menu.addAction(open_act)

        save_act = QAction("保存译文为 PDF...", self)
        save_act.setShortcut(QKeySequence.Save)
        save_act.triggered.connect(self.save_pdf)
        menu.addAction(save_act)

        menu.addSeparator()
        quit_act = QAction("退出", self)
        quit_act.triggered.connect(self.close)
        menu.addAction(quit_act)

    # -- connection -----------------------------------------------------

    def _sync_translator(self):
        # In local mode the URLs/model are managed by the llama backend.
        if self.backend_mode == "local":
            return
        url = self.url_edit.text().strip().rstrip("/")
        self.translator.base_url = url
        self.translator.ocr_base_url = url
        self.translator.model = self.model_combo.currentText().strip()

    def _refresh_models(self):
        if self.backend_mode == "local":
            return
        self._sync_translator()
        try:
            models = self.translator.list_models()
        except TranslationError as e:
            self.statusBar().showMessage(str(e))
            return
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if current in models:
            self.model_combo.setCurrentText(current)
        elif "hy-mt2-1.8b" in models:
            self.model_combo.setCurrentText("hy-mt2-1.8b")
        self.statusBar().showMessage(f"已连接，发现 {len(models)} 个模型")

    # -- backend switching (remote / local llama.cpp) -------------------

    def _on_backend_changed(self, _index: int):
        mode = self.backend_combo.currentData()
        if mode == self.backend_mode:
            return
        if self._is_busy() or self.llama_worker is not None:
            QMessageBox.information(self, "处理中", "请等任务完成后再切换后端。")
            # revert selection
            self.backend_combo.blockSignals(True)
            self.backend_combo.setCurrentIndex(0 if self.backend_mode == "remote" else 1)
            self.backend_combo.blockSignals(False)
            return

        self.backend_mode = mode
        remote = mode == "remote"
        self.url_edit.setEnabled(remote)
        self.model_combo.setEnabled(remote)
        self.refresh_btn.setEnabled(remote)
        self.source_combo.setEnabled(not remote)

        if remote:
            self.llama.stop_all()
            self.local_ready = {"translation": False, "ocr": False}
            self._sync_translator()
            self.statusBar().showMessage("已切换到远程后端 (LM Studio)")
        else:
            self.translate_btn.setEnabled(False)
            if self.llama.binary_available():
                self.statusBar().showMessage("正在启动本地翻译模型（首次会下载模型，请耐心等待）…")
            else:
                self.statusBar().showMessage("正在下载本地引擎与模型（首次较久，请耐心等待）…")
            self._start_local_role("translation")

    def _on_source_changed(self, _index: int):
        self.llama.download_source = self.source_combo.currentData()

    def _start_local_role(self, role: str):
        """Launch a local llama-server for a role on a background thread."""
        self.progress.setRange(0, 0)  # busy / spinning
        self.progress.setToolTip("模型下载中…" if not self.llama.binary_available()
                                 else "模型加载中…")
        self.llama_thread = QThread()
        self.llama_worker = LlamaStartWorker(self.llama, role)
        self.llama_worker.moveToThread(self.llama_thread)
        self.llama_thread.started.connect(self.llama_worker.run)
        self.llama_worker.log.connect(self._on_llama_log)
        self.llama_worker.ready.connect(self._on_llama_ready)
        self.llama_worker.error.connect(self._on_llama_error)
        self.llama_thread.start()

    def _on_llama_log(self, msg: str):
        # show only the last line, keep it short
        line = msg.strip().splitlines()[-1] if msg.strip() else ""
        self.statusBar().showMessage(line[:160])

    def _on_llama_ready(self, role: str, base_url: str, model_id: str):
        self._teardown_llama_thread()
        self.progress.idle()
        self.local_ready[role] = True
        if role == "translation":
            self.translator.base_url = base_url
            self.translator.model = model_id or "local"
            self.translate_btn.setEnabled(bool(self.blocks))
            self.statusBar().showMessage(f"本地翻译模型就绪 ✓ ({base_url})")
        elif role == "ocr":
            self.translator.ocr_base_url = base_url
            self.translator.ocr_model = model_id or "glm-ocr"
            self.statusBar().showMessage(f"本地 OCR 模型就绪 ✓ ({base_url})")
            if self._pending_ocr_path:
                path, self._pending_ocr_path = self._pending_ocr_path, None
                self._run_ocr_worker(path)

    def _on_llama_error(self, role: str, message: str):
        self._teardown_llama_thread()
        self.progress.idle()
        self._pending_ocr_path = None
        self._set_busy(False)
        QMessageBox.critical(self, "本地引擎启动失败", message)
        self.statusBar().showMessage(f"{role} 本地模型启动失败")

    def _teardown_llama_thread(self):
        if self.llama_thread:
            self.llama_thread.quit()
            self.llama_thread.wait()
            self.llama_thread = None
        self.llama_worker = None

    # -- file loading ---------------------------------------------------

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "",
            "支持的文件 (*.pdf *.docx *.doc *.md *.markdown *.txt "
            "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif);;"
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif);;"
            "所有文件 (*.*)",
        )
        if path:
            self._load_document(path)

    def _is_busy(self) -> bool:
        return (self.worker is not None or self.ocr_worker is not None
                or self.llama_worker is not None)

    def _load_document(self, path: str):
        if self._is_busy():
            QMessageBox.information(self, "处理中", "请等待当前任务完成或取消后再打开新文件。")
            return

        ext = os.path.splitext(path)[1].lower()
        if ext not in extractors.SUPPORTED_EXTENSIONS:
            QMessageBox.warning(
                self, "不支持的文件",
                f"不支持的文件类型: {ext or '(无扩展名)'}\n"
                "支持 PDF / Word / Markdown / 纯文本 / 图片(OCR)。",
            )
            return

        if extractors.is_image(path):
            self._start_ocr(path)
            return

        try:
            blocks = extractors.extract_blocks(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "读取失败", f"无法读取文件:\n{e}")
            return

        if not blocks:
            QMessageBox.warning(self, "空文档", "未能从该文件提取到任何文本。")
            return

        self.current_file = path
        self.blocks = blocks
        self.translations = []
        self._set_source("\n\n".join(blocks))
        self.target_view.clear()
        self.progress.setValue(0)
        self.translate_btn.setEnabled(True)
        self.save_pdf_btn.setEnabled(False)
        self.save_txt_btn.setEnabled(False)
        self.statusBar().showMessage(
            f"已加载 {os.path.basename(path)} — {len(blocks)} 个段落，开始翻译…"
        )
        self.start_translation()  # auto-start

    # -- drag & drop ----------------------------------------------------

    def _supported_drop_path(self, mime) -> str | None:
        """Return the first supported local file path in a drag's mime data."""
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in extractors.SUPPORTED_EXTENSIONS:
                return path
        return None

    def dragEnterEvent(self, event):
        if not self._is_busy() and self._supported_drop_path(event.mimeData()):
            event.acceptProposedAction()
            self._show_drop_overlay(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self._is_busy() and self._supported_drop_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._show_drop_overlay(False)
        event.accept()

    def dropEvent(self, event):
        self._show_drop_overlay(False)
        path = self._supported_drop_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self._load_document(path)
        else:
            event.ignore()

    def _show_drop_overlay(self, visible: bool):
        if visible:
            self.drop_overlay.setGeometry(self.centralWidget().rect())
            self.drop_overlay.raise_()
            self.drop_overlay.show()
        else:
            self.drop_overlay.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.drop_overlay.isVisible():
            self.drop_overlay.setGeometry(self.centralWidget().rect())

    # -- OCR (image -> text) -------------------------------------------

    def _start_ocr(self, path: str):
        self._sync_translator()
        self.current_file = path
        self.blocks = []
        self.translations = []
        self.source_view.setPlainText("⏳ 正在识别图片文字，请稍候…")
        self.target_view.clear()
        self.progress.setRange(0, 0)  # indeterminate / busy
        self.save_pdf_btn.setEnabled(False)
        self.save_txt_btn.setEnabled(False)
        self._set_busy(True)

        # local mode: make sure the OCR server is up first (lazy start)
        if self.backend_mode == "local" and not self.local_ready["ocr"]:
            self._pending_ocr_path = path
            self.statusBar().showMessage("正在启动本地 OCR 模型（首次会下载）…")
            self._start_local_role("ocr")
            return

        self.statusBar().showMessage(
            f"正在用 {self.translator.ocr_model} 识别 {os.path.basename(path)} …"
        )
        self._run_ocr_worker(path)

    def _run_ocr_worker(self, path: str):
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage(
            f"正在用 {self.translator.ocr_model} 识别 {os.path.basename(path)} …"
        )
        self.ocr_thread = QThread()
        self.ocr_worker = OcrWorker(self.translator, path)
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.finished.connect(self._on_ocr_done)
        self.ocr_worker.error.connect(self._on_ocr_error)
        self.ocr_thread.start()

    def _on_ocr_done(self, text: str):
        self._teardown_ocr_thread()
        self.progress.idle()
        self._set_busy(False)

        blocks = extractors.split_text_into_blocks(text)
        if not blocks:
            self.source_view.clear()
            self.translate_btn.setEnabled(False)
            QMessageBox.warning(self, "未识别到文字", "未能从该图片中识别出文字。")
            self.statusBar().showMessage("OCR 完成，但未识别到文字")
            return

        self.blocks = blocks
        self._set_source("\n\n".join(blocks))
        self.translate_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"图片识别完成 ✓ 共 {len(blocks)} 段，开始翻译…"
        )
        self.start_translation()  # auto-start

    def _on_ocr_error(self, message: str):
        self._teardown_ocr_thread()
        self.progress.idle()
        self._set_busy(False)
        self.source_view.clear()
        self.translate_btn.setEnabled(False)
        QMessageBox.critical(self, "OCR 出错", message)
        self.statusBar().showMessage("OCR 出错")

    def _teardown_ocr_thread(self):
        if self.ocr_thread:
            self.ocr_thread.quit()
            self.ocr_thread.wait()
            self.ocr_thread = None
        self.ocr_worker = None

    # -- translation ----------------------------------------------------

    def start_translation(self):
        if not self.blocks:
            return
        if self.backend_mode == "local" and not self.local_ready["translation"]:
            self.statusBar().showMessage("本地翻译模型尚未就绪，请稍候…")
            return
        self._sync_translator()
        if not self.translator.model:
            QMessageBox.warning(self, "缺少模型", "请先选择一个模型。")
            return

        self.translations = []
        self.target_view.clear()
        self.progress.setMaximum(len(self.blocks))
        self.progress.setValue(0)
        self._set_busy(True)

        self.thread = QThread()
        self.worker = TranslateWorker(self.translator, self.blocks)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.block_done.connect(self._on_block_done)
        self.worker.progress.connect(self._on_progress)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_finished)
        self.thread.start()

    def cancel_translation(self):
        if self.worker:
            self.worker.cancel()
            self.statusBar().showMessage("正在取消...")
        elif self.ocr_worker:
            self.ocr_worker.cancel()
            self._teardown_ocr_thread()
            self.progress.idle()
            self.source_view.clear()
            self._set_busy(False)
            self.statusBar().showMessage("已取消图片识别")

    def _on_block_done(self, source: str, translated: str):
        self.translations.append(translated)
        if self.md_mode:
            # re-render the accumulated translation as Markdown
            self._render_view(self.target_view, "target",
                              "\n\n".join(self.translations))
            cursor = self.target_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.target_view.setTextCursor(cursor)
            self.target_view.ensureCursorVisible()
            return
        cursor = self.target_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(self.font_sizes["target"])
        cursor.setCharFormat(fmt)
        if self.target_view.toPlainText():
            cursor.insertText("\n\n")
        cursor.insertText(translated)
        self.target_view.setTextCursor(cursor)
        self.target_view.ensureCursorVisible()

    def _on_progress(self, done: int, total: int):
        self.progress.setValue(done)
        self.statusBar().showMessage(f"翻译中... {done}/{total}")

    def _on_error(self, message: str):
        self._teardown_thread()
        self.progress.idle()
        self._set_busy(False)
        QMessageBox.critical(self, "翻译出错", message)
        self.statusBar().showMessage("翻译出错")

    def _on_finished(self):
        self._teardown_thread()
        self.progress.idle()
        self._set_busy(False)
        has_output = bool(self.target_view.toPlainText().strip())
        self.save_pdf_btn.setEnabled(has_output)
        self.save_txt_btn.setEnabled(has_output)
        self.statusBar().showMessage("翻译完成 ✓")

    def _teardown_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self.worker = None

    def _set_busy(self, busy: bool):
        self.translate_btn.setEnabled(not busy and bool(self.blocks))
        self.open_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.refresh_btn.setEnabled(not busy)

    # -- export ---------------------------------------------------------

    def save_pdf(self):
        text = self.target_view.toPlainText().strip()
        if not text:
            return
        default = self._default_save_name(".pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存为 PDF", default, "PDF 文件 (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self._write_pdf(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"无法保存 PDF:\n{e}")
            return
        self.statusBar().showMessage(f"已保存: {path}")

    def _write_pdf(self, path: str):
        doc = QTextDocument()
        font = QFont(CJK_FONT, 12)
        doc.setDefaultFont(font)
        name = os.path.basename(self.current_file) if self.current_file else ""

        if self.md_mode:
            # keep Markdown formatting (headings, bold, lists…)
            md = self.target_view.toMarkdown()
            title = f"# {name} — 中文译文\n\n" if name else ""
            doc.setMarkdown(title + md)
            doc.setDefaultFont(font)
        else:
            text = self.target_view.toPlainText()
            title = (
                f"<h2 style='font-family:{CJK_FONT}'>{name} — 中文译文</h2>"
                if name else ""
            )
            paragraphs = "".join(
                f"<p style='font-family:{CJK_FONT}; font-size:12pt; "
                f"line-height:150%'>{_escape_html(p)}</p>"
                for p in text.split("\n\n")
            )
            doc.setHtml(f"<html><body>{title}{paragraphs}</body></html>")

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setOutputFileName(path)
        doc.print_(printer)

    def save_text(self):
        text = self.target_view.toPlainText().strip()
        if not text:
            return
        default = self._default_save_name(".txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存为文本", default, "文本文件 (*.txt)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.statusBar().showMessage(f"已保存: {path}")

    def _default_save_name(self, ext: str) -> str:
        if self.current_file:
            base = os.path.splitext(os.path.basename(self.current_file))[0]
            return f"{base}_zh{ext}"
        return f"translation{ext}"

    def closeEvent(self, event):
        if self.worker:
            self.worker.cancel()
        if self.ocr_worker:
            self.ocr_worker.cancel()
        self._teardown_thread()
        self._teardown_ocr_thread()
        self._teardown_llama_thread()
        self.llama.stop_all()
        super().closeEvent(event)


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _icon() -> QIcon | None:
    for name in ("icon.ico", "icon.png"):
        p = resource_path(name)
        if os.path.exists(p):
            return QIcon(p)
    return None


def main():
    global CJK_FONT
    app = QApplication(sys.argv)
    app.setApplicationName("本地模型文章翻译器")
    CJK_FONT = resolve_cjk_font()
    base_font = QFont(CJK_FONT)
    base_font.setPixelSize(13)  # base UI font for chrome (buttons, labels…)
    app.setFont(base_font)
    icon = _icon()
    if icon:
        app.setWindowIcon(icon)
    app.setStyleSheet(build_stylesheet(False))
    win = MainWindow()  # applies the theme itself
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
