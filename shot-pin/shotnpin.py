#!/usr/bin/env python3
"""
ShotNPin - Simple screenshot, annotation, and pinning tool

A lightweight application for capturing, annotating, and pinning screenshots.
"""

# ============================================================================
# Standard Library Imports
# ============================================================================
import logging
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Callable

# ============================================================================
# Third-party Library Imports
# ============================================================================
from dataclasses import dataclass
from pynput import keyboard
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QByteArray, pyqtSignal, QObject
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import (
    QPixmap, QPainter, QPen, QBrush, QColor, QShortcut, QKeySequence, 
    QCursor, QIcon, QFont
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, 
    QColorDialog, QSlider, QHBoxLayout, QFileDialog, QLineEdit, 
    QSystemTrayIcon, QMenu, QMessageBox
)

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ShotNPin')

# ============================================================================
# Application Constants
# ============================================================================

# File and Path Constants
ICON_FILENAME = "icons8-screenshot-100.png"
SINGLE_INSTANCE_KEY = 'shotnpin_single_instance'

# Dimensions & Sizes
RESIZE_HANDLE_SIZE = 8
MIN_SIZE = 2
ICON_SIZE = 24
TOOLBAR_MARGIN = 5
TOOLBAR_SPACING = 3
SELECTION_BORDER_WIDTH = 2

# Drawing Defaults
DEFAULT_PEN_WIDTH = 2
DEFAULT_PEN_COLOR = QColor(255, 0, 0)
DEFAULT_FONT_SIZE = 16
MAX_HISTORY = 20

# Keyboard Shortcuts
GLOBAL_HOTKEY_CAP = '<ctrl>+<alt>+1'
GLOBAL_HOTKEY_PIN = '<ctrl>+<alt>+2'
KEYBOARD_STEP_SMALL = 1
KEYBOARD_STEP_LARGE = 10

# Colors
TOOLBAR_BG_COLOR = "#2b2b2b"
BUTTON_BG_COLOR = "#3c3c3c"
BUTTON_HOVER_COLOR = "#4c4c4c"
BUTTON_ACTIVE_COLOR = "#0078d4"
BORDER_COLOR = "#555"
SELECTION_BORDER_COLOR = QColor(0, 120, 215)
OVERLAY_COLOR = QColor(0, 0, 0, 100)

# Glow Effect Colors for PinnedOverlay
GLOW_LAYERS = [
    (QColor(220, 220, 220, 80), 1),
    (QColor(220, 220, 220, 60), 2),
    (QColor(220, 220, 220, 40), 3),
    (QColor(220, 220, 220, 20), 5),
    (QColor(220, 220, 220, 10), 9),
]

# ============================================================================
# SVG Icons
# ============================================================================
SVG_ICONS = {
    'undo': "M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3",
    'redo': "m15 15 6-6m0 0-6-6m6 6H9a6 6 0 0 0 0 12h3",
    'close': "M5 5L19 19M19 5L5 19",
    'pin': "M12 2A6 6 0 1 0 12 14L12 22L12 14A6 6 0 0 0 12 2Z",
    'copy': "M 16 9 V 5 a 2 2 0 0 0 -2 -2 H 6 A 2 2 0 0 0 4 5 v 8 A 2 2 0 0 0 6 15 h 2 m 8 -6 H 18 a 2 2 0 0 1 2 2 V 19 A 2 2 0 0 1 18 21 h -8 A 2 2 0 0 1 8 19 V 15 m 8 -6 H 10 a 2 2 0 0 0 -2 2 v 4",
    'save': "M12 3v13m-5-5l5 5l5-5M4 21h16",
    'rectangle': "M 5 7 A 2.25 2.25 0 0 1 7 5 h 10 a 2.25 2.25 0 0 1 2 2 v 10 a 2.25 2.25 0 0 1 -2 2 h -10 a 2.25 2.25 0 0 1 -2 -2 Z",
    'pen': "m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125",
    'line': "M4 20 L20 4",
    'text': "M4 7V4h16v3M9 20h6M12 4v16",
}

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SnapshotItem:
    """Represents a screenshot snapshot with selection state."""
    screenshot: QPixmap
    start_pos: Optional[QPoint] = None
    end_pos: Optional[QPoint] = None

@dataclass
class AnnotationState:
    """Represents an annotation state for undo/redo."""
    screenshot: QPixmap
    selection_rect: Optional[QRect] = None

# ============================================================================
# Helper Functions
# ============================================================================

def create_svg_icon(path_data: str, color: str = "#ffffff", size: int = ICON_SIZE) -> QIcon:
    """Create a QIcon from SVG path data."""
    svg_template = f'''<?xml version="1.0" encoding="UTF-8"?>
    <svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="{path_data}" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>'''

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(svg_template.encode()))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)

def get_app_icon() -> QIcon:
    """Get the application icon with correct path resolution."""
    icon_path = str(Path(__file__).parent / ICON_FILENAME)
    return QIcon(icon_path)

def get_app_controller() -> Optional["AppController"]:
    """Safely get the global AppController from QApplication instance."""
    app = QApplication.instance()
    return getattr(app, 'controller', None)

def get_actionbar() -> Optional["ActionBar"]:
    """Safely get the shared global actionbar from the AppController."""
    controller = get_app_controller()
    return getattr(controller, 'actionbar', None)

def get_virtual_desktop_bounds(screens) -> Tuple[int, int, int, int]:
    """Calculate the virtual desktop bounds from multiple screens."""
    if not screens:
        return (0, 0, 0, 0)

    min_x = min(screen.geometry().left() for screen in screens)
    min_y = min(screen.geometry().top() for screen in screens)
    max_x = max(screen.geometry().right() for screen in screens)
    max_y = max(screen.geometry().bottom() for screen in screens)

    return (min_x, min_y, max_x, max_y)

# ============================================================================
# Single Instance Management
# ============================================================================

class SingleInstance(QObject):
    """Uses QLocalServer/QLocalSocket for inter-process communication."""

    new_instance_detected = pyqtSignal(str)

    def __init__(self, key: str = SINGLE_INSTANCE_KEY):
        super().__init__()
        self.key = key
        self.server = None

    # Initialization Methods
    def is_already_running(self) -> bool:
        """Check if another instance is already running."""
        socket = QLocalSocket()
        socket.connectToServer(self.key)

        if socket.waitForConnected(500):
            socket.write(b"new_instance")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            logger.info(f"Another instance is already running (connected to '{self.key}')")
            return True

        QLocalServer.removeServer(self.key)

        self.server = QLocalServer()
        if not self.server.listen(self.key):
            logger.error(f"Failed to create local server: {self.server.errorString()}")
            return True

        self.server.newConnection.connect(self._handle_new_connection)
        logger.info(f"Single instance server started (key: '{self.key}')")
        return False

    # Event Handlers
    def _handle_new_connection(self):
        """Handle connection from a new instance trying to start."""
        connection = self.server.nextPendingConnection()
        if connection:
            if connection.waitForReadyRead(1000):
                message = connection.readAll().data().decode('utf-8', errors='ignore')
                logger.info(f"Received message from new instance: {message}")
                self.new_instance_detected.emit(message)
            connection.close()

    # Cleanup Methods
    def cleanup(self):
        """Clean up the server."""
        if self.server:
            self.server.close()
            QLocalServer.removeServer(self.key)
            logger.info("Single instance server cleaned up")

# ============================================================================
# Application Controller
# ============================================================================

