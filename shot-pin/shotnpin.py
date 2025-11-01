#!/usr/bin/env python3
"""
ShotNPin - Simple screenshot, annotation, and pinning tool

A lightweight application for capturing, annotating, and pinning screenshots.
"""
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Callable

from pynput import keyboard
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QByteArray, pyqtSignal, QObject
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QShortcut, QKeySequence, QCursor, QIcon, QFont
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QColorDialog,
    QSlider, QHBoxLayout, QFileDialog, QLineEdit, QSystemTrayIcon, QMenu, QMessageBox
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

# Dimensions & Sizes
GLOW_SIZE = 5
RESIZE_HANDLE_SIZE = 8
MIN_SELECTION_SIZE = 20
MIN_VALID_RECT = 10
ICON_SIZE = 24
TOOLBAR_MARGIN = 5
TOOLBAR_SPACING = 3
SELECTION_BORDER_WIDTH = 3

# Drawing Defaults
DEFAULT_PEN_WIDTH = 2
DEFAULT_PEN_COLOR = QColor(255, 0, 0)
DEFAULT_FONT_SIZE = 16
MAX_HISTORY = 20

# Keyboard
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

ICON_FILENAME = "icons8-screenshot-100.png"

# ============================================================================
# SVG Icons
# ============================================================================

# Icon path data for toolbar buttons
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


def create_svg_icon(path_data: str, color: str = "#ffffff", size: int = ICON_SIZE) -> QIcon:
    """
    Create a QIcon from SVG path data.

    Args:
        path_data: SVG path definition
        color: Stroke color (hex format)
        size: Icon size in pixels

    Returns:
        QIcon object rendered from SVG
    """
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
    """
    Get the application icon with correct path resolution.
    """
    icon_path = str(Path(__file__).parent / ICON_FILENAME)
    return QIcon(icon_path)

def get_app_controller():
    """
    Safely get the global AppController from QApplication instance.
    """
    app = QApplication.instance()
    return getattr(app, 'controller', None)

def get_actionbar() -> Optional["ActionBar"]:
    """
    Safely get the shared global toolbar from the AppController.
    """
    controller = get_app_controller()
    return getattr(controller, 'toolbar', None)

def get_virtual_desktop_bounds(screens) -> Tuple[int, int, int, int]:
    """
    Calculate the virtual desktop bounds from multiple screens.

    Args:
        screens: List of QScreen objects

    Returns:
        Tuple of (min_x, min_y, max_x, max_y) representing the virtual desktop bounds
    """
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
    """
    Uses QLocalServer/QLocalSocket for inter-process communication.
    """

    # Signal emitted when a new instance tries to start
    new_instance_detected = pyqtSignal(str)

    def __init__(self, key: str = 'shotnpin_single_instance'):
        """
        Initialize single instance checker.
        """
        super().__init__()
        self.key = key
        self.server = None

    def is_already_running(self) -> bool:
        """
        Check if another instance is already running.
        """
        # Try to connect to existing instance
        socket = QLocalSocket()
        socket.connectToServer(self.key)

        if socket.waitForConnected(500):
            # Another instance is running, send a message
            socket.write(b"new_instance")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            logger.info(f"Another instance is already running (connected to '{self.key}')")
            return True

        # First remove any stale server (from crashed previous instance)
        QLocalServer.removeServer(self.key)

        self.server = QLocalServer()
        if not self.server.listen(self.key):
            logger.error(f"Failed to create local server: {self.server.errorString()}")
            return True  # Assume another instance is running to be safe

        # Connect signal to handle new instances trying to connect
        self.server.newConnection.connect(self._handle_new_connection)
        logger.info(f"Single instance server started (key: '{self.key}')")
        return False

    def _handle_new_connection(self):
        """Handle connection from a new instance trying to start."""
        connection = self.server.nextPendingConnection()
        if connection:
            if connection.waitForReadyRead(1000):
                message = connection.readAll().data().decode('utf-8', errors='ignore')
                logger.info(f"Received message from new instance: {message}")
                self.new_instance_detected.emit(message)
            connection.close()

    def _cleanup(self):
        """Clean up the server."""
        if self.server:
            self.server.close()
            QLocalServer.removeServer(self.key)
            logger.info("Single instance server cleaned up")


# ============================================================================
# Application Controller
# ============================================================================


