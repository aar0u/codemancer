import sys
import os
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextEdit, QLineEdit,
                             QLabel, QPushButton)
from PyQt6.QtCore import QTimer, Qt, QRegularExpression
from PyQt6.QtGui import (QTextCharFormat, QColor,
                         QTextCursor, QSyntaxHighlighter, QFont)

class SimpleTailGUI(QWidget):
    def __init__(self, log_file_path):
        super().__init__()
        self.log_file_path = log_file_path
        self.max_lines = 1000
        self.highlight_keyword = "ERROR"
        self.last_position = 0
        self.display_lines = []  # Store lines in memory like Java version
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
                print(f"Dragged in file: {file_path}")
                self.log_file_path = file_path
                self.last_position = 0
                self.display_lines = []
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
        control_layout.addWidget(QLabel("Highlight:"))
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

    def read_last_lines(self, file_path, num_lines):
        """Read last N lines from file efficiently (similar to Java implementation)"""
        result = []
        try:
            with open(file_path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                file_length = f.tell()
                if file_length == 0:
                    return result

                buffer_size = 8192
                pos = file_length
                lines_found = 0
                current_line = []

                while pos > 0 and lines_found < num_lines:
                    read_size = min(buffer_size, pos)
                    pos -= read_size
                    f.seek(pos)
                    chunk = f.read(read_size)

                    # Process buffer from end to beginning
                    for i in range(len(chunk) - 1, -1, -1):
                        byte_val = chunk[i:i+1]
                        if lines_found >= num_lines:
                            break

                        # Check for newline
                        if byte_val == b'\n':
                            # Add the current line even if empty
                            try:
                                line_bytes = b''.join(reversed(current_line))
                                # Clean NUL characters from UTF-16 files read as UTF-8
                                line_str = line_bytes.decode('utf-8', errors='replace').replace('\u0000', '').replace('\r', '')
                                result.insert(0, line_str)
                            except:
                                result.insert(0, '')
                            current_line = []
                            lines_found += 1
                        elif byte_val != b'\r' and byte_val != b'\x00':  # Skip CR and NUL
                            current_line.append(byte_val)

                # Handle last line if exists and not reached line limit
                if current_line and lines_found < num_lines:
                    try:
                        line_bytes = b''.join(reversed(current_line))
                        line_str = line_bytes.decode('utf-8', errors='replace').replace('\u0000', '').replace('\r', '')
                        result.insert(0, line_str)
                    except:
                        result.insert(0, '')

        except Exception as e:
            print(f"[GUI] Error reading last lines: {e}")

        return result

    def update_max_lines(self):
        """Update max lines in real time"""
        try:
            new_lines = int(self.line_count_input.text())
            if new_lines > 0:
                self.max_lines = new_lines
                print(f"[GUI] Max lines set to: {self.max_lines}")
                # Immediately reload to apply new line limit
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

        # Check if file exists
        if not os.path.exists(self.log_file_path):
            return

        start_time = time.time()

        try:
            # Get current file size
            file_size = os.path.getsize(self.log_file_path)

            # Detect file truncation (file was rotated or cleared)
            file_truncated = self.last_position > file_size

            if force_reload or self.last_position == 0 or file_truncated:
                # Full reload: read last N lines efficiently
                self.display_lines = self.read_last_lines(self.log_file_path, self.max_lines)
                self.last_position = file_size
                new_lines_count = len(self.display_lines)
            else:
                # Incremental read: only read new content
                with open(self.log_file_path, 'rb') as f:
                    f.seek(self.last_position)
                    new_bytes = f.read()
                    self.last_position = f.tell()

                    if not new_bytes:
                        return  # No update

                    # Decode with error handling and clean NUL characters
                    new_content = new_bytes.decode('utf-8', errors='replace').replace('\u0000', '')

                    # Split into lines (keep empty segments with -1 limit)
                    new_lines = new_content.split('\n')
                    new_lines_count = len(new_lines)

                    # Merge lines: if chunk doesn't start with newline, first segment continues last line
                    if self.display_lines and new_lines:
                        # Merge first new segment with last existing line
                        self.display_lines[-1] = self.display_lines[-1] + new_lines[0]
                        # Add remaining new lines
                        if len(new_lines) > 1:
                            self.display_lines.extend(new_lines[1:])
                    else:
                        self.display_lines.extend(new_lines)

                    # Trim to max_lines
                    if len(self.display_lines) > self.max_lines:
                        self.display_lines = self.display_lines[-self.max_lines:]

            # Build final text from display_lines
            final_text = '\n'.join(self.display_lines)

            # Set text, highlighter will reapply
            self.log_display.setText(final_text)

            # Auto scroll to bottom
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()
            )

            # Performance logging
            update_time = int((time.time() - start_time) * 1000)
            total_lines = len(self.display_lines)
            print(f"[GUI] Loaded: {new_lines_count} lines | Total: {total_lines} lines | Time: {update_time}ms")

        except Exception as e:
            error_msg = f"Error reading file: {e}"
            self.log_display.setText(error_msg)
            print(f"[GUI] {error_msg}", file=sys.stderr)

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
        format.setFontWeight(QFont.Weight.Bold)
        for keyword in keywords:
            if keyword:
                pattern = QRegularExpression(QRegularExpression.escape(keyword), QRegularExpression.PatternOption.CaseInsensitiveOption)
                self.highlighting_rules.append((pattern, format))
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart()
                length = match.capturedLength()
                self.setFormat(start, length, format)

if __name__ == '__main__':
    log_path = sys.argv[1] if len(sys.argv) > 1 else "sample.log"
    app = QApplication(sys.argv)
    window = SimpleTailGUI(log_path)
    window.show()
    sys.exit(app.exec())