class AppController(QObject):
    """Main application controller managing system tray and screenshot functionality."""

    # Signals
    screenshot_triggered = pyqtSignal()
    pin_clipboard_triggered = pyqtSignal()

    def __init__(self, single_instance: SingleInstance):
        super().__init__()
        self.about_window = None
        self.tray_icon = None
        self.single_instance = single_instance

        self.screenshot_snapshots: List[SnapshotItem] = []
        self.actionbar = ActionBar()
        self.capture_overlay = CaptureOverlay()
        self.pinned_windows: List['PinnedOverlay'] = []

        self._setup_about_window()
        self._setup_tray()
        self._setup_hotkey()
        self._setup_single_instance_handler()

        self.screenshot_triggered.connect(self._prepare_fullscreen_capture)
        self.pin_clipboard_triggered.connect(self._pin_clipboard_image)

    # Initialization Methods
    def _setup_about_window(self):
        """Create the about window (hidden by default)."""
        self.about_window = MainWindow()

    def _setup_tray(self):
        """Create and configure system tray icon and menu."""
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("ShotNPin - Screenshot Tool")

        tray_menu = QMenu()
        tray_menu.addAction("Take Screenshot").triggered.connect(self._prepare_fullscreen_capture)
        tray_menu.addAction("&About").triggered.connect(self._show_about)
        tray_menu.addSeparator()
        tray_menu.addAction("&Exit").triggered.connect(self._quit_application)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_icon_activated)
        self.tray_icon.show()

        if self.tray_icon.isVisible():
            logger.info("System tray icon created and visible")
        else:
            logger.warning("System tray icon created but not visible, retrying...")
            QTimer.singleShot(500, self._ensure_tray_visible)

    def _ensure_tray_visible(self):
        """Ensure the tray icon is visible."""
        if self.tray_icon and not self.tray_icon.isVisible():
            logger.warning("Tray icon not visible, attempting to show again...")
            self.tray_icon.hide()
            QTimer.singleShot(100, lambda: self.tray_icon.show())
            QTimer.singleShot(300, self._final_tray_check)

    def _final_tray_check(self):
        """Final check for tray icon visibility."""
        if self.tray_icon:
            if self.tray_icon.isVisible():
                logger.info("Tray icon is now visible")
            else:
                logger.error("Failed to show tray icon after retries")
                if self.tray_icon.supportsMessages():
                    self.tray_icon.showMessage(
                        "ShotNPin",
                        f"Running in background. Use {GLOBAL_HOTKEY_CAP} to capture.",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000
                    )

    def _setup_hotkey(self):
        """Register global hotkey."""
        try:
            hotkeys = {
                GLOBAL_HOTKEY_CAP: lambda: self.screenshot_triggered.emit(),
                GLOBAL_HOTKEY_PIN: lambda: self.pin_clipboard_triggered.emit()
            }
            keyboard.GlobalHotKeys(hotkeys).start()
            logger.info(f"Registered global hotkeys: {', '.join(hotkeys.keys())}")
        except Exception as e:
            logger.error(f"Hotkey registration failed: {e}")
            if sys.platform == "darwin":
                logger.info("On macOS: Please grant Accessibility permissions in System Preferences > Security & Privacy > Privacy & Accessibility")
                QMessageBox.warning(
                    None,
                    "ShotNPin",
                    "Failed to register global hotkey.\nPlease grant Accessibility permissions in System Preferences > Privacy > Accessibility."
                )
            else:
                logger.info("You may need to run with administrator/root privileges for global hotkeys")

    def _setup_single_instance_handler(self):
        """Setup handler for when another instance tries to start."""
        self.single_instance.new_instance_detected.connect(
            lambda msg: self._show_about() if msg == "new_instance" else None
        )

    # Event Handlers
    def _tray_icon_activated(self, reason):
        """Handle tray icon activation (clicks)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._prepare_fullscreen_capture()

    def _show_about(self):
        """Show the about window."""
        if self.about_window:
            self.about_window.show()
            self.about_window.activateWindow()
            self.about_window.raise_()

    # Screenshot Methods
    def _prepare_fullscreen_capture(self):
        """Prepare fullscreen capture for user selection."""
        if self.capture_overlay and self.capture_overlay.isVisible():
            logger.debug("Capture already in progress, ignoring")
            return

        screens = QApplication.screens()
        if not screens:
            logger.error("No screen available for capture")
            return

        full_screen = self._capture_all_screens(screens)
        if full_screen and not full_screen.isNull():
            self.capture_overlay.new_capture(full_screen)
            self.capture_overlay.show()
            logger.info(f">>> [{self.capture_overlay.display_name}] OPENED")
        else:
            logger.error("Failed to capture full_screen")

    def _capture_all_screens(self, screens):
        """Capture all screens and combine them into a single pixmap."""
        if not screens:
            return None

        min_x, min_y, max_x, max_y = get_virtual_desktop_bounds(screens)
        virtual_width = max_x - min_x + 1
        virtual_height = max_y - min_y + 1

        logger.debug(f"Virtual desktop bounds: {min_x}, {min_y}, {virtual_width}x{virtual_height}")

        max_dpr = max(screen.devicePixelRatio() for screen in screens)

        combined_pixmap = QPixmap(int(virtual_width * max_dpr), int(virtual_height * max_dpr))
        combined_pixmap.fill(Qt.GlobalColor.transparent)
        combined_pixmap.setDevicePixelRatio(max_dpr)

        painter = QPainter(combined_pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        try:
            for screen in screens:
                screen_geometry = screen.geometry()
                screen_pixmap = screen.grabWindow(0)

                if not screen_pixmap.isNull():
                    x_offset = screen_geometry.left() - min_x
                    y_offset = screen_geometry.top() - min_y

                    if screen.devicePixelRatio() != max_dpr:
                        scaled_pixmap = screen_pixmap.scaled(
                            int(screen_geometry.width() * max_dpr),
                            int(screen_geometry.height() * max_dpr),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        scaled_pixmap.setDevicePixelRatio(max_dpr)
                        painter.drawPixmap(x_offset, y_offset, scaled_pixmap)
                    else:
                        painter.drawPixmap(x_offset, y_offset, screen_pixmap)
        except Exception as e:
            logger.error(f"Error in screen capture operation: {e}", exc_info=True)
            raise
        finally:
            painter.end()
        return combined_pixmap

    # Clipboard Methods
    def _pin_clipboard_image(self):
        """Pin image from clipboard as a PinnedImageWindow."""
        clipboard = QApplication.instance().clipboard()
        mime = clipboard.mimeData()
        if mime.hasImage():
            pixmap = clipboard.pixmap()
            if not pixmap or pixmap.isNull():
                logger.error("Clipboard image is null or invalid.")
                return

            pinned = PinnedOverlay(pixmap, position=QCursor.pos())
            pinned.show()

            self.pinned_windows.append(pinned)
            logger.info(f"Clipboard pinned to screen: {len(self.pinned_windows)}")
        else:
            logger.warning("No image found in clipboard to pin.")

    # Utility Methods
    def _add_to_screenshot_snapshots(self, screenshot: QPixmap, start_pos: Optional[QPoint] = None, end_pos: Optional[QPoint] = None):
        """Add screenshot to snapshots with size limit."""
        snapshot = SnapshotItem(
            screenshot=screenshot.copy(),
            start_pos=start_pos,
            end_pos=end_pos
        )
        self.screenshot_snapshots.append(snapshot)

        if len(self.screenshot_snapshots) > MAX_HISTORY:
            self.screenshot_snapshots.pop(0)

        logger.debug(f"Snapshots added: {len(self.screenshot_snapshots)}")

    # Application Lifecycle
    def _quit_application(self):
        """Quit the application and clean up all resources."""
        if self.capture_overlay:
            try:
                self.capture_overlay.close()
            except Exception as e:
                logger.debug(f"Error closing capture overlay: {e}")

        for pinned_window in self.pinned_windows[:]:
            try:
                pinned_window.close()
            except Exception as e:
                logger.debug(f"Error closing pinned window: {e}")

        if self.single_instance:
            self.single_instance.cleanup()

        logger.info("Application quitting")
        QApplication.quit()

# ============================================================================
# UI Classes
# ============================================================================

class FocusPreservingEventFilter(QObject):
    """Event filter to preserve focus on linked widgets when actionbar widgets gain focus."""
    
    def __init__(self, actionbar: "ActionBar"):
        super().__init__()
        self.actionbar = actionbar
    
    def eventFilter(self, obj, event):
        if event.type() == event.Type.MouseButtonRelease and self.actionbar.linked_widget:
            QTimer.singleShot(0, lambda: (
                self.actionbar.linked_widget.activateWindow(),
                self.actionbar.linked_widget.setFocus()
            ))
        return False

class ActionBar(QWidget):
    """Floating toolbar providing annotation controls and actions."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self.linked_widget: Optional["OverlayBase"] = None
        self.button_actions = []

        # Create event filter for focus preservation
        self.focus_filter = FocusPreservingEventFilter(self)

        self.font_size = DEFAULT_FONT_SIZE
        self.current_pen_color = DEFAULT_PEN_COLOR

        # Text input state
        self.text_input: Optional[QLineEdit] = None
        self.text_input_pos: Optional[QPoint] = None

        # Drawing state
        self.drawing = False
        self.last_point = QPoint()
        self.last_point_clamped = False
        self.draw_start_point = QPoint()
        self.preview_rect: Optional[QRect] = None
        self.preview_line: Optional[Tuple[QPoint, QPoint]] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TOOLBAR_MARGIN, TOOLBAR_MARGIN, TOOLBAR_MARGIN, TOOLBAR_MARGIN)
        layout.setSpacing(TOOLBAR_SPACING)

        self._setup_styles()
        self._init_buttons(layout)
        self.adjustSize()

    # Initialization Methods
    def _setup_styles(self):
        """Apply stylesheet to actionbar and its widgets."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {TOOLBAR_BG_COLOR};
                border-radius: 5px;
                border: 1px solid {BORDER_COLOR};
            }}
            QPushButton {{
                background-color: {BUTTON_BG_COLOR};
                color: white;
                border: 1px solid {BORDER_COLOR};
                border-radius: 3px;
                padding: 5px;
            }}
            QPushButton:hover {{
                background-color: {BUTTON_HOVER_COLOR};
            }}
            QPushButton:pressed, QPushButton:checked {{
                background-color: {BUTTON_ACTIVE_COLOR};
            }}
            QSlider::groove:horizontal {{
                border: 1px solid {BORDER_COLOR};
                height: 6px;
                background: {BUTTON_BG_COLOR};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {BUTTON_ACTIVE_COLOR};
                border: 1px solid {BORDER_COLOR};
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider {{
                min-width: 60px;
                max-width: 60px;
            }}
            QLabel {{
                color: white;
            }}
        """)

    def _init_buttons(self, layout: QHBoxLayout):
        """Create and add all actionbar buttons to the layout."""
        # Tool buttons
        tool_configs = [
            ("pen", "Pen Tool"),
            ("rectangle", "Rectangle Tool"),
            ("line", "Line Tool"),
            ("text", "Text Tool"),
        ]

        self.tool_buttons = []
        for idx, (mode, label) in enumerate(tool_configs, start=1):
            btn = self._create_button(
                icon_name=mode,
                tooltip=f"{label} ({idx})",
                callback=self._tool_button_handler,
                checkable=True
            )
            btn.setProperty("mode", mode)
            layout.addWidget(btn)
            self.tool_buttons.append(btn)
            self.button_actions.append(lambda b=btn: b.click())

        # Color picker button
        self.color_btn = self._create_button(tooltip=f"Choose Color ({len(self.button_actions) + 1})", callback=self._choose_color)
        self._update_color_button(self.current_pen_color)
        layout.addWidget(self.color_btn)
        self.button_actions.append(lambda: self.color_btn.click())

        # Pen width controls
        self.pen_width_label = QLabel()
        self.pen_width_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pen_width_label.setFixedWidth(24)
        layout.addWidget(self.pen_width_label)

        self.pen_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.pen_width_slider.setRange(1, 20)
        self.pen_width_slider.setFixedWidth(60)
        self.pen_width_slider.setSingleStep(1)
        self.pen_width_slider.valueChanged.connect(self.pen_width_label.setNum)
        self.pen_width_slider.setValue(DEFAULT_PEN_WIDTH)
        layout.addWidget(self.pen_width_slider)

        # Action buttons
        buttons_config = [
            ('undo', "Undo (Ctrl+Z)", lambda: self.linked_widget.undo_action()),
            ('redo', "Redo (Ctrl+Y)", lambda: self.linked_widget.redo_action()),
            ('copy', "Copy to Clipboard (Ctrl+C)", self._copy_to_clipboard),
            ('save', "Save to File (Ctrl+S)", self._save_to_file),
            ('pin', "Pin (Ctrl+T)", lambda: self.linked_widget.pin_to_screen()),
            ('close', "Close (Esc)", lambda: self.linked_widget.close()),
        ]

        self.undo_btn, self.redo_btn, self.copy_btn, self.save_btn, self.pin_btn, self.close_btn = [
            self._create_button(icon, tooltip, callback) for icon, tooltip, callback in buttons_config
        ]

        for btn in [self.undo_btn, self.redo_btn, self.copy_btn, self.save_btn, self.pin_btn, self.close_btn]:
            layout.addWidget(btn)

        # Install event filter on all child widgets to prevent focus stealing
        for child in self.findChildren(QWidget):
            child.installEventFilter(self.focus_filter)

    def _create_button(
        self,
        icon_name: Optional[str] = None,
        tooltip: str = "",
        callback: Optional[Callable[[], None]] = None,
        checkable: bool = False
    ) -> QPushButton:
        """Helper method to create a toolbar button."""
        btn = QPushButton()
        btn.setToolTip(tooltip)
        if icon_name is not None:
            btn.setIcon(create_svg_icon(SVG_ICONS[icon_name]))
        if callback:
            btn.clicked.connect(callback)
        if checkable:
            btn.setCheckable(True)
            btn.setChecked(False)
        return btn

    # Tool Management
    def _tool_button_handler(self):
        """Handler for drawing tool buttons to ensure mutual exclusion."""
        sender = self.sender()
        if sender.isChecked():
            self.deactivate_draw_tools(exclude_btn=sender)
        else:
            sender.setChecked(False)

    def _get_active_draw_mode(self) -> Optional[str]:
        """Get the currently active drawing mode."""
        for btn in self.tool_buttons:
            if btn.isChecked():
                return btn.property("mode")
        return None

    def is_any_draw_tool_active(self) -> bool:
        """Check if any of the drawing tool buttons are pressed."""
        return any(btn.isChecked() for btn in self.tool_buttons)

    def deactivate_draw_tools(self, exclude_btn: Optional[QPushButton] = None):
        """Deactivate all drawing tool buttons except the excluded one."""
        for btn in self.tool_buttons:
            if btn is not exclude_btn:
                btn.setChecked(False)

    # UI Management
    def popup_for(self, linked: "OverlayBase"):
        """Show actionbar for a specific widget."""
        logger.info(f"[ActionBar] Showing -> {linked.display_name}")
        self.linked_widget = linked

        if isinstance(linked, PinnedOverlay):
            self.pin_btn.setVisible(False)
            self.pin_btn.setEnabled(False)
            self.setParent(None)
        else:
            self.pin_btn.setVisible(True)
            self.pin_btn.setEnabled(True)
            self.setParent(linked)

        self._position()
        self.show()

    def dismiss(self):
        """Hide the actionbar."""
        self.deactivate_draw_tools()
        self.hide()

    def _position(self):
        """Position actionbar at bottom right of selection area."""
        if isinstance(self.linked_widget, PinnedOverlay):
            x = self.linked_widget.width() - self.width()
            y = self.linked_widget.height() + TOOLBAR_MARGIN
            self.move(self.linked_widget.mapToGlobal(QPoint(x, y)))
        else:
            selection_rect = self.linked_widget.content_rect
            x = selection_rect.right() - self.width() + SELECTION_BORDER_WIDTH
            y = selection_rect.bottom() + TOOLBAR_MARGIN + SELECTION_BORDER_WIDTH
            x = max(0, min(x, self.linked_widget.width() - self.width()))
            y = min(y, self.linked_widget.height() - self.height())
            self.move(x, y)

    # Color and Style Methods
    def _choose_color(self):
        """Open color picker dialog."""
        color = QColorDialog.getColor(self.current_pen_color, self.linked_widget, "Choose Pen Color")
        if color.isValid():
            self.current_pen_color = color
            self._update_color_button(color)

    def _update_color_button(self, color: QColor):
        """Update color button appearance based on selected color."""
        text_color = 'white' if color.lightness() < 128 else 'black'
        self.color_btn.setStyleSheet(
            f"background-color: {color.name()}; "
            f"color: {text_color}; "
            f"border: 1px solid #555; "
            f"border-radius: 3px;"
        )

    # Text Annotation Methods
    def _add_text_annotation(self, pos: QPoint):
        """Add text annotation at the given position."""
        if self.text_input:
            self._finalize_text_input()

        self.text_input_pos = pos
        self.text_input = QLineEdit(self.linked_widget)

        font = QFont("Arial", self.font_size)
        font.setBold(True)
        self.text_input.setFont(font)

        brightness = self.current_pen_color.lightness()
        bg_color = "rgba(255, 255, 255, 180)" if brightness < 128 else "rgba(0, 0, 0, 180)"
        text_color = self.current_pen_color.name()

        self.text_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                padding: 0px;
                margin: 0px;
                font-weight: bold;
            }}
        """)

        self.text_input.setTextMargins(0, 0, 0, 0)
        self.text_input.setContentsMargins(0, 0, 0, 0)
        self.text_input.setMinimumWidth(100)
        self.text_input.adjustSize()
        self.text_input.move(pos.x(), pos.y())
        self.text_input.show()
        self.text_input.setFocus()

        self.text_input.returnPressed.connect(lambda: self._finalize_text_input(font))
        self.text_input.editingFinished.connect(lambda: self._finalize_text_input(font))

    def _finalize_text_input(self, font: Optional[QFont] = None):
        """Finalize the text input and draw it on the screenshot."""
        if not self.text_input or not self.text_input_pos:
            return

        text = self.text_input.text()

        if text:
            painter = QPainter(self.linked_widget.base_pixmap)
            try:
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                font.setPointSize(self.font_size)
                painter.setFont(font)
                painter.setPen(self.current_pen_color)

                content_margins = self.text_input.contentsMargins()
                x_offset = content_margins.left() if content_margins.left() > 0 else 2
                y_offset = content_margins.top() if content_margins.top() > 0 else 1

                pos = self._window_to_pixmap_pos(self.text_input_pos)

                text_rect = QRect(pos.x() + x_offset, pos.y() + y_offset, 1000, 100)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
            except Exception as e:
                logger.error(f"Error in text annotation: {e}", exc_info=True)
                raise
            finally:
                painter.end()

            self.linked_widget._save_annotation_state()
            self.linked_widget.update()

        self.text_input.deleteLater()
        self.text_input = None
        self.text_input_pos = None

    # Drawing and Preview Methods
    def _paint_shape_preview(self, painter: QPainter):
        """Paint preview for rectangle/line drawing modes."""
        if not self.linked_widget:
            return

        if self.preview_rect and self._get_active_draw_mode() == "rectangle":
            painter.setPen(self._create_drawing_pen(Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
            painter.setBrush(QColor(self.current_pen_color.red(), self.current_pen_color.green(), self.current_pen_color.blue(), 50))
            painter.drawRect(self.preview_rect)

        if self.preview_line and self._get_active_draw_mode() == "line":
            painter.setPen(self._create_drawing_pen())
            painter.drawLine(self.preview_line[0], self.preview_line[1])

    def _create_drawing_pen(self, cap_style=Qt.PenCapStyle.RoundCap, join_style=Qt.PenJoinStyle.RoundJoin) -> QPen:
        """Create a standard pen for drawing operations."""
        return QPen(
            self.current_pen_color,
            self.pen_width_slider.value(),
            Qt.PenStyle.SolidLine,
            cap_style,
            join_style
        )

    # Coordinate Conversion Methods
    def _window_to_pixmap_pos(self, pos: QPoint) -> QPoint:
        """Convert window coordinates to pixmap coordinates."""
        if hasattr(self.linked_widget, 'glow_size'):
            return QPoint(pos.x() - self.linked_widget.glow_size, pos.y() - self.linked_widget.glow_size)
        return pos

    def _clamp_pos_to_only_pixmap(self, pos: QPoint, for_container_window: bool = True) -> QPoint:
        """Clamp position to be within the pixmap bounds."""
        if not self.linked_widget:
            return pos

        content_rect = self.linked_widget.content_rect

        pen_half_width = self.pen_width_slider.value() // 2

        clamped_pos = QPoint(
            int(max(content_rect.left() + 1 + pen_half_width, min(pos.x(), content_rect.right() - 1 - pen_half_width))),
            int(max(content_rect.top() + 1 + pen_half_width, min(pos.y(), content_rect.bottom() - 1 - pen_half_width)))
        )

        if for_container_window:
            return clamped_pos
        else:
            return self._window_to_pixmap_pos(clamped_pos)

    def handle_key_press(self, event):
        """Handle key press events for shortcuts."""
        if not self.isVisible():
            return False

        key = event.key()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            shortcuts = {
                Qt.Key.Key_Z: self.linked_widget.undo_action,
                Qt.Key.Key_Y: self.linked_widget.redo_action,
                Qt.Key.Key_S: self._save_to_file,
                Qt.Key.Key_C: self._copy_to_clipboard,
                Qt.Key.Key_T: self.pin_btn.click,
            }
            if key in shortcuts:
                shortcuts[key]()
                return True
            return False

        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            button_index = key - Qt.Key.Key_1
            if button_index < len(self.button_actions):
                self.button_actions[button_index]()
            return True

    def handle_mouse_press(self, event):
        """Start drawing or place text annotation based on draw mode."""
        if not self.linked_widget or not self.is_any_draw_tool_active():
            return False

        pos = event.pos()
        if self._get_active_draw_mode() == "text":
            self._add_text_annotation(pos)
        else:
            self.drawing = True
            self.last_point = pos
            self.last_point_clamped = False
            self.draw_start_point = pos
        return True

    def handle_mouse_move(self, event):
        """Handle mouse move for drawing preview."""
        if not self.linked_widget or not self.is_any_draw_tool_active():
            return False

        pos = event.pos()
        if self.drawing and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)):
            draw_mode = self._get_active_draw_mode()

            if draw_mode == "pen":
                if self.last_point_clamped:
                    return

                content_rect = self.linked_widget.content_rect
                pen_half_width = self.pen_width_slider.value() // 2
                draw_rect = content_rect.adjusted(pen_half_width, pen_half_width, -pen_half_width, -pen_half_width)
                
                if content_rect and not draw_rect.contains(event.pos()):
                    pos = self._clamp_pos_to_only_pixmap(pos)
                    self.last_point_clamped = True

                pixmap_last_point = self._window_to_pixmap_pos(self.last_point)
                pixmap_pos = self._window_to_pixmap_pos(pos)

                painter = QPainter(self.linked_widget.base_pixmap)
                try:
                    pen = self._create_drawing_pen()
                    painter.setPen(pen)
                    painter.drawLine(pixmap_last_point, pixmap_pos)
                except Exception as e:
                    logger.error(f"Error in pen drawing: {e}", exc_info=True)
                    raise
                finally:
                    painter.end()
                self.last_point = pos
            elif draw_mode == "rectangle":
                clamped_pos = self._clamp_pos_to_only_pixmap(pos)
                self.preview_rect = QRect(self.draw_start_point, clamped_pos).normalized()
            elif draw_mode == "line":
                clamped_pos = self._clamp_pos_to_only_pixmap(pos)
                self.preview_line = (self.draw_start_point, clamped_pos)
            self.linked_widget.update()
        return True

    def handle_wheel_event(self, event):
        """Adjust font size when scrolling with text input active."""
        if not self.linked_widget or not self.is_any_draw_tool_active():
            return

        if self.text_input and self.text_input.isVisible():
            delta = event.angleDelta().y()
            if delta > 0:
                self.font_size = min(72, self.font_size + 2)
            else:
                self.font_size = max(8, self.font_size - 2)

            font = self.text_input.font()
            font.setPointSize(self.font_size)
            self.text_input.setFont(font)
            self.text_input.adjustSize()

    # Drawing Finalization
    def _finalize_sharp(self, end_point: QPoint):
        """Draw the shape to the pixmap based on current draw mode."""
        painter = QPainter(self.linked_widget.base_pixmap)
        try:
            draw_mode = self._get_active_draw_mode()

            if draw_mode == "rectangle":
                pen = self._create_drawing_pen(Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
                painter.setPen(pen)
                painter.setBrush(QColor(
                    self.current_pen_color.red(),
                    self.current_pen_color.green(),
                    self.current_pen_color.blue(),
                    50
                ))
                pixmap_start_point = self._clamp_pos_to_only_pixmap(self.draw_start_point, False)
                clamped_end_point = self._clamp_pos_to_only_pixmap(end_point, False)
                rect = QRect(pixmap_start_point, clamped_end_point).normalized()
                painter.drawRect(rect)
                self.preview_rect = None
            elif draw_mode == "line":
                pen = self._create_drawing_pen()
                painter.setPen(pen)
                pixmap_start_point = self._clamp_pos_to_only_pixmap(self.draw_start_point, False)
                clamped_end_point = self._clamp_pos_to_only_pixmap(end_point, False)
                painter.drawLine(pixmap_start_point, clamped_end_point)
                self.preview_line = None
        except Exception as e:
            logger.error(f"Error in shape finalization: {e}", exc_info=True)
            raise
        finally:
            painter.end()

        self.linked_widget._save_annotation_state()
        self.linked_widget.update()

    # Export Methods
    def _save_to_file(self):
        """Save the current selection to a file."""
        cropped, _ = self.linked_widget._get_content_for_export()
        self.linked_widget.close()
        if cropped:
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                "Save Screenshot",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;All Files (*)"
            )
            if file_path:
                if cropped.save(file_path):
                    logger.info(f"Screenshot saved to {file_path}")
                else:
                    logger.error(f"Failed to save screenshot to {file_path}")

    def _copy_to_clipboard(self):
        """Copy the current selection to clipboard."""
        cropped, _ = self.linked_widget._get_content_for_export()
        self.linked_widget.close()
        if cropped:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setPixmap(cropped)
                logger.info("Screenshot copied to clipboard")
            else:
                logger.error("Clipboard not available")

class OverlayBase(QWidget):
    """Base class for overlay widgets with annotation."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.setMouseTracking(True)

        self.display_id = 0
        self.base_pixmap: Optional[QPixmap] = None
        self.hint_label = None
        self.annotation_states: List[AnnotationState] = []

        # Dragging state
        self.dragging = False
        self.drag_offset = QPoint()

        # Resizing state
        self.resizing = False
        self.resize_edge: Optional[str] = None
        self.resize_handle_size = RESIZE_HANDLE_SIZE

        QShortcut(QKeySequence("Esc"), self).activated.connect(self._handle_esc_shortcut)

    # Properties
    @property
    def content_rect(self) -> Optional[QRect]:
        """Get the current selection rectangle. Override in subclasses if applicable."""
        return None

    @property
    def display_name(self):
        """Get display name for logging."""
        return f"{type(self).__name__[:-7]} #{self.display_id}"

    # Cursor Management
    def _update_cursor(self, pos: QPoint):
        """Update cursor based on position and current state."""
        pressed = QApplication.mouseButtons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)

        resize_edge = self._get_resize_edge(pos)
        if resize_edge:
            self.setCursor(self._get_resize_cursor(resize_edge))
        elif pressed and (self.dragging or self.resizing):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif get_actionbar().is_any_draw_tool_active():
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _get_resize_edge(self, pos: QPoint) -> Optional[str]:
        """Detect which edge/corner of the selection is under the cursor."""
        margin = self.resize_handle_size
        rect = self.content_rect
        if rect is None:
            return None
        expanded = rect.adjusted(-margin, -margin, margin, margin)
        if not expanded.contains(pos):
            return None

        x, y = pos.x(), pos.y()
        at_left = abs(x - rect.left()) <= margin
        at_right = abs(x - rect.right()) <= margin
        at_top = abs(y - rect.top()) <= margin
        at_bottom = abs(y - rect.bottom()) <= margin

        # Check corners first (more specific)
        if at_left and at_top:
            return 'top-left'
        if at_right and at_top:
            return 'top-right'
        if at_left and at_bottom:
            return 'bottom-left'
        if at_right and at_bottom:
            return 'bottom-right'

        # Check edges
        if at_top:
            return 'top'
        if at_bottom:
            return 'bottom'
        if at_left:
            return 'left'
        if at_right:
            return 'right'

        return None

    def _get_resize_cursor(self, edge: str) -> Qt.CursorShape:
        """Get the appropriate cursor shape for a resize edge."""
        cursor_map = {
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
        }
        return cursor_map.get(edge, Qt.CursorShape.ArrowCursor)

    # Abstract Methods (must be implemented by subclasses)
    def _apply_resize(self, mouse_x, mouse_y, keep_aspect=False):
        """Apply resize transformation. Must be implemented by subclasses."""
        raise NotImplementedError

    def _get_content_for_export(self):
        """Get pixmap for export (save/copy). Must be implemented by subclasses."""
        raise NotImplementedError

    def pin_to_screen(self):
        """Pin content to screen. Must be implemented by subclasses."""
        raise NotImplementedError

    # Event Handlers
    def keyPressEvent(self, event):
        """Handle key press events."""
        get_actionbar().handle_key_press(event)

    def mousePressEvent(self, event):
        """Handle mouse press events."""
        pos = event.pos()
        self._update_cursor(pos)
        resize_edge = self._get_resize_edge(pos)

        if resize_edge:
            self.resizing = True
            self.resize_edge = resize_edge
        else:
            if get_actionbar().handle_mouse_press(event):
                return
            self.dragging = True
            if isinstance(self, PinnedOverlay):
                self.drag_offset = pos
            else:
                self.drag_offset = pos - self.content_rect.topLeft()

    def mouseMoveEvent(self, event):
        """Handle mouse move events."""
        self._update_cursor(event.pos())
        actionbar = get_actionbar()

        if self.dragging:
            new_top_left = event.pos() - self.drag_offset
            if isinstance(self, PinnedOverlay):
                self.move(self.mapToGlobal(new_top_left))
            else:
                self._move_selection(new_top_left)
            actionbar._position()
            return
        elif self.resizing:
            keep_aspect = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._apply_resize(event.pos().x(), event.pos().y(), keep_aspect)
            actionbar._position()

        actionbar.handle_mouse_move(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release events."""
        self._update_cursor(event.pos())
        actionbar = get_actionbar()

        if actionbar.drawing:
            actionbar._finalize_sharp(event.pos())
            actionbar.drawing = False
        elif self.dragging:
            self.dragging = False
        elif self.resizing:
            self.resizing = False
            self.resize_edge = None
            self._save_annotation_state()

    def _handle_esc_shortcut(self):
        """Handle Escape key shortcut."""
        actionbar = get_actionbar()
        if actionbar.text_input:
            actionbar.text_input.deleteLater()
            actionbar.text_input = None
            actionbar.text_input_pos = None
            return

        if actionbar.is_any_draw_tool_active():
            actionbar.deactivate_draw_tools()
        else:
            self.close()

    # Undo/Redo System
    def _init_annotation_states(self):
        """Initialize annotation states for undo/redo functionality."""
        self.annotation_states = []
        self.undo_redo_index = -1

    def _save_annotation_state(self):
        """Save current annotation state to states list for undo/redo."""
        # Remove any states after current index (for redo)
        self.annotation_states = self.annotation_states[:self.undo_redo_index + 1]

        # Add new state
        cropped, selection_rect = self._get_content_for_export()
        state = AnnotationState(
            screenshot=cropped.copy(),
            selection_rect=selection_rect
        )
        self.annotation_states.append(state)
        self.undo_redo_index += 1

        if len(self.annotation_states) > MAX_HISTORY:
            self.annotation_states.pop(0)
            self.undo_redo_index -= 1

        logger.debug(f"[{self.display_name}] Saved annotation state: {self.undo_redo_index + 1}")

    def undo_action(self):
        """Undo last annotation."""
        if self.undo_redo_index > 0:
            self.undo_redo_index -= 1
            self._restore_annotation_state(self.undo_redo_index)
            self.update()

    def redo_action(self):
        """Redo annotation."""
        if self.undo_redo_index < len(self.annotation_states) - 1:
            self.undo_redo_index += 1
            self._restore_annotation_state(self.undo_redo_index)
            self.update()

    def _restore_annotation_state(self, index: int):
        """Restore annotation state from index."""
        logger.debug(f"[{self.display_name}] Restoring state {index + 1} of {len(self.annotation_states)}")
        state = self.annotation_states[index]
        state_pixmap = state.screenshot
        selection_rect = state.selection_rect

        if isinstance(self, PinnedOverlay):
            self.base_pixmap = state_pixmap.copy()
            self._update_window_size_from_pixmap()

            actionbar = get_actionbar()
            if actionbar.isVisible() and actionbar.linked_widget == self:
                actionbar._position()
        else:
            painter = QPainter(self.base_pixmap)
            try:
                painter.drawPixmap(selection_rect, state_pixmap, state_pixmap.rect())
            except Exception as e:
                logger.error(f"Error in restoring annotation state: {e}", exc_info=True)
                raise
            finally:
                painter.end()

    # Hint and UI Methods
    def _show_hint(self, message: str, duration: int = 1000):
        """Show a temporary hint message overlay on the screen."""
        if self.hint_label is None:
            self.hint_label = QLabel(message, self)
            self.hint_label.setStyleSheet(
                "background-color: rgba(0, 0, 0, 180); "
                "color: white; "
                "padding: 10px 20px; "
                "border-radius: 5px; "
                "font-size: 14px;"
            )
            self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.hint_label.setText(message)

        self.hint_label.adjustSize()
        x = (self.width() - self.hint_label.width()) // 2
        y = (self.height() - self.hint_label.height()) // 2
        self.hint_label.move(x, y)
        self.hint_label.show()

        QTimer.singleShot(duration, self.hint_label.hide)

    def closeEvent(self, event):
        """Clean up actionbar and release resources when closing."""
        get_actionbar().hide()
        self.annotation_states.clear()
        self.base_pixmap = None
        logger.info(f"<<< [{self.display_name}] CLOSED")

class CaptureOverlay(OverlayBase):
    """Fullscreen overlay for selecting and annotating screenshot areas."""

    def __init__(self):
        super().__init__()

        screens = QApplication.screens()
        if screens:
            min_x, min_y, max_x, max_y = get_virtual_desktop_bounds(screens)
            virtual_width = max_x - min_x + 1
            virtual_height = max_y - min_y + 1
            self.setGeometry(min_x, min_y, virtual_width, virtual_height)
            logger.debug(f"CaptureOverlay geometry set to virtual desktop: {min_x}, {min_y}, {virtual_width}x{virtual_height}")
        else:
            screen = QApplication.primaryScreen()
            if screen:
                full_geometry = screen.geometry()
                self.setGeometry(full_geometry)

        self.setCursor(Qt.CursorShape.CrossCursor)

    # Initialization Methods
    def new_capture(self, full_screen: QPixmap):
        """Initialize a new capture session."""
        self.display_id += 1
        self.base_pixmap = full_screen

        # Selection state
        self.start_pos: Optional[QPoint] = None
        self.end_pos: Optional[QPoint] = None
        self.selecting = False

        # Current position in screenshot snapshots
        self.current_snapshot_index: int = -1

    # Properties
    @property
    def content_rect(self) -> Optional[QRect]:
        """Get the current selection rectangle, normalized."""
        if self.start_pos is not None and self.end_pos is not None:
            return QRect(self.start_pos, self.end_pos).normalized()
        return None

    # Painting Methods
    def paintEvent(self, event):
        """Paint the capture overlay."""
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.base_pixmap)

        if self.content_rect is not None:
            self._paint_overlay_around_selection(painter, self.content_rect)
            self._paint_selection_border(painter, self.content_rect)
        else:
            painter.fillRect(self.rect(), OVERLAY_COLOR)

        get_actionbar()._paint_shape_preview(painter)

    def _paint_overlay_around_selection(self, painter: QPainter, selection_rect: QRect):
        """Paint dark overlay around the selection area."""
        overlay = OVERLAY_COLOR

        # Top area
        if selection_rect.top() > 0:
            painter.fillRect(0, 0, self.width(), selection_rect.top(), overlay)

        # Bottom area
        bottom_y = selection_rect.bottom() + 1
        remaining_height = self.height() - bottom_y
        if remaining_height > 0:
            painter.fillRect(0, bottom_y, self.width(), remaining_height, overlay)

        # Left area
        if selection_rect.left() > 0:
            painter.fillRect(0, selection_rect.top(), selection_rect.left(),
                           selection_rect.height(), overlay)

        # Right area
        if selection_rect.right() < self.width() - 1:
            painter.fillRect(selection_rect.right() + 1, selection_rect.top(),
                           self.width() - selection_rect.right() - 1, selection_rect.height(), overlay)

    def _paint_selection_border(self, painter: QPainter, selection_rect: QRect):
        """Paint the selection rectangle border."""
        border_width = SELECTION_BORDER_WIDTH if self.selecting else SELECTION_BORDER_WIDTH + 1
        pen = QPen(SELECTION_BORDER_COLOR, border_width, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)

        half = border_width // 2
        border_rect = selection_rect.adjusted(-half, -half, half, half)
        painter.drawRect(border_rect)

    # Event Handlers
    def keyPressEvent(self, event):
        """Handle key press events."""
        key = event.key()

        # Handle history navigation keys (< and >)
        if key == Qt.Key.Key_Comma:
            self._navigate_snapshots(-1)
            return
        elif key == Qt.Key.Key_Period:
            self._navigate_snapshots(1)
            return

        # Handle arrow keys for selection movement
        arrow_keys = [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]
        if key in arrow_keys and self.content_rect is not None:
            self._handle_arrow_key_movement(event)
            return

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.content_rect is None:
            self.selecting = True
            self.start_pos = event.pos()
            self.end_pos = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._update_cursor(event.pos())
        if self.selecting:
            self.end_pos = event.pos()
            self.update()
        else:
            super().mouseMoveEvent(event)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.selecting:
            self.selecting = False
            self.end_pos = event.pos()
            self._finalize_selection()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Only while cursor is not over the actionbar."""
        actionbar = get_actionbar()
        if not actionbar.geometry().contains(event.position().toPoint()):
            actionbar.handle_wheel_event(event)
        else:
            super().wheelEvent(event)

    # Selection Management
    def _apply_resize(self, mouse_x, mouse_y, keep_aspect=False):
        """Apply resize transformation based on current resize edge."""
        resize_operations = {
            'left': lambda: self.start_pos.setX(min(mouse_x, self.end_pos.x() - MIN_SIZE)),
            'right': lambda: self.end_pos.setX(max(mouse_x, self.start_pos.x() + MIN_SIZE)),
            'top': lambda: self.start_pos.setY(min(mouse_y, self.end_pos.y() - MIN_SIZE)),
            'bottom': lambda: self.end_pos.setY(max(mouse_y, self.start_pos.y() + MIN_SIZE)),
            'top-left': lambda: (
                self.start_pos.setX(min(mouse_x, self.end_pos.x() - MIN_SIZE)),
                self.start_pos.setY(min(mouse_y, self.end_pos.y() - MIN_SIZE))
            ),
            'top-right': lambda: (
                self.end_pos.setX(max(mouse_x, self.start_pos.x() + MIN_SIZE)),
                self.start_pos.setY(min(mouse_y, self.end_pos.y() - MIN_SIZE))
            ),
            'bottom-left': lambda: (
                self.start_pos.setX(min(mouse_x, self.end_pos.x() - MIN_SIZE)),
                self.end_pos.setY(max(mouse_y, self.start_pos.y() + MIN_SIZE))
            ),
            'bottom-right': lambda: (
                self.end_pos.setX(max(mouse_x, self.start_pos.x() + MIN_SIZE)),
                self.end_pos.setY(max(mouse_y, self.start_pos.y() + MIN_SIZE))
            ),
        }

        if self.resize_edge in resize_operations:
            resize_operations[self.resize_edge]()

    def _move_selection(self, new_pos: QPoint):
        """Move selection to a new position while maintaining its size."""
        delta_x = self.end_pos.x() - self.start_pos.x()
        delta_y = self.end_pos.y() - self.start_pos.y()

        # Clamp to screen boundaries
        new_x = max(0, min(new_pos.x(), self.width() - abs(delta_x)))
        new_y = max(0, min(new_pos.y(), self.height() - abs(delta_y)))

        # Update positions using deltas to preserve exact size
        self.start_pos = QPoint(new_x, new_y)
        self.end_pos = QPoint(new_x + delta_x, new_y + delta_y)

    def _finalize_selection(self):
        """Finalize selection and initialize actionbar with snapshot handling."""
        selection_rect = self.content_rect

        # Selection too small, clear it to allow new selection
        if selection_rect is None or selection_rect.width() <= MIN_SIZE or selection_rect.height() <= MIN_SIZE:
            self.start_pos = None
            self.end_pos = None
            self.update()
            return

        self.start_pos = selection_rect.topLeft()
        self.end_pos = selection_rect.bottomRight()
        self.update()

        actionbar = get_actionbar()
        actionbar.popup_for(self)

        self._init_annotation_states()
        self._save_annotation_state()

        get_app_controller()._add_to_screenshot_snapshots(
            self.base_pixmap,
            self.start_pos,
            self.end_pos
        )
        logger.debug(f"Added screenshot to snapshots with selection: {self.start_pos} -> {self.end_pos}")
        self.current_snapshot_index = -1

    def _handle_arrow_key_movement(self, event):
        """Handle arrow key movement of selection."""
        step = KEYBOARD_STEP_LARGE if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else KEYBOARD_STEP_SMALL

        key_to_delta = {
            Qt.Key.Key_Left: (-step, 0),
            Qt.Key.Key_Right: (step, 0),
            Qt.Key.Key_Up: (0, -step),
            Qt.Key.Key_Down: (0, step),
        }

        delta_x, delta_y = key_to_delta.get(event.key(), (0, 0))
        new_pos = self.start_pos + QPoint(delta_x, delta_y)

        self._move_selection(new_pos)
        get_actionbar()._position()
        self.update()

    # Snapshot Navigation
    def _find_current_snapshot_index(self, screenshot_snapshots):
        """Find the current snapshot index by checking stored index or comparing screenshot data."""
        if self.current_snapshot_index >= 0 and self.current_snapshot_index < len(screenshot_snapshots):
            return self.current_snapshot_index

        # Try to find by comparing screenshot data
        for i, snapshot in enumerate(screenshot_snapshots):
            if snapshot.screenshot.cacheKey() == self.base_pixmap.cacheKey():
                return i

        return len(screenshot_snapshots)

    def _navigate_snapshots(self, direction: int):
        """Navigate through screenshot snapshots."""
        screenshot_snapshots = get_app_controller().screenshot_snapshots

        if len(screenshot_snapshots) == 0:
            logger.debug("Cannot navigate: screenshot snapshots is empty")
            return

        current_index = self._find_current_snapshot_index(screenshot_snapshots)
        new_index = current_index + direction

        logger.debug(f"Navigating to screenshot index {new_index} from {current_index} in direction {direction}")

        if new_index < 0:
            self._show_hint("Already at first screenshot")
        elif new_index >= len(screenshot_snapshots):
            self._show_hint("Already at latest screenshot")
        else:
            snapshot = screenshot_snapshots[new_index]
            self._restore_selection(
                screenshot=snapshot.screenshot,
                start_pos=snapshot.start_pos,
                end_pos=snapshot.end_pos,
                reset_annotation=True
            )
            logger.debug(f"Navigated to screenshot {new_index} with selection: {self.start_pos} -> {self.end_pos}")
            self.update()
            self.current_snapshot_index = new_index

    def _restore_selection(self, screenshot, start_pos, end_pos, reset_annotation=True):
        """Restore screenshot selection and optional reset annotation states."""
        self.base_pixmap = screenshot.copy()
        self.start_pos = start_pos
        self.end_pos = end_pos

        if reset_annotation:
            self._init_annotation_states()
            self._save_annotation_state()

        if self.content_rect is not None:
            get_actionbar().popup_for(self)

    # Utility Methods
    def _scale_rect(self, rect: QRect) -> QRect:
        """Scale a rectangle by device pixel ratio for high DPI displays."""
        if self.base_pixmap.devicePixelRatio() <= 1.0:
            return rect
        return QRect(
            int(rect.x() * self.base_pixmap.devicePixelRatio()),
            int(rect.y() * self.base_pixmap.devicePixelRatio()),
            int(rect.width() * self.base_pixmap.devicePixelRatio()),
            int(rect.height() * self.base_pixmap.devicePixelRatio())
        )

    def _get_content_for_export(self) -> Tuple[Optional[QPixmap], Optional[QRect]]:
        """Get the cropped annotated screenshot from current selection."""
        result: Tuple[Optional[QPixmap], Optional[QRect]] = (None, None)
        selection_rect = self.content_rect
        if selection_rect is not None and selection_rect.width() > MIN_SIZE and selection_rect.height() > MIN_SIZE:
            scaled_rect = self._scale_rect(selection_rect)
            cropped = self.base_pixmap.copy(scaled_rect)
            cropped.setDevicePixelRatio(self.base_pixmap.devicePixelRatio())
            result = (cropped, selection_rect)
        return result

    def pin_to_screen(self):
        """Pin the current selection."""
        cropped, selection_rect = self._get_content_for_export()
        if cropped:
            pinned_window = PinnedOverlay(
                cropped,
                position=selection_rect.topLeft(),
                annotation_states=self.annotation_states,
                undo_redo_index=self.undo_redo_index
            )
            # Transfer annotation states reference
            self.annotation_states = []
            pinned_window.show()

            get_app_controller().pinned_windows.append(pinned_window)
            logger.info(f"Screenshot pinned to screen: {len(get_app_controller().pinned_windows)}")
        get_actionbar().dismiss()
        self.close()

class PinnedOverlay(OverlayBase):
    """Pinned window for displaying captured and annotated screenshots."""

    _instance_counter = 0

    def __init__(self, pixmap: QPixmap, position: Optional[QPoint] = None,
                 annotation_states: Optional[List[AnnotationState]] = None,
                 undo_redo_index: int = -1):
        super().__init__()

        PinnedOverlay._instance_counter += 1
        self.display_id = PinnedOverlay._instance_counter

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Store original pixmap for high-quality resizing
        self.original_pixmap = pixmap.copy()
        self.aspect_ratio = self.original_pixmap.width() / self.original_pixmap.height()

        self.base_pixmap = pixmap
        self.glow_size = max(offset for _, offset in GLOW_LAYERS)

        self._update_window_size_from_pixmap()
        self.initial_position = position

        # Transparency state
        self.opacity = 1.0
        self.setWindowOpacity(self.opacity)

        # Opacity label
        self.opacity_label = QLabel(self)
        self.opacity_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                border: 1px solid #0078d4;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        self.opacity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.opacity_label.hide()

        # Timer to hide opacity label
        self.opacity_timer = QTimer(self)
        self.opacity_timer.setSingleShot(True)
        self.opacity_timer.timeout.connect(self.opacity_label.hide)

        # Initialize annotation states
        if annotation_states:
            self.annotation_states = annotation_states
            self.undo_redo_index = undo_redo_index
            logger.info(f">>> [{self.display_name}] OPENED (restored {len(annotation_states)} states, index={undo_redo_index})")
        else:
            self._init_annotation_states()
            self._save_annotation_state()
            logger.info(f">>> [{self.display_name}] OPENED (new, saved initial state)")

        # Keyboard shortcuts
        QShortcut(QKeySequence("Space"), self).activated.connect(self._handle_space_shortcut)

    # Initialization Methods
    def showEvent(self, event):
        """Handle show event to position the window with glow effect adjustment."""
        super().showEvent(event)
        if self.initial_position:
            self.move(self.initial_position.x() - self.glow_size, self.initial_position.y() - self.glow_size)
            self.initial_position = None

    # Properties
    @property
    def content_rect(self) -> Optional[QRect]:
        """Get the content rectangle accounting for glow effect."""
        logical_width = int(self.base_pixmap.width() / self.base_pixmap.devicePixelRatio())
        logical_height = int(self.base_pixmap.height() / self.base_pixmap.devicePixelRatio())
        return QRect(self.glow_size, self.glow_size, logical_width, logical_height)

    # Window Management
    def _update_window_size_from_pixmap(self):
        """Update window size based on current base_pixmap dimensions plus glow."""
        content = self.content_rect
        self.setFixedSize(content.width() + 2 * self.glow_size,
                         content.height() + 2 * self.glow_size)

    def _handle_space_shortcut(self):
        """Handle space key to show/hide actionbar."""
        actionbar = get_actionbar()
        if actionbar.isVisible():
            actionbar.dismiss()
        else:
            actionbar.popup_for(self)

    # Painting Methods
    def paintEvent(self, event):
        """Paint the pinned overlay with glow effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Draw glow effect expanding outward from the pixmap
        for color, offset in GLOW_LAYERS:
            painter.setBrush(QBrush(color))
            glow_rect = self.content_rect.adjusted(-offset, -offset, offset, offset)
            painter.drawRect(glow_rect)

        # Draw the pixmap at the center
        painter.drawPixmap(self.glow_size, self.glow_size, self.base_pixmap)

        get_actionbar()._paint_shape_preview(painter)

    # Event Handlers
    def mouseDoubleClickEvent(self, event):
        """Close window on double click."""
        self.close()

    def wheelEvent(self, event):
        """Handle mouse wheel events to adjust window opacity/transparency."""
        delta = event.angleDelta().y()

        if delta > 0:
            self.opacity = min(1.0, self.opacity + 0.05)
        else:
            self.opacity = max(0.1, self.opacity - 0.05)

        self.setWindowOpacity(self.opacity)

        opacity_percent = int(self.opacity * 100)
        self.opacity_label.setText(f"{opacity_percent}%")
        self.opacity_label.adjustSize()

        margin = 10
        label_x = self.width() - self.opacity_label.width() - margin
        label_y = margin
        self.opacity_label.move(label_x, label_y)
        self.opacity_label.show()
        self.opacity_label.raise_()

        self.opacity_timer.start(1000)

    # Resize Methods
    def _calculate_new_size(self, mouse_x: int, mouse_y: int, keep_aspect: bool) -> Tuple[int, int, int, int]:
        """Calculate new size for resize operation."""
        content_x = mouse_x - self.glow_size
        content_y = mouse_y - self.glow_size

        current_width = int(self.base_pixmap.width() / self.base_pixmap.devicePixelRatio())
        current_height = int(self.base_pixmap.height() / self.base_pixmap.devicePixelRatio())

        new_width = current_width
        new_height = current_height

        if 'right' in self.resize_edge:
            new_width = max(MIN_SIZE, content_x)
        elif 'left' in self.resize_edge:
            new_width = max(MIN_SIZE, current_width - content_x)

        if 'bottom' in self.resize_edge:
            new_height = max(MIN_SIZE, content_y)
        elif 'top' in self.resize_edge:
            new_height = max(MIN_SIZE, current_height - content_y)

        if keep_aspect:
            if 'right' in self.resize_edge or 'left' in self.resize_edge:
                new_height = int(new_width / self.aspect_ratio)
            elif 'bottom' in self.resize_edge or 'top' in self.resize_edge:
                new_width = int(new_height * self.aspect_ratio)

        return current_width, current_height, new_width, new_height

    def _apply_resize(self, mouse_x: int, mouse_y: int, keep_aspect: bool = False):
        """Apply resize transformation to the pinned overlay's base_pixmap."""
        current_width, current_height, new_width, new_height = self._calculate_new_size(
            mouse_x, mouse_y, keep_aspect
        )

        if new_width == current_width and new_height == current_height:
            return

        # IMPORTANT: Always scale from original_pixmap to avoid quality degradation
        dpr = self.original_pixmap.devicePixelRatio()
        self.base_pixmap = self.original_pixmap.scaled(
            int(new_width * dpr),
            int(new_height * dpr),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.base_pixmap.setDevicePixelRatio(dpr)

        self._update_window_size_from_pixmap()

        # Adjust window position for top/left resizing to keep opposite corner fixed
        if 'left' in self.resize_edge or 'top' in self.resize_edge:
            current_pos = self.pos()
            new_x = current_pos.x() + (current_width - new_width) if 'left' in self.resize_edge else current_pos.x()
            new_y = current_pos.y() + (current_height - new_height) if 'top' in self.resize_edge else current_pos.y()
            self.move(new_x, new_y)

        self.update()

    # Abstract Method Implementations
    def _get_content_for_export(self) -> Tuple[Optional[QPixmap], Optional[QRect]]:
        """Get content for export (returns the base pixmap)."""
        return (self.base_pixmap, None)

    def pin_to_screen(self):
        """Pin content to screen (no-op for already pinned content)."""
        pass

    # Cleanup
    def closeEvent(self, event):
        """Clean up and remove from pinned windows list."""
        super().closeEvent(event)

        self.original_pixmap = None

        # Clean up timers
        opacity_timer = getattr(self, 'opacity_timer', None)
        if opacity_timer:
            opacity_timer.stop()

        pinned_list = get_app_controller().pinned_windows
        if self in pinned_list:
            pinned_list.remove(self)
        logger.info(f"Remaining pinned: {len(pinned_list)}")

class MainWindow(QMainWindow):
    """About dialog window showing application information."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowTitle("About - ShotNPin")
        self.setGeometry(100, 100, 300, 250)
        self._setup_ui()

    # Initialization Methods
    def _setup_ui(self):
        """Create and configure UI elements for about dialog."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Title
        title = QLabel("ShotNPin")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Hotkey info
        shortcut_label = QLabel("Shortcut: {}".format(GLOBAL_HOTKEY_CAP))
        shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcut_label.setStyleSheet("color: #0078d4; font-weight: bold;")
        layout.addWidget(shortcut_label)

        # Instructions
        info_text = (
            "1. Drag to select screenshot area\n"
            "2. Use toolbar to draw and annotate\n"
            "3. Adjust with drag or arrow keys\n"
            "4. Scroll wheel changes text font size\n"
            "5. Copy/Save/Pin with toolbar or hotkeys\n"
            "6. On pinned: scroll to change transparency\n"
            "7. Use , and . keys to navigate history"
        )
        info = QLabel(info_text)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: gray; margin-top: 10px; font-size: 11px;")
        layout.addWidget(info)

        layout.addStretch()

# ============================================================================
# Application Entry Point
# ============================================================================

def main():
    """Initialize and run the ShotNPin application."""
    app = QApplication(sys.argv)
    app.setApplicationName("ShotNPin")
    app.setWindowIcon(get_app_icon())

    single_instance = SingleInstance()
    if single_instance.is_already_running():
        logger.info("Application startup blocked - another instance is already running")
        sys.exit(0)

    app.setQuitOnLastWindowClosed(False)

    controller = AppController(single_instance)
    app.controller = controller

    sys.exit(app.exec())

if __name__ == "__main__":
    main()