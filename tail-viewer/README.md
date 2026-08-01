## Project Overview

TailViewer is a cross-platform log file viewer (similar to `tail -f`) with both GUI and CLI modes. It monitors log files in real-time with keyword highlighting.

**Two implementations:**
- `TailViewer.java` - Java Swing GUI (production version, supports CLI mode)
- `simple_tail_gui.py` - Python standard-library `tkinter` GUI (alternative implementation)

## Build & Run

### Java Version

```bash
# Build JAR
gen-jar.bat

# Run GUI
java -jar dist/TailViewer.jar [logfile]

# Run CLI (via wrapper scripts)
tail.bat [logfile] [--lines N] [--keywords word1,word2]
tail.sh [logfile] [--lines N] [--keywords word1,word2]
```

### GraalVM Native Image

```bash
# Step 1: Generate metadata (interact with UI extensively!)
meta-graal.bat

# Step 2: Build native executable
build-graal.bat
```

**Important:** Always run `meta-graal.bat` before `build-graal.bat` to collect reflection metadata. The GraalVM path is hardcoded in scripts: `D:\dev\_sdks\graalvm-community-openjdk-25+37.1`

### Python Version

```bash
python simple_tail_gui.py [logfile]
```

### Generate Test Logs

```bash
gen-log.bat [logfile]  # Appends random log entries every 1 second
```

## Architecture Highlights

### File Reading (Both Versions)
- Uses file position tracking (`lastPosition`) to read only new content
- Detects file truncation when `lastPosition > fileSize` (handles log rotation)
- Reads last N lines efficiently by reading file backwards in 8KB chunks
- Cleans NUL characters (`\u0000`) for UTF-16 files read as UTF-8

### Line Management
- Maintains in-memory buffer of last N lines (default 1000)
- **Line merging:** When new content doesn't start with newline, first segment is merged with last existing line
- Trims buffer when exceeding max lines

### UI Features
- Auto-pause when text is selected (title shows "[PAUSED]")
- File loading through the "Open file" button
- Real-time keyword highlighting (comma-separated, case-insensitive)
- Auto-scroll to bottom
- Update interval: 1000ms (Java), 500ms (Python)

### Java CLI Mode
- Activated with `--cli` flag
- Uses ANSI color codes for terminal highlighting
- Same tailing logic as GUI mode

## Key Implementation Details

**UTF-16/UTF-8 Handling:**
- Java: TailViewer.java:97, 132
- Python: `simple_tail_gui.py` decodes UTF-8 with replacement and removes NUL characters

**Line Merging Logic:**
- Java: TailViewer.java:287-299
- Python: `simple_tail_gui.py` merges the first segment of each incremental read into the current final line

**GraalVM Native Image:**
- Metadata: `ni-config/reachability-metadata.json`
- Requires `--initialize-at-run-time=sun.awt.Win32FontManager`
- Sets `java.home` property for font loading (TailViewer.java:403-414)

## Development Notes

- Java version uses IntelliJ IDEA (`.idea/`, `tail-viewer.iml`)
- Compiled output: `dist/` directory
- Default test file: `sample.log`
- `tail.bat`/`tail.sh` wrappers force CLI mode by adding `--cli` flag if not present