class AppController(QObject):
    """
    Main application controller managing system tray and screenshot functionality.

    Handles all application-level logic including tray menu, screenshot capture,
    global hotkey registration, single instance management, and application lifecycle.
    """

    # Signal for thread-safe
    screenshot_triggered = pyqtSignal()
    pin_clipboard_triggered = pyqtSignal()

    def __init__(self, single_instance: SingleInstance):
        super().__init__()
        self.about_window = None
        self.tray_icon = None
        self.single_instance = single_instance

        # Global screenshot snapshots with state
        self.screenshot_snapshots: List[dict] = []  # Each item: {'screenshot': QPixmap, 'start_pos': QPoint, 'end_pos': QPoint}

        self.toolbar = ActionBar()

        # Managed window references
        self.capture_overlay = CaptureOverlay()
        self.pinned_windows: List['PinnedOverlay'] = []

        self._setup_about_window()
        self._setup_tray()
        self._setup_hotkey()
        self._setup_single_instance_handler()

        # Connect signals to slots
        self.screenshot_triggered.connect(self.prepare_fullscreen_capture)
        self.pin_clipboard_triggered.connect(self.pin_clipboard_image)

    def pin_clipboard_image(self):
        """Pin image from clipboard as a PinnedImageWindow."""
        app = QApplication.instance()
        clipboard = app.clipboard()
        mime = clipboard.mimeData()
        if mime.hasImage():
            pixmap = clipboard.pixmap()
            if not pixmap or pixmap.isNull():
                logger.error("Clipboard image is null or invalid.")
                return

            pinned = PinnedOverlay(
                pixmap,
                position=QCursor.pos(),
                selection_rect=QRect(0, 0, pixmap.width(), pixmap.height()),
            )
            pinned.show()

            self.pinned_windows.append(pinned)
            logger.info(f"Clipboard pinned to screen. Total pinned: {len(self.pinned_windows)}")
        else:
            logger.warning("No image found in clipboard to pin.")

    def _setup_about_window(self):
        """Create the about window (hidden by default)."""
        self.about_window = MainWindow()

    def _setup_tray(self):
        """Create and configure system tray icon and menu."""
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip("ShotNPin - Screenshot Tool")

        # Create tray menu
        tray_menu = QMenu()

        # Take Screenshot action
        screenshot_action = tray_menu.addAction("Take Screenshot")
        screenshot_action.triggered.connect(self.prepare_fullscreen_capture)

        # About action
        about_action = tray_menu.addAction("&About")
        about_action.triggered.connect(self.show_about)

        tray_menu.addSeparator()

        # Exit action
        exit_action = tray_menu.addAction("&Exit")
        exit_action.triggered.connect(self.quit_application)

        self.tray_icon.setContextMenu(tray_menu)

        # Double-click to take screenshot
        self.tray_icon.activated.connect(self.tray_icon_activated)

        # Show the tray icon
        self.tray_icon.show()

        # Verify the icon is visible
        if self.tray_icon.isVisible():
            logger.info("System tray icon created and visible")
        else:
            logger.warning("System tray icon created but not visible, retrying...")
            # Try again after a short delay
            QTimer.singleShot(500, self._ensure_tray_visible)

    def _retry_tray_setup(self):
        """Retry setting up the system tray if it wasn't available initially."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("System tray now available, setting up...")
            self._setup_tray()
        else:
            logger.error("System tray still not available, giving up")
            QMessageBox.warning(
                None,
                "ShotNPin",
                "System tray is not available.\nThe application will still work via the global hotkey."
            )

    def _ensure_tray_visible(self):
        """Ensure the tray icon is visible."""
        if self.tray_icon and not self.tray_icon.isVisible():
            logger.warning("Tray icon not visible, attempting to show again...")
            self.tray_icon.hide()  # Hide first
            QTimer.singleShot(100, lambda: self.tray_icon.show())  # Then show

            # Final check
            QTimer.singleShot(300, self._final_tray_check)

    def _final_tray_check(self):
        """Final check for tray icon visibility."""
        if self.tray_icon:
            if self.tray_icon.isVisible():
                logger.info("Tray icon is now visible")
            else:
                logger.error("Failed to show tray icon after retries")
                # Show a notification message
                if self.tray_icon.supportsMessages():
                    self.tray_icon.showMessage(
                        "ShotNPin",
                        f"Running in background. Use {GLOBAL_HOTKEY_CAP} to capture.",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000
                    )

    def tray_icon_activated(self, reason):
        """Handle tray icon activation (clicks)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.prepare_fullscreen_capture()

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
            if sys.platform == "darwin":  # macOS
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
            lambda msg: self.show_about() if msg == "new_instance" else None
        )

    def show_about(self):
        """Show the about window."""
        if self.about_window:
            self.about_window.show()
            self.about_window.activateWindow()
            self.about_window.raise_()

    def prepare_fullscreen_capture(self):
        """Prepare fullscreen capture for user selection."""
        # Check if a CaptureOverlay is already open
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

            logger.info(f">>> [Overlay #{CaptureOverlay._display_counter}] CaptureOverlay OPENED")
        else:
            logger.error("Failed to capture full_screen")

    def _capture_all_screens(self, screens):
        """Capture all screens and combine them into a single pixmap."""
        if not screens:
            return None

        # Calculate the virtual desktop bounds
        min_x, min_y, max_x, max_y = get_virtual_desktop_bounds(screens)

        virtual_width = max_x - min_x + 1
        virtual_height = max_y - min_y + 1

        logger.debug(f"Virtual desktop bounds: {min_x}, {min_y}, {virtual_width}x{virtual_height}")

        # Get the maximum device pixel ratio among all screens
        max_dpr = max(screen.devicePixelRatio() for screen in screens)

        # Create a pixmap for the entire virtual desktop with proper DPI scaling
        combined_pixmap = QPixmap(int(virtual_width * max_dpr), int(virtual_height * max_dpr))
        combined_pixmap.fill(Qt.GlobalColor.transparent)
        combined_pixmap.setDevicePixelRatio(max_dpr)

        painter = QPainter(combined_pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Capture each screen and paste it at the correct position
        for screen in screens:
            screen_geometry = screen.geometry()
            screen_pixmap = screen.grabWindow(0)

            if not screen_pixmap.isNull():
                # Calculate position relative to virtual desktop
                x_offset = screen_geometry.left() - min_x
                y_offset = screen_geometry.top() - min_y

                # Scale the screen pixmap to match the combined pixmap's DPR
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

        painter.end()
        return combined_pixmap

    def _add_to_screenshot_snapshots(self, screenshot: QPixmap, start_pos: Optional[QPoint] = None, end_pos: Optional[QPoint] = None):
        """Add screenshot to snapshots with size limit."""
        # Add to snapshots with state
        snapshot_item = {
            'screenshot': screenshot.copy(),
            'start_pos': start_pos,
            'end_pos': end_pos
        }
        self.screenshot_snapshots.append(snapshot_item)

        # Limit snapshots size
        if len(self.screenshot_snapshots) > MAX_HISTORY:
            # Remove oldest screenshot
            self.screenshot_snapshots.pop(0)

        logger.debug(f"Screenshot added to snapshots. Total: {len(self.screenshot_snapshots)}")

    def quit_application(self):
        """Quit the application and clean up all resources."""

        # Close all managed windows
        if self.capture_overlay:
            try:
                self.capture_overlay.close()
            except Exception as e:
                logger.debug(f"Error closing capture overlay: {e}")

        # Close all pinned windows
        for pinned_window in self.pinned_windows[:]:  # Use slice to create a copy for safe iteration
            try:
                pinned_window.close()
            except Exception as e:
                logger.debug(f"Error closing pinned window: {e}")

        # Clean up single instance lock
        if self.single_instance:
            self.single_instance._cleanup()

        logger.info("Application quitting")
        QApplication.quit()


# ============================================================================
# UI Classes
# ============================================================================


class ActionBar(QWidget):
    """
    Floating toolbar providing annotation controls and actions.

    Displays buttons for drawing tools, undo/redo, color selection,
    pen width adjustment, and various actions (copy, save, pin, close).
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self.linked_widget = None
        # List to store button actions in order for keyboard shortcuts
        self.button_actions = []

        self.font_size = DEFAULT_FONT_SIZE
        self.current_pen_color = DEFAULT_PEN_COLOR

        # Text input state
        self.text_input: Optional[QLineEdit] = None
        self.text_input_pos: Optional[QPoint] = None

        # Drawing state
        self.drawing = False
        self.last_point = QPoint()
        self.draw_start_point = QPoint()
        self.preview_rect: Optional[QRect] = None
        self.preview_line: Optional[Tuple[QPoint, QPoint]] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TOOLBAR_MARGIN, TOOLBAR_MARGIN, TOOLBAR_MARGIN, TOOLBAR_MARGIN)
        layout.setSpacing(TOOLBAR_SPACING)

        self._setup_styles()
        self._init_buttons(layout)
        self.adjustSize()

        # Ensure all children have arrow cursor
        for child in self.findChildren(QWidget):
            child.setCursor(Qt.CursorShape.ArrowCursor)

    def _setup_styles(self):
        """Apply stylesheet to toolbar and its widgets."""
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
        """Create and add all toolbar buttons to the layout."""

        tool_names = [
            ("pen", "Pen Tool"),
            ("rectangle", "Rectangle Tool"),
            ("line", "Line Tool"),
            ("text", "Text Tool"),
        ]
        self.tool_buttons = []
        for idx, (mode, label) in enumerate(tool_names, start=1):
            btn = self._create_button(
                icon_name=mode,
                tooltip=f"{label} ({idx})",
                callback=self.tool_button_handler,
                checkable=True
            )
            btn.setProperty("mode", mode) 
            layout.addWidget(btn)
            self.tool_buttons.append(btn)
            self.button_actions.append(lambda b=btn: b.click())

        # Color picker button
        self.color_btn = self._create_button(tooltip=f"Choose Color ({len(self.button_actions) + 1})", callback=self.choose_color)
        self.update_color_button(self.current_pen_color)
        layout.addWidget(self.color_btn)
        self.button_actions.append(lambda: self.color_btn.click())

        # Pen width controls
        self.pen_width_label = QLabel()
        self.pen_width_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pen_width_label.setFixedWidth(24)
        layout.addWidget(self.pen_width_label)

        self.pen_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.pen_width_slider.setRange(1, 20)
        self.pen_width_slider.setValue(1)
        self.pen_width_slider.setFixedWidth(60)
        self.pen_width_slider.setSingleStep(1)
        self.pen_width_slider.valueChanged.connect(self.pen_width_label.setNum)
        self.pen_width_slider.setValue(DEFAULT_PEN_WIDTH)
        layout.addWidget(self.pen_width_slider)

        # Undo/Redo buttons
        self.undo_btn = self._create_button('undo', "Undo (Ctrl+Z)", lambda: self.linked_widget.undo_action())
        layout.addWidget(self.undo_btn)

        self.redo_btn = self._create_button('redo', "Redo (Ctrl+Y)", lambda: self.linked_widget.redo_action())
        layout.addWidget(self.redo_btn)

        # Action buttons
        self.copy_btn = self._create_button('copy', "Copy to Clipboard (Ctrl+C)", lambda: self.copy_to_clipboard())
        layout.addWidget(self.copy_btn)

        self.save_btn = self._create_button('save', "Save to File (Ctrl+S)", lambda: self.save_to_file())
        layout.addWidget(self.save_btn)

        self.pin_btn = self._create_button('pin', "Pin (Ctrl+T)", lambda: self.linked_widget.pin_to_display())
        layout.addWidget(self.pin_btn)

        self.close_btn = self._create_button('close', "Close (Esc)", lambda: self.linked_widget.close())
        layout.addWidget(self.close_btn)

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

    def tool_button_handler(self):
        """
        Handler for drawing tool buttons to ensure mutual exclusion,
        but allow all to be unselected.
        """
        sender = self.sender()
        if sender.isChecked():
            # Uncheck all others
            for btn in self.tool_buttons:
                if btn is not sender:
                    btn.setChecked(False)
        else:
            # Allow all to be unselected
            sender.setChecked(False)

    def get_active_draw_mode(self) -> Optional[str]:
        """Get the currently active drawing mode."""
        for btn in self.tool_buttons:
            if btn.isChecked():
                return btn.property("mode")
        return None

    def is_any_draw_tool_active(self) -> bool:
        """Check if any of the drawing tool buttons (pen, rectangle, line, text) are pressed."""
        return any(btn.isChecked() for btn in self.tool_buttons)
    
    def deactivate_all_draw_tools(self):
        """Deactivate all drawing tool buttons."""
        for btn in self.tool_buttons:
            btn.setChecked(False)

    def _show_toolbar(self, linked: QWidget):
        """Show toolbar linked to a specific widget."""
        logger.info(f"Showing toolbar linked to widget: {linked}")
        self.linked_widget = linked
        self._position_toolbar()
        self.show()

    def _position_toolbar(self):
        """Position toolbar at bottom right of selection area (in parent coordinates)"""
        if isinstance(self.linked_widget, CaptureOverlay):
            selection_rect = self.linked_widget.overlay_selection_rect
            toolbar_x = selection_rect.right() - self.width() + SELECTION_BORDER_WIDTH
            toolbar_y = selection_rect.bottom() + TOOLBAR_MARGIN + SELECTION_BORDER_WIDTH
            toolbar_x = max(0, min(toolbar_x, self.linked_widget.width() - self.width()))
            toolbar_y = min(toolbar_y, self.linked_widget.height() - self.height())
            self.move(toolbar_x, toolbar_y)
        else:
            toolbar_x = self.linked_widget.width() - self.width()
            toolbar_y = self.linked_widget.height() + TOOLBAR_MARGIN
            # self.move(toolbar_x, toolbar_y)
            self.move(self.linked_widget.mapToGlobal(QPoint(toolbar_x, toolbar_y)))

        # self.raise_()  # Keep it on top of other child widgets

    def choose_color(self):
        """Open color picker dialog"""
        color = QColorDialog.getColor(self.current_pen_color, self, "Choose Pen Color")
        if color.isValid():
            self.current_pen_color = color
            self.update_color_button(color)

    def update_color_button(self, color: QColor):
        """Update color button appearance based on selected color."""
        text_color = 'white' if color.lightness() < 128 else 'black'
        self.color_btn.setStyleSheet(
            f"background-color: {color.name()}; "
            f"color: {text_color}; "
            f"border: 1px solid #555; "
            f"border-radius: 3px;"
        )

    def _add_text_annotation(self, pos: QPoint):
        """Add text annotation at the given position"""
        # Create a text input field at the clicked position
        if self.text_input:
            self._finalize_text_input()

        self.text_input_pos = pos
        self.text_input = QLineEdit(self.linked_widget)

        # Style the text input
        font = QFont("Arial", self.font_size)
        font.setBold(True)
        self.text_input.setFont(font)

        # Calculate text color brightness to set contrasting background
        brightness = self.current_pen_color.lightness()
        bg_color = "rgba(255, 255, 255, 180)" if brightness < 128 else "rgba(0, 0, 0, 180)"
        text_color = self.current_pen_color.name()

        # No border at all to avoid offset issues
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

        # Set all margins to 0
        self.text_input.setTextMargins(0, 0, 0, 0)
        self.text_input.setContentsMargins(0, 0, 0, 0)

        # Position the input so it appears where the text will be drawn
        self.text_input.setMinimumWidth(100)
        self.text_input.adjustSize()

        # Position at click location - we'll adjust the final text drawing to match
        self.text_input.move(pos.x(), pos.y())

        self.text_input.show()
        self.text_input.setFocus()

        # Connect signals
        self.text_input.returnPressed.connect(lambda: self._finalize_text_input(font))
        self.text_input.editingFinished.connect(lambda: self._finalize_text_input(font))

    def _finalize_text_input(self, font: Optional[QFont] = None):
        """Finalize the text input and draw it on the screenshot"""
        if not self.text_input or not self.text_input_pos:
            return

        text = self.text_input.text()

        if text:
            painter = QPainter(self.linked_widget.full_screen)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            font.setPointSize(self.font_size)
            painter.setFont(font)

            # Set up pen for text
            painter.setPen(self.current_pen_color)

            # Calculate text offset based on QLineEdit's content margins
            # QLineEdit has internal padding that varies by platform
            content_margins = self.text_input.contentsMargins()
            x_offset = content_margins.left() if content_margins.left() > 0 else 2
            y_offset = content_margins.top() if content_margins.top() > 0 else 1

            # Draw text with calculated offsets
            text_rect = QRect(
                self.text_input_pos.x() + x_offset,
                self.text_input_pos.y() + y_offset,
                1000,  # Width (large enough for any text)
                100    # Height (large enough for any font size)
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
            painter.end()

            self.linked_widget._save_annotation_state()
            self.linked_widget.update()

        # Clean up
        self.text_input.deleteLater()
        self.text_input = None
        self.text_input_pos = None

    def _paint_shape_preview(self, painter: QPainter):
        """Paint preview for rectangle/line drawing modes"""
        if not self.linked_widget:
            return
        if self.preview_rect and self.get_active_draw_mode() == "rectangle":
            painter.setPen(self._create_drawing_pen(Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
            painter.setBrush(QColor(self.current_pen_color.red(), self.current_pen_color.green(), self.current_pen_color.blue(), 50))
            painter.drawRect(self.preview_rect)

        if self.preview_line and self.get_active_draw_mode() == "line":
            painter.setPen(self._create_drawing_pen())
            painter.drawLine(self.preview_line[0], self.preview_line[1])

    def handle_key_press(self, event):
        if not self.linked_widget:
            return False

        key = event.key()
        # Handle Ctrl modifier
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            shortcuts = {
                Qt.Key.Key_Z: self.linked_widget.undo_action,
                Qt.Key.Key_Y: self.linked_widget.redo_action,
                Qt.Key.Key_S: self.save_to_file,
                Qt.Key.Key_C: self.copy_to_clipboard,
                Qt.Key.Key_T: self.linked_widget.pin_to_display,
            }
            if key in shortcuts:
                shortcuts[key]()
                return True
            return False

        # Handle number keys for toolbar shortcuts (1-9)
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            button_index = key - Qt.Key.Key_1
            if button_index < len(self.button_actions):
                self.button_actions[button_index]()
            return True

    def handle_mouse_press(self, event):
        """Start drawing or place text annotation based on draw mode"""
        if not self.linked_widget or not self.is_any_draw_tool_active():
            return False

        pos = event.pos()
        if self.get_active_draw_mode() == "text":
            self._add_text_annotation(pos)
        else:
            self.drawing = True
            self.last_point = pos
            self.draw_start_point = pos
        return True

    def handle_mouse_move(self, event):
        """Handle mouse move for drawing preview"""
        if not self.linked_widget or not self.is_any_draw_tool_active():
            return False

        pos = event.pos()
        if self.drawing and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)):
            draw_mode = self.get_active_draw_mode()

            if draw_mode == "pen":
                # pen draws directly onto the screenshot
                painter = QPainter(self.linked_widget.full_screen)
                pen = self._create_drawing_pen()
                painter.setPen(pen)
                painter.drawLine(self.last_point, pos)
                self.last_point = pos
                painter.end()
            elif draw_mode == "rectangle":
                self.preview_rect = QRect(self.draw_start_point, pos).normalized()
            elif draw_mode == "line":
                self.preview_line = (self.draw_start_point, pos)
            self.linked_widget.update()
        return True

    def handle_wheel_event(self, event):
        """Finalize drawing on mouse release"""
        if not self.linked_widget or not self.is_any_draw_tool_active():
            return False

        if self.text_input and self.text_input.isVisible():
            # Get wheel delta (positive = scroll up, negative = scroll down)
            delta = event.angleDelta().y()
            # Adjust font size (scroll up = larger, scroll down = smaller)
            if delta > 0:
                self.font_size = min(72, self.font_size + 2)  # Max font size: 72
            else:
                self.font_size = max(8, self.font_size - 2)   # Min font size: 8

            font = self.text_input.font()
            font.setPointSize(self.font_size)
            self.text_input.setFont(font)
            self.text_input.adjustSize()

            event.accept()
        return True

    def _create_drawing_pen(self, cap_style=Qt.PenCapStyle.RoundCap, join_style=Qt.PenJoinStyle.RoundJoin) -> QPen:
        """Create a standard pen for drawing operations"""
        return QPen(
            self.current_pen_color,
            self.pen_width_slider.value(),
            Qt.PenStyle.SolidLine,
            cap_style,
            join_style
        )

    def _finalize_sharp(self, end_point: QPoint):
        """Draw the shape to the pixmap based on current draw mode"""
        painter = QPainter(self.linked_widget.full_screen)
        draw_mode = self.get_active_draw_mode()
        if draw_mode == "rectangle":
            pen = self._create_drawing_pen(Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(QColor(
                self.current_pen_color.red(),
                self.current_pen_color.green(),
                self.current_pen_color.blue(),
                50
            ))
            rect = QRect(self.draw_start_point, end_point).normalized()
            painter.drawRect(rect)
            self.preview_rect = None
        elif draw_mode == "line":
            pen = self._create_drawing_pen()
            painter.setPen(pen)
            painter.drawLine(self.draw_start_point, end_point)
            self.preview_line = None
        painter.end()
        self.linked_widget._save_annotation_state()
        self.linked_widget.update()

    def save_to_file(self):
        """Save the current selection to a file"""
        cropped, _ = self.linked_widget._get_cropped_selection()
        self.linked_widget.close()
        if cropped:
            # Open save dialog
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

    def copy_to_clipboard(self):
        """Copy the current selection to clipboard"""
        cropped, _ = self.linked_widget._get_cropped_selection()
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

        self.hint_label = None
        self.annotation_states: List[dict] = []

        QShortcut(QKeySequence("Esc"), self).activated.connect(self._handle_esc_shortcut)

    def _handle_esc_shortcut(self):
        """Esc can happen before actionbar is shown, so handle here."""
        actionbar = get_actionbar()
        if actionbar.text_input:
            actionbar.text_input.deleteLater()
            actionbar.text_input = None
            actionbar.text_input_pos = None
            return

        if actionbar.is_any_draw_tool_active():
            actionbar.deactivate_all_draw_tools()
        else:
            self.close()

    def _init_annotation_states(self):
        """Initialize annotation states for undo/redo functionality."""
        self.annotation_states = []
        self.undo_redo_index = -1

    def _save_annotation_state(self):
        """Save current annotation state to states list for undo/redo"""

        # Remove any states after current index (for redo)
        self.annotation_states = self.annotation_states[:self.undo_redo_index + 1]

        # Add new state
        cropped, selection_rect = self._get_cropped_selection()
        self.annotation_states.append({
            'screenshot': cropped,
            'selection_rect': selection_rect
        })
        self.undo_redo_index += 1

        if len(self.annotation_states) > MAX_HISTORY:
            self.annotation_states.pop(0)
            self.undo_redo_index -= 1
        
        logger.info(f"Annotation states: {len(self.annotation_states)}")

    def undo_action(self):
        """Undo last annotation"""
        if self.undo_redo_index > 0:
            self.undo_redo_index -= 1
            self._restore_annotation_state(self.undo_redo_index)
            self.update()

    def redo_action(self):
        """Redo annotation"""
        if self.undo_redo_index < len(self.annotation_states) - 1:
            self.undo_redo_index += 1
            self._restore_annotation_state(self.undo_redo_index)
            self.update()
    
    def _restore_annotation_state(self, index: int):
        """Restore annotation state from index"""
        state_item = self.annotation_states[index]
        state_pixmap = state_item['screenshot']
        selection_rect = state_item['selection_rect']
        painter = QPainter(self.full_screen)
        painter.drawPixmap(selection_rect, state_pixmap, state_pixmap.rect())
        painter.end()

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

        # Position at the center of the screen
        self.hint_label.adjustSize()
        x = (self.width() - self.hint_label.width()) // 2
        y = (self.height() - self.hint_label.height()) // 2
        self.hint_label.move(x, y)
        self.hint_label.show()

        # Hide after duration
        QTimer.singleShot(duration, self.hint_label.hide)

    def closeEvent(self, event):
        get_actionbar().hide()
        self.annotation_states.clear()

class CaptureOverlay(OverlayBase):
    """
    Fullscreen overlay for selecting and annotating screenshot areas.

    Features:
    - Drag to select rectangular area
    - Resize selection with edge/corner handles
    - Move selection by dragging
    - Arrow keys for fine positioning
    - Multiple drawing tools (pen, rectangle, line, text)
    - Undo/redo support with history
    - Keyboard shortcuts for all actions
    """

    # Class-level counter for unique instance IDs
    _display_counter = 0

    def __init__(self):
        super().__init__()

        screens = QApplication.screens()
        if screens:
            min_x, min_y, max_x, max_y = get_virtual_desktop_bounds(screens)

            virtual_width = max_x - min_x + 1
            virtual_height = max_y - min_y + 1

            # Set geometry to cover the entire desktop
            self.setGeometry(min_x, min_y, virtual_width, virtual_height)
            logger.debug(f"CaptureOverlay geometry set to virtual desktop: {min_x}, {min_y}, {virtual_width}x{virtual_height}")
        else:
            # Fallback to primary screen if no screens found
            screen = QApplication.primaryScreen()
            if screen:
                full_geometry = screen.geometry()
                self.setGeometry(full_geometry)

        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.full_screen)

        get_actionbar()._paint_shape_preview(painter)

        selection_rect = self.overlay_selection_rect
        if selection_rect is not None:
            self._paint_overlay_around_selection(painter, selection_rect)
            self._paint_selection_border(painter, selection_rect)
        else:
            painter.fillRect(self.rect(), OVERLAY_COLOR)

    def keyPressEvent(self, event):
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
        if key in arrow_keys and self.overlay_selection_rect is not None:
            self._handle_arrow_key_movement(event)
            return

        if get_actionbar().handle_key_press(event):
            return

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        pos = event.pos()
        selection_rect = self.overlay_selection_rect
        if selection_rect is not None and not self.selecting:
            resize_edge = self._get_resize_edge(pos, selection_rect)
            if resize_edge:
                self.resizing = True
                self.resize_edge = resize_edge
            elif selection_rect.contains(pos):
                if get_actionbar().handle_mouse_press(event):
                    return
                self.dragging_selection = True
                self.drag_offset = pos - selection_rect.topLeft()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            self.selecting = True

    def mouseMoveEvent(self, event):
        actionbar = get_actionbar()
        if self.resizing:
            self._apply_resize(event.pos().x(), event.pos().y())
            actionbar._position_toolbar()
            self.update()
        elif self.dragging_selection:
            selection_rect = self.overlay_selection_rect
            if selection_rect is not None:
                width = selection_rect.width()
                height = selection_rect.height()
                new_top_left = event.pos() - self.drag_offset

                new_x = max(0, min(new_top_left.x(), self.width() - width))
                new_y = max(0, min(new_top_left.y(), self.height() - height))

                self.start_pos = QPoint(new_x, new_y)
                self.end_pos = QPoint(new_x + width, new_y + height)
                actionbar._position_toolbar()
                self.update()
        elif self.selecting:
            self.end_pos = event.pos()
            self.update()
        elif self.overlay_selection_rect is not None:
            self._update_cursor(event.pos())
            if self.overlay_selection_rect.contains(event.pos()):
                actionbar.handle_mouse_move(event)

    def mouseReleaseEvent(self, event):
        actionbar = get_actionbar()
        if event.button() == Qt.MouseButton.LeftButton or event.button() == Qt.MouseButton.RightButton:
            if self.resizing:
                self.resizing = False
                self.resize_edge = None
            elif self.dragging_selection:
                self.dragging_selection = False
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.selecting:
                self.selecting = False
                self.end_pos = event.pos()
                self._finalize_selection()
            elif actionbar.drawing:
                if self.overlay_selection_rect.contains(event.pos()):
                    actionbar._finalize_sharp(event.pos())
                actionbar.drawing = False

    def wheelEvent(self, event):
        """Handle mouse wheel events for font size adjustment when text input is active"""
        # Don't do if the wheel event is over the toolbar
        actionbar = get_actionbar()
        if not actionbar.geometry().contains(event.position().toPoint()):
            actionbar.handle_wheel_event(event)
        else:
            super().wheelEvent(event)

    def new_capture(self, full_screen: QPixmap):
        CaptureOverlay._display_counter += 1

        self.full_screen = full_screen

        # Selection state
        self.start_pos: Optional[QPoint] = None
        self.end_pos: Optional[QPoint] = None
        self.selecting = False

        # Dragging state
        self.dragging_selection = False
        self.drag_offset = QPoint()

        # Resizing state
        self.resizing = False
        self.resize_edge: Optional[str] = None
        self.resize_handle_size = RESIZE_HANDLE_SIZE


        # Current position in screenshot snapshots (-1 means not in snapshots)
        self.current_snapshot_index: int = -1

        self._init_annotation_states()

    @property
    def overlay_selection_rect(self) -> Optional[QRect]:
        """Get the current selection rectangle, normalized. Returns None if selection is not valid."""
        if self.start_pos is not None and self.end_pos is not None:
            return QRect(self.start_pos, self.end_pos).normalized()
        return None

    def _paint_overlay_around_selection(self, painter: QPainter, selection_rect: QRect):
        """Paint dark overlay around the selection area"""
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
        """Paint the selection rectangle border"""
        border_width = SELECTION_BORDER_WIDTH if not self.selecting else SELECTION_BORDER_WIDTH - 1
        pen = QPen(SELECTION_BORDER_COLOR, border_width, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)

        # Draw four sides of the border
        painter.drawLine(selection_rect.left(), selection_rect.top(),
                       selection_rect.right(), selection_rect.top())
        painter.drawLine(selection_rect.left(), selection_rect.bottom(),
                       selection_rect.right(), selection_rect.bottom())
        painter.drawLine(selection_rect.left(), selection_rect.top(),
                       selection_rect.left(), selection_rect.bottom())
        painter.drawLine(selection_rect.right(), selection_rect.top(),
                       selection_rect.right(), selection_rect.bottom())

    def _get_resize_edge(self, pos: QPoint, rect: QRect) -> Optional[str]:
        """
        Detect which edge/corner of the selection is under the cursor.

        Returns edge name: 'top', 'bottom', 'left', 'right',
                          'top-left', 'top-right', 'bottom-left', 'bottom-right',
                          or None if not on an edge.
        """
        margin = self.resize_handle_size
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

    def _update_cursor(self, pos):
        """Update cursor based on position relative to selection"""
        if get_actionbar().is_any_draw_tool_active():
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        selection_rect = self.overlay_selection_rect
        if selection_rect is None:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        resize_edge = self._get_resize_edge(pos, selection_rect)

        if resize_edge:
            self.setCursor(self._get_resize_cursor(resize_edge))
        elif selection_rect.contains(pos):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _apply_resize(self, mouse_x, mouse_y):
        """Apply resize transformation based on current resize edge"""
        min_size = MIN_SELECTION_SIZE

        # Map edge names to resize operations
        resize_operations = {
            'left': lambda: self.start_pos.setX(min(mouse_x, self.end_pos.x() - min_size)),
            'right': lambda: self.end_pos.setX(max(mouse_x, self.start_pos.x() + min_size)),
            'top': lambda: self.start_pos.setY(min(mouse_y, self.end_pos.y() - min_size)),
            'bottom': lambda: self.end_pos.setY(max(mouse_y, self.start_pos.y() + min_size)),
            'top-left': lambda: (
                self.start_pos.setX(min(mouse_x, self.end_pos.x() - min_size)),
                self.start_pos.setY(min(mouse_y, self.end_pos.y() - min_size))
            ),
            'top-right': lambda: (
                self.end_pos.setX(max(mouse_x, self.start_pos.x() + min_size)),
                self.start_pos.setY(min(mouse_y, self.end_pos.y() - min_size))
            ),
            'bottom-left': lambda: (
                self.start_pos.setX(min(mouse_x, self.end_pos.x() - min_size)),
                self.end_pos.setY(max(mouse_y, self.start_pos.y() + min_size))
            ),
            'bottom-right': lambda: (
                self.end_pos.setX(max(mouse_x, self.start_pos.x() + min_size)),
                self.end_pos.setY(max(mouse_y, self.start_pos.y() + min_size))
            ),
        }

        if self.resize_edge in resize_operations:
            resize_operations[self.resize_edge]()

    def _finalize_selection(self):
        """Finalize selection and initialize toolbar with snapshot handling"""
        selection_rect = self.overlay_selection_rect

        # Selection too small, clear it to allow new selection
        if selection_rect is None or selection_rect.width() <= MIN_VALID_RECT or selection_rect.height() <= MIN_VALID_RECT:
            self.start_pos = None
            self.end_pos = None
            self.update()
            return

        self.start_pos = selection_rect.topLeft()
        self.end_pos = selection_rect.bottomRight()
        self.update()

        actionbar = get_actionbar()
        actionbar.setParent(self)
        actionbar._show_toolbar(self)

        self._save_annotation_state()
        # Save screenshot with selection to snapshots
        app = QApplication.instance()
        if hasattr(app, 'controller') and app.controller:
            app.controller._add_to_screenshot_snapshots(
                self.full_screen,
                self.start_pos,
                self.end_pos
            )
            logger.debug(f"Added screenshot to snapshots with selection: {self.start_pos} -> {self.end_pos}")

            # Reset snapshot index since we're now on a new screenshot
            self.current_snapshot_index = -1

    def _handle_arrow_key_movement(self, event):
        """Handle arrow key movement of selection"""
        width = abs(self.end_pos.x() - self.start_pos.x())
        height = abs(self.end_pos.y() - self.start_pos.y())
        current_x = self.start_pos.x()
        current_y = self.start_pos.y()
        step = KEYBOARD_STEP_LARGE if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else KEYBOARD_STEP_SMALL

        # Calculate new position based on arrow key
        key_to_delta = {
            Qt.Key.Key_Left: (-step, 0),
            Qt.Key.Key_Right: (step, 0),
            Qt.Key.Key_Up: (0, -step),
            Qt.Key.Key_Down: (0, step),
        }

        delta_x, delta_y = key_to_delta.get(event.key(), (0, 0))
        new_x = max(0, min(self.width() - width, current_x + delta_x))
        new_y = max(0, min(self.height() - height, current_y + delta_y))

        self.start_pos = QPoint(new_x, new_y)
        self.end_pos = QPoint(new_x + width, new_y + height)
        get_actionbar()._position_toolbar()
        self.update()

    def _find_current_snapshot_index(self, screenshot_snapshots):
        """
        Find the current snapshot index by checking stored index or comparing screenshot data.

        Args:
            screenshot_snapshots: List of screenshot snapshot items

        Returns:
            Current snapshot index, or len(screenshot_snapshots) if not found
        """
        if self.current_snapshot_index >= 0 and self.current_snapshot_index < len(screenshot_snapshots):
            return self.current_snapshot_index

        # Try to find by comparing screenshot data
        for i, snapshot_item in enumerate(screenshot_snapshots):
            snapshot_screenshot = snapshot_item['screenshot']
            if snapshot_screenshot.cacheKey() == self.full_screen.cacheKey():
                return i

        # If not found, for navigation purposes, set to len so previous index is the last one
        return len(screenshot_snapshots)

    def _navigate_snapshots(self, direction: int):
        """
        Navigate through screenshot snapshots (different screenshots).

        Args:
            direction: -1 for previous (left), 1 for next (right)
        """
        app = QApplication.instance()
        if not hasattr(app, 'controller') or not app.controller or not app.controller.screenshot_snapshots:
            return

        screenshot_snapshots = app.controller.screenshot_snapshots

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
            # Get the snapshot item
            snapshot_item = screenshot_snapshots[new_index]

            # Restore selection from snapshot item
            self._restore_selection(
                screenshot=snapshot_item['screenshot'],
                start_pos=snapshot_item['start_pos'],
                end_pos=snapshot_item['end_pos'],
                reset_annotation=True
            )

            logger.debug(f"Navigated to screenshot {new_index} with selection: {self.start_pos} -> {self.end_pos}")

            self.update()

            # Update current snapshot index
            self.current_snapshot_index = new_index

    def _restore_selection(self, screenshot, start_pos, end_pos, reset_annotation=True):
        """Restore screenshot selection and optional reset annotation states

        Args:
            screenshot: The screenshot pixmap to restore
            start_pos: Starting position for the selection
            end_pos: Ending position for the selection
            reset_annotation: If True, reset annotation states (default True)
        """
        self.full_screen = screenshot.copy()
        self.start_pos = start_pos
        self.end_pos = end_pos

        if reset_annotation:
            self._init_annotation_states()
            self._save_annotation_state()

        # Show toolbar if selection exists
        if self.overlay_selection_rect is not None:
            get_actionbar()._show_toolbar(self)

    def _scale_rect(self, rect: QRect) -> QRect:
        """
        Scale a rectangle by device pixel ratio for high DPI displays.
        Note: Only use this when directly accessing pixmap pixel data (like copy).
        When drawing with QPainter on a pixmap with devicePixelRatio set,
        Qt automatically handles the scaling, so use logical coordinates.
        """
        if self.full_screen.devicePixelRatio() <= 1.0:
            return rect
        return QRect(
            int(rect.x() * self.full_screen.devicePixelRatio()),
            int(rect.y() * self.full_screen.devicePixelRatio()),
            int(rect.width() * self.full_screen.devicePixelRatio()),
            int(rect.height() * self.full_screen.devicePixelRatio())
        )

    def _get_cropped_selection(self) -> Tuple[Optional[QPixmap], Optional[QRect]]:
        """
        Get the cropped annotated screenshot from current selection.

        Returns:
            Tuple of (cropped_pixmap, selection_rect) or (None, None) if invalid.
        """
        result: Tuple[Optional[QPixmap], Optional[QRect]] = (None, None)
        selection_rect = self.overlay_selection_rect
        if selection_rect is not None and selection_rect.width() > MIN_VALID_RECT and selection_rect.height() > MIN_VALID_RECT:
            # Scale the selection rect for high DPI displays
            scaled_rect = self._scale_rect(selection_rect)
            cropped = self.full_screen.copy(scaled_rect)
            # Preserve the device pixel ratio on the cropped pixmap
            cropped.setDevicePixelRatio(self.full_screen.devicePixelRatio())
            result = (cropped, selection_rect)
        return result

    def pin_to_display(self):
        """Pin the current selection"""
        cropped, selection_rect = self._get_cropped_selection()
        if cropped:
            pinned_window = PinnedOverlay(
                cropped,
                position=selection_rect.topLeft(),
                selection_rect=selection_rect,
                saved_annotation_states=self.annotation_states,
                saved_state_index=self.undo_redo_index
            )
            # Transfer annotation states reference, so close .clear() won't delete data
            self.annotation_states = []
            pinned_window.show()

            app = QApplication.instance()
            if hasattr(app, 'controller') and app.controller:
                app.controller.pinned_windows.append(pinned_window)
                logger.info(f"Screenshot pinned to screen. Total pinned: {len(app.controller.pinned_windows)}")
        self.close()

    def closeEvent(self, event):
        """Clean up toolbar and release resources when closing"""
        super().closeEvent(event)

        self.full_screen = None
        logger.info(f"<<< [Overlay #{CaptureOverlay._display_counter}] CaptureOverlay HIDED")
        event.accept()


class PinnedOverlay(OverlayBase):
    """
    Pinned window for displaying captured and annotated screenshots.

    Features:
    - Always-on-top frameless window with glow effect
    - Draggable with left mouse button
    - Double-click to close
    - Space key to reopen in edit mode
    - Esc key to close
    - Mouse scroll to adjust transparency
    """

    def __init__(self, pixmap: QPixmap, position: Optional[QPoint] = None,
                 selection_rect: Optional[QRect] = None,
                 saved_annotation_states: Optional[List[QPixmap]] = None,
                 saved_state_index: int = -1):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.pixmap = pixmap
        self.selection_rect = selection_rect
        self.saved_annotation_states = saved_annotation_states or []
        self.saved_state_index = saved_state_index
        self.glow_size = GLOW_SIZE

        logical_width, logical_height = self._get_logical_size()

        # Size includes padding for glow effect
        self.setFixedSize(logical_width + 2 * self.glow_size,
                         logical_height + 2 * self.glow_size)

        # Position adjusted for glow effect
        if position:
            self.move(position.x() - self.glow_size, position.y() - self.glow_size)

        # Dragging state
        self.dragging = False
        self.offset = QPoint()

        # Transparency state
        self.opacity = 1.0  # 100% opaque by default
        self.setWindowOpacity(self.opacity)

        # Opacity label (hidden by default)
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

        # Keyboard shortcuts
        QShortcut(QKeySequence("Space"), self).activated.connect(self._handle_space_shortcut)

    def _handle_space_shortcut(self):
        actionbar = get_actionbar()
        if actionbar.isVisible():
            actionbar.hide()
        else:
            actionbar.setParent(None)
            actionbar._show_toolbar(self)

    def _get_logical_size(self) -> Tuple[int, int]:
        """Get the logical size of the pixmap (accounting for device pixel ratio)"""
        return (
            int(self.pixmap.width() / self.pixmap.devicePixelRatio()),
            int(self.pixmap.height() / self.pixmap.devicePixelRatio())
        )

    def paintEvent(self, event):
        logical_width, logical_height = self._get_logical_size()

        glow_base_color = (220, 220, 220)
        glow_layers = [
            (QColor(*glow_base_color, 80), 1),   # Inner
            (QColor(*glow_base_color, 60), 2),
            (QColor(*glow_base_color, 40), 3),
            (QColor(*glow_base_color, 20), 5),
            (QColor(*glow_base_color, 10), 9),   # Outer
        ]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Draw glow effect expanding outward from the pixmap
        for color, offset in glow_layers:
            painter.setBrush(QBrush(color))
            glow_rect = QRect(self.glow_size - offset, self.glow_size - offset,
                            logical_width + offset * 2, logical_height + offset * 2)
            painter.drawRect(glow_rect)

        # Draw the pixmap at the center (glow expands outward)
        painter.drawPixmap(self.glow_size, self.glow_size, self.pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(self.mapToGlobal(event.pos() - self.offset))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def mouseDoubleClickEvent(self, event):
        self.close()

    def wheelEvent(self, event):
        """Handle mouse wheel events to adjust window opacity/transparency"""
        # Get wheel delta (positive = scroll up, negative = scroll down)
        delta = event.angleDelta().y()

        # Adjust opacity (scroll up = more opaque, scroll down = more transparent)
        if delta > 0:
            self.opacity = min(1.0, self.opacity + 0.05)  # Increase opacity (less transparent)
        else:
            self.opacity = max(0.1, self.opacity - 0.05)  # Decrease opacity (more transparent), min 10%

        # Apply the new opacity
        self.setWindowOpacity(self.opacity)

        # Update and show the opacity label
        opacity_percent = int(self.opacity * 100)
        self.opacity_label.setText(f"{opacity_percent}%")
        self.opacity_label.adjustSize()

        # Position the label in the top-right corner with some margin
        margin = 10
        label_x = self.width() - self.opacity_label.width() - margin
        label_y = margin
        self.opacity_label.move(label_x, label_y)
        self.opacity_label.show()
        self.opacity_label.raise_()

        # Restart timer to hide label after 1 second of no scrolling
        self.opacity_timer.start(1000)

        event.accept()

    def reopen_capture(self):
        """Reopen capture overlay with the saved annotation states restored"""
        if not (self.saved_annotation_states and self.selection_rect):
            return

        app = QApplication.instance()
        if not hasattr(app, 'controller') or not app.controller:
            logger.error("AppController not available")
            return
        overlay = app.controller.capture_overlay
        if not overlay:
            logger.error("CaptureOverlay not available")
            return

        # Restore selection from current annotation state
        overlay._restore_selection(
            screenshot=self.saved_annotation_states[self.saved_state_index],
            start_pos=self.selection_rect.topLeft(),
            end_pos=self.selection_rect.bottomRight(),
            reset_annotation=False
        )

        # Transfer saved annotation states reference, so close .clear() won't delete data
        overlay.annotation_states = self.saved_annotation_states
        self.saved_annotation_states = []
        overlay.undo_redo_index = self.saved_state_index

        overlay.show()

        logger.info(f">>> [Overlay #{overlay.instance_id}] CaptureOverlay REOPENED from pinned window")

        self.close()

    def closeEvent(self, event):
        """Clean up and remove from pinned windows list"""
        super().closeEvent(event)

        # Clean up timers
        if hasattr(self, 'opacity_timer'):
            self.opacity_timer.stop()

        pinned_list = get_app_controller().pinned_windows
        pinned_list.remove(self)
        self.pixmap = None
        logger.info(f"Pinned window closed. Remaining: {len(pinned_list)}")
        event.accept()


class MainWindow(QMainWindow):
    """
    About dialog window showing application information.

    Simple dialog displaying app name, hotkey, and usage instructions.
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowTitle("About - ShotNPin")
        self.setGeometry(100, 100, 300, 250)
        self._setup_ui()

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

    # Don't quit when last window closes (we run in system tray)
    app.setQuitOnLastWindowClosed(False)

    # Create app controller with single instance management
    controller = AppController(single_instance)
    app.controller = controller

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
