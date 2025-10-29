#!/usr/bin/env python3
"""
ShotNPin - Simple screenshot, annotation, and pinning tool

A lightweight application for capturing, annotating, and pinning screenshots.
"""
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple, List

from pynput import keyboard
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QByteArray, pyqtSignal, QObject
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QShortcut, QKeySequence, QIcon, QFont
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
MIN_VALID_RECT = 5
ICON_SIZE = 24
TOOLBAR_MARGIN = 5
TOOLBAR_SPACING = 3

# Drawing Defaults
DEFAULT_PEN_WIDTH = 2
DEFAULT_PEN_COLOR = QColor(255, 0, 0)
DEFAULT_FONT_SIZE = 16
MAX_HISTORY = 50

# Keyboard
GLOBAL_HOTKEY = '<ctrl>+<shift>+q'
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
    'pencil': "m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125",
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
    """
    Main application controller managing system tray and screenshot functionality.

    Handles all application-level logic including tray menu, screenshot capture,
    global hotkey registration, single instance management, and application lifecycle.
    """

    # Signal for thread-safe screenshot triggering from keyboard hotkey
    screenshot_triggered = pyqtSignal()

    def __init__(self, single_instance: SingleInstance):
        super().__init__()
        self.about_window = None
        self.tray_icon = None
        self.single_instance = single_instance

        self._setup_about_window()
        self._setup_tray()
        self._setup_hotkey()
        self._setup_single_instance_handler()

        # Connect signal to slot
        self.screenshot_triggered.connect(self.take_screenshot)

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
        screenshot_action.triggered.connect(self.take_screenshot)

        # About action
        about_action = tray_menu.addAction("About")
        about_action.triggered.connect(self.show_about)

        tray_menu.addSeparator()

        # Exit action
        exit_action = tray_menu.addAction("Exit")
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
                        f"Running in background. Use {GLOBAL_HOTKEY} to capture.",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000
                    )

    def tray_icon_activated(self, reason):
        """Handle tray icon activation (clicks)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.take_screenshot()

    def _setup_hotkey(self):
        """Register global hotkey for screenshot capture."""
        try:
            # Define the hotkey combination
            hotkeys = {GLOBAL_HOTKEY: lambda: self.screenshot_triggered.emit()}
            keyboard.GlobalHotKeys(hotkeys).start()
 
            logger.info(f"Global hotkey registered: {GLOBAL_HOTKEY}")
        except Exception as e:
            logger.error(f"Failed to register global hotkey {GLOBAL_HOTKEY}: {e}")
            if sys.platform == "darwin":  # macOS
                logger.info("On macOS: Please grant Accessibility permissions in System Preferences > Security & Privacy > Privacy > Accessibility")
                QMessageBox.warning(
                    None,
                    "ShotNPin - Permission Required",
                    f"Failed to register global hotkey {GLOBAL_HOTKEY}.\n\n"
                    "Please grant Accessibility permissions in System Preferences:\n"
                    "System Preferences → Security & Privacy → Privacy → Accessibility\n\n"
                    "Add Terminal or this application to the list and check it."
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

    def take_screenshot(self):
        """Capture screen and open editor."""
        # Check if a CaptureEditor is already open
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, CaptureEditor) and widget.isVisible():
                logger.debug("Screenshot already in progress, ignoring")
                return

        try:
            screens = QApplication.screens()
            if not screens:
                logger.error("No screen available for capture")
                return

            screenshot = self._capture_all_screens(screens)
            if screenshot and not screenshot.isNull():
                editor = CaptureEditor(screenshot)

                # Keep reference to prevent garbage collection
                app = QApplication.instance()
                app.capture_editor = editor

                editor.show()
                logger.debug("Capture editor opened")
            else:
                logger.error("Failed to capture screenshot")
        except Exception as e:
            logger.error(f"Error capturing screen: {e}")

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
                
                logger.debug(f"Captured screen at {x_offset}, {y_offset}, DPR: {screen.devicePixelRatio()}")
        
        painter.end()
        
        return combined_pixmap

    def quit_application(self):
        """Quit the application and clean up all resources."""

        # Close all capture editors and pinned windows
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, (CaptureEditor, PinnedImageWindow)):
                try:
                    widget.close()
                except Exception as e:
                    logger.debug(f"Error closing window: {e}")

        # Clean up single instance lock
        if self.single_instance:
            self.single_instance.cleanup()

        logger.info("Application quitting")
        QApplication.quit()


# ============================================================================
# UI Classes
# ============================================================================


class FloatingToolbar(QWidget):
    """
    Floating toolbar providing annotation controls and actions.

    Displays buttons for drawing tools, undo/redo, color selection,
    pen width adjustment, and various actions (copy, save, pin, close).
    """

    def __init__(self, parent: 'CaptureEditor'):
        super().__init__(parent)
        self.parent_window = parent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # List to store button actions in order for keyboard shortcuts
        self.button_actions = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TOOLBAR_MARGIN, TOOLBAR_MARGIN, TOOLBAR_MARGIN, TOOLBAR_MARGIN)
        layout.setSpacing(TOOLBAR_SPACING)

        self._setup_styles()
        self._create_buttons(layout)
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

    def _create_buttons(self, layout: QHBoxLayout):
        """Create and add all toolbar buttons to the layout."""
        parent = self.parent_window

        # Drawing tool buttons (checkable) - with number shortcuts
        self.pen_btn = self._create_button('pencil', f"Pen Tool ({len(self.button_actions) + 1})",
                                          lambda: parent.set_draw_mode("pen"), checkable=True)
        layout.addWidget(self.pen_btn)
        self.button_actions.append(lambda: self.pen_btn.click())

        self.rect_btn = self._create_button('rectangle', f"Rectangle Tool ({len(self.button_actions) + 1})",
                                            lambda: parent.set_draw_mode("rectangle"), checkable=True)
        layout.addWidget(self.rect_btn)
        self.button_actions.append(lambda: self.rect_btn.click())

        self.line_btn = self._create_button('line', f"Line Tool ({len(self.button_actions) + 1})",
                                           lambda: parent.set_draw_mode("line"), checkable=True)
        layout.addWidget(self.line_btn)
        self.button_actions.append(lambda: self.line_btn.click())

        self.text_btn = self._create_button('text', f"Text Tool ({len(self.button_actions) + 1})",
                                           lambda: parent.set_draw_mode("text"), checkable=True)
        layout.addWidget(self.text_btn)
        self.button_actions.append(lambda: self.text_btn.click())

        # Color picker button
        self.color_btn = QPushButton()
        self.color_btn.setToolTip(f"Choose Color ({len(self.button_actions) + 1})")
        self.color_btn.clicked.connect(parent.choose_color)
        self.update_color_button(parent.pen_color)
        layout.addWidget(self.color_btn)
        self.button_actions.append(parent.choose_color)

        # Pen width controls
        self.pen_width_label = QLabel(str(parent.pen_width))
        self.pen_width_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pen_width_label.setFixedWidth(24)
        layout.addWidget(self.pen_width_label)

        self.pen_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.pen_width_slider.setRange(1, 20)
        self.pen_width_slider.setValue(parent.pen_width)
        self.pen_width_slider.setFixedWidth(60)
        self.pen_width_slider.setSingleStep(1)
        self.pen_width_slider.valueChanged.connect(parent.update_pen_width)
        self.pen_width_slider.valueChanged.connect(self.pen_width_label.setNum)
        layout.addWidget(self.pen_width_slider)

        # Undo/Redo buttons
        self.undo_btn = self._create_button('undo', "Undo (Ctrl+Z)", parent.undo_action)
        layout.addWidget(self.undo_btn)

        self.redo_btn = self._create_button('redo', "Redo (Ctrl+Y)", parent.redo_action)
        layout.addWidget(self.redo_btn)

        # Action buttons
        self.copy_btn = self._create_button('copy', "Copy to Clipboard (Ctrl+C)", parent.copy_to_clipboard)
        layout.addWidget(self.copy_btn)

        self.save_btn = self._create_button('save', "Save to File (Ctrl+S)", parent.save_to_file)
        layout.addWidget(self.save_btn)

        self.pin_btn = self._create_button('pin', "Pin (Ctrl+T)", parent.pin_to_display)
        layout.addWidget(self.pin_btn)

        self.close_btn = self._create_button('close', "Close (Esc)", parent.close)
        layout.addWidget(self.close_btn)

    def _create_button(self, icon_name: str, tooltip: str, callback, checkable: bool = False) -> QPushButton:
        """Helper method to create a toolbar button."""
        btn = QPushButton()
        btn.setIcon(create_svg_icon(SVG_ICONS[icon_name]))
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        if checkable:
            btn.setCheckable(True)
            btn.setChecked(False)
        return btn

    def update_color_button(self, color: QColor):
        """Update color button appearance based on selected color."""
        text_color = 'white' if color.lightness() < 128 else 'black'
        self.color_btn.setStyleSheet(
            f"background-color: {color.name()}; "
            f"color: {text_color}; "
            f"border: 1px solid #555; "
            f"border-radius: 3px;"
        )


class PinnedImageWindow(QWidget):
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
                 annotation_history: Optional[List[QPixmap]] = None,
                 history_index: int = -1):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.pixmap = pixmap
        self.selection_rect = selection_rect
        self.annotation_history = annotation_history or []
        self.history_index = history_index
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
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)
        QShortcut(QKeySequence("Space"), self).activated.connect(self.reopen_capture)

    def _get_logical_size(self) -> Tuple[int, int]:
        """Get the logical size of the pixmap (accounting for device pixel ratio)"""
        return (
            int(self.pixmap.width() / self.pixmap.devicePixelRatio()),
            int(self.pixmap.height() / self.pixmap.devicePixelRatio())
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw glow effect expanding outward from the pixmap
        glow_layers = [
            (QColor(0, 0, 0, 80), 1),
            (QColor(0, 0, 0, 60), 2),
            (QColor(0, 0, 0, 40), 3),
            (QColor(0, 0, 0, 20), 4),
            (QColor(0, 0, 0, 10), 5),
        ]

        logical_width, logical_height = self._get_logical_size()

        for color, offset in glow_layers:
            painter.setPen(QPen(color, 1, Qt.PenStyle.SolidLine))
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
        """Reopen capture editor with the annotation history restored"""
        if not (self.annotation_history and self.selection_rect):
            return

        # Get the current annotated screenshot from history
        current_screenshot = self.annotation_history[self.history_index]
        editor = CaptureEditor(current_screenshot)
        editor.start_pos = self.selection_rect.topLeft()
        editor.end_pos = self.selection_rect.bottomRight()

        # Transfer annotation history reference, so close .clear() won't delete data
        editor.history = self.annotation_history
        self.annotation_history = []

        editor.history_index = self.history_index
        editor.screenshot = editor.history[editor.history_index].copy()

        # Keep reference to prevent garbage collection
        app = QApplication.instance()
        app.capture_editor = editor

        editor.show()
        editor.create_toolbar()
        logger.debug("Reopened capture editor from pinned window")

        self.close()

    def closeEvent(self, event):
        """Clean up and remove from pinned windows list"""
        # Remove this window from the application's pinned windows list
        app = QApplication.instance()
        if hasattr(app, 'pinned_windows') and self in app.pinned_windows:
            app.pinned_windows.remove(self)
            logger.info(f"Pinned window closed. Remaining: {len(app.pinned_windows)}")

        # Clean up timers
        if hasattr(self, 'opacity_timer'):
            self.opacity_timer.stop()

        # Clear resources to release memory
        self.annotation_history.clear()
        self.pixmap = None

        event.accept()


class CaptureEditor(QWidget):
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

    def __init__(self, screenshot: QPixmap):
        super().__init__()
        self.screenshot = screenshot.copy()

        # Window setup
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)

        screens = QApplication.screens()
        if screens:
            min_x, min_y, max_x, max_y = get_virtual_desktop_bounds(screens)
            
            virtual_width = max_x - min_x + 1
            virtual_height = max_y - min_y + 1
            
            # Set geometry to cover the entire desktop
            self.setGeometry(min_x, min_y, virtual_width, virtual_height)
            logger.debug(f"CaptureEditor geometry set to virtual desktop: {min_x}, {min_y}, {virtual_width}x{virtual_height}")
        else:
            # Fallback to primary screen if no screens found
            screen = QApplication.primaryScreen()
            if screen:
                full_geometry = screen.geometry()
                self.setGeometry(full_geometry)
        
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.setMouseTracking(True)

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

        # Drawing state
        self.drawing = False
        self.annotation_active = False
        self.last_point = QPoint()
        self.draw_start_point = QPoint()
        self.pen_color = DEFAULT_PEN_COLOR
        self.pen_width = DEFAULT_PEN_WIDTH
        self.font_size = DEFAULT_FONT_SIZE
        self.draw_mode = "pen"
        self.preview_rect: Optional[QRect] = None
        self.preview_line: Optional[Tuple[QPoint, QPoint]] = None

        # Text input state
        self.text_input: Optional[QLineEdit] = None
        self.text_input_pos: Optional[QPoint] = None

        # History for undo/redo
        self.history: List[QPixmap] = []
        self.history_index = -1
        self.max_history = MAX_HISTORY

        # Toolbar
        self.toolbar: Optional[FloatingToolbar] = None

        self.save_annotation_state()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.screenshot)

        self._paint_preview(painter)

        if self.start_pos is not None and self.end_pos is not None:
            selection_rect = QRect(self.start_pos, self.end_pos).normalized()
            self._paint_overlay_around_selection(painter, selection_rect)
            self._paint_selection_border(painter, selection_rect)
        else:
            painter.fillRect(self.rect(), OVERLAY_COLOR)

    def _paint_preview(self, painter: QPainter):
        """Paint preview for rectangle/line drawing modes"""
        if self.preview_rect and self.draw_mode == "rectangle":
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(self.pen_color.red(),
                                   self.pen_color.green(),
                                   self.pen_color.blue(), 50))
            painter.drawRect(self.preview_rect)

        if self.preview_line and self.draw_mode == "line":
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(self.preview_line[0], self.preview_line[1])

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
        border_width = 3 if not self.selecting else 2
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

    def get_resize_edge(self, pos: QPoint, rect: QRect) -> Optional[str]:
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

    def get_resize_cursor(self, edge: str) -> Qt.CursorShape:
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

    def mousePressEvent(self, event):
        pos = event.pos()

        if event.button() == Qt.MouseButton.LeftButton:
            # Handle left click - can start selection or interact with existing selection
            if self.start_pos and self.end_pos and not self.selecting:
                self._handle_click_on_existing_selection(pos)
            else:
                # Start new selection
                self.start_pos = pos
                self.end_pos = pos
                self.selecting = True

        elif event.button() == Qt.MouseButton.RightButton:
            # Right click always initiates drawing/annotation (if selection exists)
            if self.start_pos and self.end_pos:
                self._start_drawing_or_annotate(pos)

    def _handle_click_on_existing_selection(self, pos: QPoint):
        """Handle clicks when a selection already exists"""
        selection_rect = QRect(self.start_pos, self.end_pos).normalized()

        # Check for resize handle click (only when not in annotation mode)
        if not self.annotation_active:
            resize_edge = self.get_resize_edge(pos, selection_rect)
            if resize_edge:
                self.resizing = True
                self.resize_edge = resize_edge
                return

        # Check if click is for annotation or selection manipulation
        if self.annotation_active or not selection_rect.contains(pos):
            self._start_drawing_or_annotate(pos)
        else:
            # Start dragging the selection
            self.dragging_selection = True
            self.drag_offset = pos - selection_rect.topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _start_drawing_or_annotate(self, pos: QPoint):
        """Start drawing or place text annotation based on draw mode"""
        if self.draw_mode == "text":
            self._add_text_annotation(pos)
        else:
            self.drawing = True
            self.last_point = pos
            self.draw_start_point = pos

    def _update_cursor(self, pos):
        """Update cursor based on position relative to selection"""
        if self.annotation_active:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        selection_rect = QRect(self.start_pos, self.end_pos).normalized()
        resize_edge = self.get_resize_edge(pos, selection_rect)

        if resize_edge:
            self.setCursor(self.get_resize_cursor(resize_edge))
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

    def mouseMoveEvent(self, event):
        if self.resizing:
            self._apply_resize(event.pos().x(), event.pos().y())
            self.position_toolbar()
            self.update()
        elif self.dragging_selection:
            selection_rect = QRect(self.start_pos, self.end_pos).normalized()
            width = selection_rect.width()
            height = selection_rect.height()
            new_top_left = event.pos() - self.drag_offset

            new_x = max(0, min(new_top_left.x(), self.width() - width))
            new_y = max(0, min(new_top_left.y(), self.height() - height))

            self.start_pos = QPoint(new_x, new_y)
            self.end_pos = QPoint(new_x + width, new_y + height)
            self.position_toolbar()
            self.update()
        elif self.drawing and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)):
            if self.draw_mode == "pen":
                painter = QPainter(self.screenshot)
                pen = QPen(self.pen_color, self.pen_width,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(self.last_point, event.pos())
                self.last_point = event.pos()
                self.update()
            elif self.draw_mode == "rectangle":
                self.preview_rect = QRect(self.draw_start_point, event.pos()).normalized()
                self.update()
            elif self.draw_mode == "line":
                self.preview_line = (self.draw_start_point, event.pos())
                self.update()
        elif self.selecting:
            self.end_pos = event.pos()
            self.update()
        elif self.start_pos and self.end_pos:
            self._update_cursor(event.pos())

    def _add_text_annotation(self, pos: QPoint):
        """Add text annotation at the given position"""
        # Create a text input field at the clicked position
        if self.text_input:
            self._finalize_text_input()

        self.text_input_pos = pos
        self.text_input = QLineEdit(self)

        # Style the text input
        font = QFont("Arial", self.font_size)
        font.setBold(True)
        self.text_input.setFont(font)

        # Calculate text color brightness to set contrasting background
        brightness = self.pen_color.lightness()
        bg_color = "rgba(255, 255, 255, 180)" if brightness < 128 else "rgba(0, 0, 0, 180)"
        text_color = self.pen_color.name()

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
        self.text_input.returnPressed.connect(self._finalize_text_input)
        self.text_input.editingFinished.connect(self._finalize_text_input)

    def wheelEvent(self, event):
        """Handle mouse wheel events for font size adjustment when text input is active"""
        # Check if mouse is over the toolbar - if so, let toolbar handle the event
        if self.toolbar and self.toolbar.geometry().contains(event.position().toPoint()):
            super().wheelEvent(event)
            return

        # Only handle wheel events when text input is active
        if self.text_input and self.text_input.isVisible():
            # Get wheel delta (positive = scroll up, negative = scroll down)
            delta = event.angleDelta().y()

            # Adjust font size (scroll up = larger, scroll down = smaller)
            if delta > 0:
                self.font_size = min(72, self.font_size + 2)  # Max font size: 72
            else:
                self.font_size = max(8, self.font_size - 2)   # Min font size: 8

            # Update the text input font immediately
            font = QFont("Arial", self.font_size)
            font.setBold(True)
            self.text_input.setFont(font)
            self.text_input.adjustSize()

            event.accept()  # Event handled
        else:
            super().wheelEvent(event)

    def _finalize_text_input(self):
        """Finalize the text input and draw it on the screenshot"""
        if not self.text_input or not self.text_input_pos:
            return

        text = self.text_input.text()

        if text:
            painter = QPainter(self.screenshot)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            # Set up font - must match exactly what we used in the input
            font = QFont("Arial", self.font_size)
            font.setBold(True)
            painter.setFont(font)

            # Set up pen for text
            painter.setPen(self.pen_color)

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

            self.save_annotation_state()
            self.update()

        # Clean up
        self.text_input.deleteLater()
        self.text_input = None
        self.text_input_pos = None

    def _finalize_drawing(self, end_pos):
        """Finalize drawing operation and save to screenshot"""
        painter = QPainter(self.screenshot)

        if self.draw_mode == "rectangle":
            pen = QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(QColor(self.pen_color.red(),
                                   self.pen_color.green(),
                                   self.pen_color.blue(), 50))
            rect = QRect(self.draw_start_point, end_pos).normalized()
            painter.drawRect(rect)
            self.preview_rect = None
        elif self.draw_mode == "line":
            pen = QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(self.draw_start_point, end_pos)
            self.preview_line = None
        # Pen mode already draws directly, no finalization needed

        painter.end()
        self.save_annotation_state()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton or event.button() == Qt.MouseButton.RightButton:
            if self.resizing:
                self.resizing = False
                self.resize_edge = None
            elif self.dragging_selection:
                self.dragging_selection = False
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.drawing:
                self._finalize_drawing(event.pos())
                self.drawing = False
            elif self.selecting:
                self.selecting = False
                self.end_pos = event.pos()

                selection_rect = QRect(self.start_pos, self.end_pos).normalized()
                if selection_rect.width() > MIN_VALID_RECT and selection_rect.height() > MIN_VALID_RECT:
                    self.start_pos = selection_rect.topLeft()
                    self.end_pos = selection_rect.bottomRight()
                    self.create_toolbar()
                    self.update()

    def keyPressEvent(self, event):
        key = event.key()

        # Handle Escape key - special case with nested logic
        if key == Qt.Key.Key_Escape:
            self._handle_escape_key()
            return

        # Handle arrow keys for selection movement
        arrow_keys = [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]
        if key in arrow_keys and self.start_pos and self.end_pos:
            self._handle_arrow_key_movement(event)
            return

        # Handle number keys for toolbar shortcuts (1-9)
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9 and self.toolbar:
            button_index = key - Qt.Key.Key_1
            if button_index < len(self.toolbar.button_actions):
                self.toolbar.button_actions[button_index]()
            return

        # Handle keyboard shortcuts with Ctrl modifier
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._handle_ctrl_shortcuts(key):
                return

        super().keyPressEvent(event)

    def _handle_escape_key(self):
        """Handle Escape key press - cancel text input or annotation mode, or close"""
        # If text input is active, cancel it
        if self.text_input:
            self.text_input.deleteLater()
            self.text_input = None
            self.text_input_pos = None
            return

        if self.annotation_active:
            self.annotation_active = False
            if self.toolbar:
                self.toolbar.pen_btn.setChecked(False)
                self.toolbar.rect_btn.setChecked(False)
                self.toolbar.line_btn.setChecked(False)
                self.toolbar.text_btn.setChecked(False)
            self.update()
        else:
            self.close()

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
        self.position_toolbar()
        self.update()

    def _handle_ctrl_shortcuts(self, key) -> bool:
        """
        Handle Ctrl+key shortcuts.

        Returns True if the shortcut was handled, False otherwise.
        """
        # Shortcuts that require selection
        if self.start_pos and self.end_pos:
            shortcuts = {
                Qt.Key.Key_S: self.save_to_file,
                Qt.Key.Key_C: self.copy_to_clipboard,
                Qt.Key.Key_T: self.pin_to_display,
            }
            if key in shortcuts:
                shortcuts[key]()
                return True

        # Shortcuts that work without selection
        global_shortcuts = {
            Qt.Key.Key_Z: self.undo_action,
            Qt.Key.Key_Y: self.redo_action,
        }
        if key in global_shortcuts:
            global_shortcuts[key]()
            return True

        return False

    def create_toolbar(self):
        """Create and show the floating toolbar"""
        if not self.toolbar:
            self.toolbar = FloatingToolbar(self)
            self.position_toolbar()
            self.toolbar.show()

    def position_toolbar(self):
        """Position toolbar at bottom right of selection area (in parent coordinates)"""
        if self.toolbar and self.start_pos and self.end_pos:
            selection_rect = QRect(self.start_pos, self.end_pos).normalized()
            # Align to right side, position below selection
            toolbar_x = selection_rect.right() - self.toolbar.width()
            toolbar_y = selection_rect.bottom() + 5

            # Keep toolbar on screen
            toolbar_x = max(0, min(toolbar_x, self.width() - self.toolbar.width()))
            toolbar_y = min(toolbar_y, self.height() - self.toolbar.height())

            # Move toolbar (it's a child widget, so coordinates are relative to parent)
            self.toolbar.move(toolbar_x, toolbar_y)
            self.toolbar.raise_()  # Keep it on top of other child widgets

    def set_draw_mode(self, mode):
        """Set the drawing mode and toggle annotation"""
        if not self.toolbar:
            return

        # Map modes to their corresponding buttons
        buttons = {
            "pen": self.toolbar.pen_btn,
            "rectangle": self.toolbar.rect_btn,
            "line": self.toolbar.line_btn,
            "text": self.toolbar.text_btn
        }

        current_btn = buttons[mode]
        is_activating = current_btn.isChecked()

        if is_activating:
            # Activate the selected mode
            self.draw_mode = mode
            self.annotation_active = True
            # Uncheck all other buttons
            for m, btn in buttons.items():
                if m != mode:
                    btn.setChecked(False)
        else:
            # Deactivate the mode
            self.annotation_active = False
            current_btn.setChecked(False)

    def update_pen_width(self, value):
        """Update pen width when slider changes"""
        self.pen_width = value

    def choose_color(self):
        """Open color picker dialog"""
        color = QColorDialog.getColor(self.pen_color, self, "Choose Pen Color")
        if color.isValid():
            self.pen_color = color
            if self.toolbar:
                self.toolbar.update_color_button(self.pen_color)

    def save_annotation_state(self):
        """Save current screenshot state to history"""
        # Remove any states after current index (for redo)
        self.history = self.history[:self.history_index + 1]

        # Add new state
        self.history.append(self.screenshot.copy())
        self.history_index += 1

        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_index -= 1

    def undo_action(self):
        """Undo last annotation"""
        if self.history_index > 0:
            self.history_index -= 1
            self.screenshot = self.history[self.history_index].copy()
            self.update()

    def redo_action(self):
        """Redo annotation"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.screenshot = self.history[self.history_index].copy()
            self.update()

    def _scale_rect(self, rect: QRect) -> QRect:
        """
        Scale a rectangle by device pixel ratio for high DPI displays.
        Note: Only use this when directly accessing pixmap pixel data (like copy).
        When drawing with QPainter on a pixmap with devicePixelRatio set,
        Qt automatically handles the scaling, so use logical coordinates.
        """
        if self.screenshot.devicePixelRatio() <= 1.0:
            return rect
        return QRect(
            int(rect.x() * self.screenshot.devicePixelRatio()),
            int(rect.y() * self.screenshot.devicePixelRatio()),
            int(rect.width() * self.screenshot.devicePixelRatio()),
            int(rect.height() * self.screenshot.devicePixelRatio())
        )

    def _get_cropped_selection(self) -> Tuple[Optional[QPixmap], Optional[QRect]]:
        """
        Get the cropped annotated screenshot from current selection.

        Returns:
            Tuple of (cropped_pixmap, selection_rect) or (None, None) if invalid.
        """
        result: Tuple[Optional[QPixmap], Optional[QRect]] = (None, None)
        if self.start_pos and self.end_pos:
            selection_rect = QRect(self.start_pos, self.end_pos).normalized()
            if selection_rect.width() > MIN_VALID_RECT and selection_rect.height() > MIN_VALID_RECT:
                # Scale the selection rect for high DPI displays
                scaled_rect = self._scale_rect(selection_rect)
                cropped = self.screenshot.copy(scaled_rect)
                # Preserve the device pixel ratio on the cropped pixmap
                cropped.setDevicePixelRatio(self.screenshot.devicePixelRatio())
                result = (cropped, selection_rect)
        return result

    def save_to_file(self):
        """Save the current selection to a file"""
        cropped, _ = self._get_cropped_selection()
        self.close()
        if cropped:
            # Open save dialog
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                "Save Screenshot",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;All Files (*)"
            )
            if file_path:
                try:
                    if cropped.save(file_path):
                        logger.info(f"Screenshot saved to {file_path}")
                    else:
                        logger.error(f"Failed to save screenshot to {file_path}")
                except Exception as e:
                    logger.error(f"Error saving screenshot: {e}")

    def copy_to_clipboard(self):
        """Copy the current selection to clipboard"""
        cropped, _ = self._get_cropped_selection()
        self.close()
        if cropped:
            try:
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setPixmap(cropped)
                    logger.info("Screenshot copied to clipboard")
                else:
                    logger.error("Clipboard not available")
            except Exception as e:
                logger.error(f"Error copying to clipboard: {e}")

    def pin_to_display(self):
        """Pin the current selection"""
        cropped, selection_rect = self._get_cropped_selection()
        if cropped:
            pinned_window = PinnedImageWindow(
                cropped,
                position=selection_rect.topLeft(),
                selection_rect=selection_rect,
                annotation_history=self.history,
                history_index=self.history_index
            )
            # Transfer annotation history reference, so close .clear() won't delete data
            self.history = []
            pinned_window.show()

            # Keep reference to prevent garbage collection
            app = QApplication.instance()
            if not hasattr(app, 'pinned_windows'):
                app.pinned_windows = []
            app.pinned_windows.append(pinned_window)
            logger.info(f"Screenshot pinned to screen. Total pinned: {len(app.pinned_windows)}")
        self.close()

    def closeEvent(self, event):
        """Clean up toolbar and release resources when closing"""
        if self.toolbar:
            self.toolbar.close()

        # Clear resources to release memory
        self.history.clear()
        self.screenshot = None

        logger.debug("Capture editor closed")
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
        shortcut_label = QLabel("Shortcut: {}".format(GLOBAL_HOTKEY))
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
            "6. On pinned: scroll to change transparency"
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
