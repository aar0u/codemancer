## Project Overview

TailViewer is a cross-platform log file viewer (similar to `tail -f`) with both GUI and CLI modes. It monitors log files in real-time with keyword highlighting.

**Two implementations:**
- `TailViewer.java` - Java Swing GUI (production version, supports CLI mode)
- `tail.py` - Python standard-library `tkinter` GUI and CLI (alternative implementation)

## Build & Run

### Java Version

```bash
# Build JAR
gen-jar.bat

# Run GUI
java -jar dist/TailViewer.jar [logfile]

# Run CLI (via wrapper scripts)
./tail.sh [--gui] [-n N|--lines=N] [logfile]
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
python3 tail.py [logfile]
```

### Generate Test Logs

```bash
gen-log.bat [logfile]  # Appends random log entries every 1 second
```

## Architecture Highlights

### File Reading (Both Versions)
- Uses file position tracking (`lastPosition`) to read only new content
- Detects file replacement and truncation (handles log rotation)
- Reads last N lines efficiently by reading file backwards in 8KB chunks
- Removes NUL characters (`\u0000`) from decoded text

### Line Management
- Maintains an in-memory buffer of the requested last N lines (default 10; stdin GUI uses 50,000)
- **Line merging:** When new content doesn't start with newline, first segment is merged with last existing line
- Trims buffer when exceeding max lines

### UI Features
- Auto-pause when text is selected (title shows "[PAUSED]")
- File loading through the "Open file" button
- Real-time pattern-based highlighting
- Auto-scroll to bottom
- Update interval: 500ms

### Java CLI Mode
- Default mode; use `--gui` for the Swing viewer
- Uses ANSI color codes for terminal highlighting
- Same tailing logic as GUI mode

## Key Implementation Details

- Both implementations decode UTF-8 with replacement and remove NUL characters.
- Both merge an incremental fragment into the preceding unterminated line.

**GraalVM Native Image:**
- Metadata: `ni-config/reachability-metadata.json`
- Requires `--initialize-at-run-time=sun.awt.Win32FontManager`
- Sets `java.home` property for font loading (TailViewer.java:403-414)

## Development Notes

- Java version uses IntelliJ IDEA (`.idea/`, `tail-viewer.iml`)
- Compiled output: `dist/` directory
- Default test file: `sample.log`
- `tail.sh` runs the Java CLI by default
