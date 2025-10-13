import os, sys
from PyQt6 import QtWidgets, QtGui
from PyQt6.QtCore import Qt

def load_names():
    try:
        with open("names.txt", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        app = QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(None, "Error", f"Failed to load list:\n{e}")
        sys.exit(1)

names = load_names()

class CheckboxListApp(QtWidgets.QWidget):
    BASE_STYLE = "QCheckBox { font-size: 18px; min-height: 32px; }"
    RED_STYLE = BASE_STYLE[:-1] + "; color: red; }"
    def __init__(self):
        super().__init__()
        self.x_states = {}  # Track X state for each checkbox
        self.setWindowTitle("Huddle Helper")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.create_title_bar())
        label = QtWidgets.QLabel("Names")
        self.layout.addWidget(label)
        self.checkboxes = []
        for name in names:
            row_widget, cb = self.create_checkbox_row(name)
            self.layout.addWidget(row_widget)
            self.checkboxes.append(cb)
        self.setLayout(self.layout)
        self.adjustSize()
        min_width = 180
        self.setMinimumWidth(min_width)
        self.setFixedSize(max(self.size().width(), min_width), self.size().height())
        # Enable window dragging
        self.oldPos = None
    def create_title_bar(self):
        title_bar = QtWidgets.QWidget()
        title_layout = QtWidgets.QHBoxLayout(title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_label = QtWidgets.QLabel("Huddle Helper")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        # Minimize button
        min_btn = QtWidgets.QPushButton()
        min_btn.setFixedSize(28, 28)
        min_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarMinButton))
        min_btn.setStyleSheet("QPushButton { border: none; background: transparent; border-radius: 6px; } QPushButton:hover { background: #40a9ff; color: white; }")
        min_btn.clicked.connect(self.showMinimized)
        title_layout.addWidget(min_btn)
        # Close button
        close_btn = QtWidgets.QPushButton()
        close_btn.setFixedSize(28, 28)
        close_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close_btn.setStyleSheet("QPushButton { border: none; background: transparent; border-radius: 6px; } QPushButton:hover { background: #ff4d4f; color: white; }")
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        title_bar.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f0f0f0, stop:1 #e6f7ff); border-bottom: 1px solid #ccc;")
        return title_bar
    def create_checkbox_row(self, name):
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        cb = QtWidgets.QCheckBox(name)
        cb.setStyleSheet(self.BASE_STYLE)
        row_layout.addWidget(cb)
        row_widget.setStyleSheet("QWidget:hover { background: #e6f7ff; }")
        row_widget.mousePressEvent = lambda event, c=cb, n=name: self.handle_checkbox_mouse(event, c, n)
        self.x_states[name] = False
        return row_widget, cb
    def handle_checkbox_mouse(self, event, cb, name):
        if event.button() == Qt.MouseButton.LeftButton:
            cb.toggle()
            self.x_states[name] = False
            cb.setText(name)
            cb.setStyleSheet(self.BASE_STYLE)
        elif event.button() == Qt.MouseButton.RightButton:
            self.x_states[name] = not self.x_states[name]
            if self.x_states[name]:
                cb.setChecked(False)
                cb.setText(f"{name}  ✗")
                cb.setStyleSheet(self.RED_STYLE)
            else:
                cb.setText(name)
                cb.setStyleSheet(self.BASE_STYLE)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.oldPos = event.globalPosition().toPoint()
    def mouseMoveEvent(self, event):
        if self.oldPos:
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPosition().toPoint()
    def mouseReleaseEvent(self, event):
        self.oldPos = None

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    # Find icon path for both script and exe
    if getattr(sys, 'frozen', False):
        # If running as exe
        icon_path = os.path.join(sys._MEIPASS, "meeting.ico")
    else:
        # If running as script
        icon_path = os.path.abspath("meeting.ico")
    app.setWindowIcon(QtGui.QIcon(icon_path))
    window = CheckboxListApp()
    window.show()
    sys.exit(app.exec())
