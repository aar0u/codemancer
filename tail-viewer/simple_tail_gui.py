import sys
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTextEdit, QLineEdit, 
                             QLabel, QPushButton)
from PyQt5.QtCore import QTimer, Qt, QRegExp
from PyQt5.QtGui import (QTextCharFormat, QColor, 
                         QTextCursor, QSyntaxHighlighter)

class SimpleTailGUI(QWidget):
    def __init__(self, log_file_path):
        super().__init__()
        self.log_file_path = log_file_path
        self.max_lines = 1000
        self.highlight_keyword = "ERROR"
        self.last_position = 0
        self.setWindowTitle("Tail GUI")
        self.setGeometry(100, 100, 800, 600)

        self.setAcceptDrops(True)
        self.init_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_log_content)
        self.timer.start(500)
        self.update_log_content()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.isfile(file_path):
                self.log_file_path = file_path
                self.last_position = 0
                self.update_log_content(force_reload=True)

    def init_ui(self):
        """Initialize UI layout"""
        main_layout = QVBoxLayout(self)

        # Top control panel
        control_layout = QHBoxLayout()
        
        # Max lines setting
        control_layout.addWidget(QLabel("Lines:"))
        self.line_count_input = QLineEdit(str(self.max_lines))
        self.line_count_input.setFixedWidth(80)
        self.line_count_input.returnPressed.connect(self.update_max_lines)
        control_layout.addWidget(self.line_count_input)
        
        # Keyword highlight setting
        control_layout.addWidget(QLabel("Hightlight:"))
        self.keyword_input = QLineEdit(self.highlight_keyword)
        self.keyword_input.setFixedWidth(120)
        self.keyword_input.returnPressed.connect(self.update_highlighter)
        
        # Button to apply changes
        self.update_btn = QPushButton("Apply")
        self.update_btn.clicked.connect(lambda: [
            self.update_max_lines(), 
            self.update_highlighter()
        ])
        
        control_layout.addWidget(self.keyword_input)
        control_layout.addWidget(self.update_btn)
        control_layout.addStretch(1)

        main_layout.addLayout(control_layout)

        # Log display area
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        main_layout.addWidget(self.log_display)
        
        # Initialize highlighter
        self.highlighter = KeywordHighlighter(self.log_display.document(), self.highlight_keyword)

    # Core logic methods

    def update_max_lines(self):
        """Update max lines in real time"""
        try:
            new_lines = int(self.line_count_input.text())
            if new_lines > 0:
                self.max_lines = new_lines
                print(f"Max lines set to: {self.max_lines}")
                # 立即重新加载以应用新的行数限制
                self.update_log_content(force_reload=True) 
        except ValueError:
            # If not a number, restore previous value
            self.line_count_input.setText(str(self.max_lines))

    def update_highlighter(self):
        """Update highlight keywords, supports comma separated"""
        new_keyword = self.keyword_input.text().strip()
        if new_keyword:
            self.highlight_keyword = new_keyword
            # Split by comma and remove spaces
            keywords = [k.strip() for k in new_keyword.split(',') if k.strip()]
            self.highlighter.set_keywords(keywords)
            print(f"Highlight keywords set to: {keywords}")

    def update_log_content(self, force_reload=False):
        """Read and display log file content, limit lines. Pause when text is selected."""
        # Pause refresh if text is selected, show status in title
        if self.log_display.textCursor().hasSelection():
            self.setWindowTitle("Tail GUI [PAUSED]")
            return
        else:
            self.setWindowTitle("Tail GUI")
        try:
            # Open file and read
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                # If force reload or first load, read from start
                if force_reload or self.last_position == 0:
                    f.seek(0)
                    content = f.read()
                    self.last_position = f.tell()
                else:
                    # Only read new content (tail -f)
                    f.seek(self.last_position)
                    new_data = f.read()
                    self.last_position = f.tell()
                    
                    if not new_data:
                        return # No update

                    content = self.log_display.toPlainText() + new_data

                # 按行分割，应用最大行数限制
                lines = content.split('\n')
                if len(lines) > self.max_lines:
                    # Keep only last max_lines lines
                    lines = lines[-self.max_lines:]
                
                final_text = '\n'.join(lines)
                
                # Set text, highlighter will reapply
                self.log_display.setText(final_text)
                
                # Auto scroll to bottom
                self.log_display.verticalScrollBar().setValue(
                    self.log_display.verticalScrollBar().maximum()
                )

        except IOError as e:
            self.log_display.setText(f"Error reading file: {e}")

class KeywordHighlighter(QSyntaxHighlighter):
    """Custom syntax highlighter for keywords"""
    def __init__(self, parent, keyword):
        super().__init__(parent)
        self.highlighting_rules = []
        if isinstance(keyword, str):
            keywords = [k.strip() for k in keyword.split(',') if k.strip()]
        else:
            keywords = keyword
        self.set_keywords(keywords)

    def set_keywords(self, keywords):
        """Set new keywords and reinitialize highlight rules"""
        self.highlighting_rules.clear()
        format = QTextCharFormat()
        format.setForeground(QColor("#FF5733"))
        format.setFontWeight(75)
        for keyword in keywords:
            if keyword:
                pattern = QRegExp(QRegExp.escape(keyword), Qt.CaseInsensitive)
                self.highlighting_rules.append((pattern, format))
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            index = pattern.indexIn(text, 0)
            while index >= 0:
                length = pattern.matchedLength()
                self.setFormat(index, length, format)
                index = pattern.indexIn(text, index + length)

if __name__ == '__main__':
    log_path = sys.argv[1] if len(sys.argv) > 1 else "sample.log"
    app = QApplication(sys.argv)
    window = SimpleTailGUI(log_path)
    window.show()
    sys.exit(app.exec_())
