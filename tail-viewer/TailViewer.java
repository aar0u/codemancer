import javax.swing.*;
import javax.swing.filechooser.FileNameExtensionFilter;
import javax.swing.text.*;
import java.awt.*;
import java.awt.datatransfer.DataFlavor;
import java.awt.dnd.*;
import java.awt.geom.Rectangle2D;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TailViewer {
    private static final int DEFAULT_MAX_LINES = 10;
    private static final int STDIN_GUI_MAX_LINES = 5_000;
    private static final int CLI_PENDING_MAX_LINES = 1_000;
    private static final int CLI_BATCH_MAX_LINES = 200;
    // Not just a scan-time bound: many highlights measurably slow down scrolling
    // for as long as they stay applied, so this has to stay small.
    private static final int SEARCH_MAX_MATCHES = 200;
    private static final long MAX_INCREMENTAL_READ_BYTES = 64 * 1024;
    private static final int UPDATE_INTERVAL_MS = 500;
    private static final String DEFAULT_LOG_FILE = "sample.log";
    private static final String RESET = "\u001B[0m";

    private static final Map<String, Color> COLORS = Map.of(
            "muted", Color.decode("#4C566A"), "logger", Color.decode("#88C0D0"),
            "quote", Color.decode("#D08770"), "error", Color.decode("#BF616A"),
            "warn", Color.decode("#EBCB8B"), "info", Color.decode("#A3BE8C"),
            "debug", Color.decode("#81A1C1"), "bracket0", Color.decode("#5E81AC"),
            "bracket1", Color.decode("#B48EAD"), "bracket2", Color.decode("#8FBCBB"));
    private static final Map<String, String> ANSI = new HashMap<>();
    private static final String[] BRACKET_COLORS = {"bracket0", "bracket1", "bracket2"};
    private static final Map<String, String> LEVEL_COLORS = Map.of(
            "FATAL", "error", "CRITICAL", "error", "SEVERE", "error", "ERROR", "error",
            "WARNING", "warn", "WARN", "warn", "INFO", "info", "DEBUG", "debug", "TRACE", "muted");
    private static final Pattern LEVEL = Pattern.compile("\\b(FATAL|CRITICAL|ERROR|SEVERE|WARNING|WARN|INFO|DEBUG|TRACE)\\b");
    private static final Pattern LOGGER = Pattern.compile("(?:^|(?<=[\\s\\[]))[A-Za-z_][\\w$]*(?:\\.[A-Za-z_][\\w$]*){2,}(?::\\d+)?\\b");
    private static final Pattern ALERT = Pattern.compile("\\b(failed|failure|exception|timeout|retry|panic|could not)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern TIMESTAMP = Pattern.compile("\\b(?:\\d{4}[-/]\\d{2}[-/]\\d{2}|\\d{1,2}[-/.]\\d{1,2}[-/.]\\d{2,4}|\\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\\d{2,4})[ T]\\d{2}:\\d{2}:\\d{2}(?:[.,:]\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?|\\b\\d{8} \\d{2}:\\d{2}:\\d{2}(?:[.,:]\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?");
    private static final Pattern STACK_TRACE = Pattern.compile("^\\s*(at |Caused by:|\\.\\.\\. \\d+ (more|common frames omitted)|Traceback \\(most recent call last\\)|File \\\"|panic:|goroutine )");
    // Identity-compared: lets getHighlights() double as a live, auto-adjusting match list.
    private static final Highlighter.HighlightPainter SEARCH_HIT_PAINTER = new DefaultHighlighter.DefaultHighlightPainter(Color.decode("#5a5a00"));
    private static final Highlighter.HighlightPainter SEARCH_CURRENT_PAINTER = new DefaultHighlighter.DefaultHighlightPainter(Color.decode("#c07800"));

    static {
        for (Map.Entry<String, Color> entry : COLORS.entrySet()) {
            Color color = entry.getValue();
            ANSI.put(entry.getKey(), String.format("\u001B[38;2;%d;%d;%dm", color.getRed(), color.getGreen(), color.getBlue()));
        }
    }

    private JFrame frame;
    private JTextPane logDisplay;
    private JTextField lineCountInput;
    private JTextField searchInput;
    private JLabel searchStatus;
    private JButton resumeButton;
    private JCheckBox wrapBox;
    private JScrollPane scrollPane;
    private final List<String> displayLines = new ArrayList<>();
    private int searchMatchIndex = -1;
    private Object currentSearchHighlight;
    private int maxLines;
    private String logFilePath;
    private long lastPosition;
    private Object lastFileKey;
    private byte[] lastMarker;
    private javax.swing.Timer timer;
    private javax.swing.Timer searchTimer;
    private boolean needsFullRender;
    private boolean stdinMode;
    private final BlockingQueue<String> stdinLines = new ArrayBlockingQueue<>(CLI_PENDING_MAX_LINES);
    private final AtomicLong stdinSkipped = new AtomicLong();
    private volatile boolean stdinClosed;

    private TailViewer(String logFilePath, int maxLines, boolean stdinMode) {
        this.logFilePath = logFilePath;
        this.maxLines = stdinMode ? STDIN_GUI_MAX_LINES : maxLines;
        this.stdinMode = stdinMode;
    }

    private record Options(String path, int lines, boolean gui) {}
    private record TailResult(List<String> lines, long position) {}
    private record LogResult(List<String> lines, long position, boolean truncated, boolean continuesPreviousLine, boolean dropped, Object fileKey, byte[] marker) {}
    private record AppendedLines(List<String> lines, long position, boolean continuesPreviousLine, long skipped, boolean truncatedCatchup) {
        boolean dropped() { return skipped > 0; }
    }
    private record Span(int start, int end, String color, int priority) {}

    private static Options parseArgs(String[] args) {
        String path = null;
        int lines = DEFAULT_MAX_LINES;
        boolean gui = false;
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            if (arg.equals("--gui")) gui = true;
            else if (arg.equals("-f") || arg.equals("-F") || arg.equals("--follow") || arg.equals("--cli")) { }
            else if (arg.equals("-n") || arg.equals("--lines")) {
                if (++i >= args.length) throw new IllegalArgumentException(arg + " requires a value");
                lines = Integer.parseInt(args[i]);
            } else if (arg.startsWith("-n") && arg.length() > 2) lines = Integer.parseInt(arg.substring(2));
            else if (arg.startsWith("--lines=")) lines = Integer.parseInt(arg.substring(8));
            else if (!arg.startsWith("-")) path = arg;
            else throw new IllegalArgumentException("Unknown option: " + arg);
        }
        if (lines <= 0) throw new IllegalArgumentException("lines must be positive");
        return new Options(path, lines, gui);
    }

    private static TailResult readTailLines(String filePath, int count) throws IOException {
        try (RandomAccessFile file = new RandomAccessFile(filePath, "r")) {
            long fileSize = file.length();
            long position = fileSize;
            if (position == 0) return new TailResult(List.of(), 0);
            Deque<byte[]> chunks = new ArrayDeque<>();
            int newlines = 0;
            while (position > 0 && newlines <= count) {
                int size = (int) Math.min(8192, position);
                position -= size;
                byte[] chunk = new byte[size];
                file.seek(position);
                file.readFully(chunk);
                chunks.addFirst(chunk);
                for (byte b : chunk) if (b == '\n') newlines++;
            }
            ByteArrayOutputStream content = new ByteArrayOutputStream();
            for (byte[] chunk : chunks) content.write(chunk);
            String[] lines = content.toString(StandardCharsets.UTF_8).replace("\0", "").split("\\R");
            int start = Math.max(0, lines.length - count);
            return new TailResult(new ArrayList<>(Arrays.asList(lines).subList(start, lines.length)), fileSize);
        }
    }

    private static byte[] readMarker(RandomAccessFile file, long position) throws IOException {
        int length = (int) Math.min(64, position);
        byte[] marker = new byte[length];
        file.seek(position - length);
        file.readFully(marker);
        return marker;
    }

    private static byte[] readMarker(String path, long position) throws IOException {
        try (RandomAccessFile file = new RandomAccessFile(path, "r")) {
            return readMarker(file, position);
        }
    }

    private static String readUtf8Line(RandomAccessFile file) throws IOException {
        String rawLine = file.readLine();
        return rawLine == null ? null : new String(rawLine.getBytes(StandardCharsets.ISO_8859_1), StandardCharsets.UTF_8).replace("\0", "");
    }

    private static AppendedLines readAppendedLines(String path, long position, long length, int maxLines) throws IOException {
        if (length - position > MAX_INCREMENTAL_READ_BYTES) {
            // Far behind - a real discontinuity, not a bounded in-window skip.
            TailResult tail = readTailLines(path, maxLines);
            return new AppendedLines(tail.lines(), tail.position(), false, 0, true);
        }
        try (RandomAccessFile file = new RandomAccessFile(path, "r")) {
            file.seek(position - 1);
            boolean continuesPreviousLine = file.read() != '\n';
            file.seek(position);
            Deque<String> lines = new ArrayDeque<>();
            long skipped = 0;
            while (file.getFilePointer() < length) {
                String line = readUtf8Line(file);
                if (line == null) break;
                if (lines.size() == maxLines) { lines.removeFirst(); skipped++; }
                lines.addLast(line);
            }
            return new AppendedLines(new ArrayList<>(lines), file.getFilePointer(), continuesPreviousLine && skipped == 0, skipped, false);
        }
    }

    private LogResult readLog(boolean reload, int maxAppendedLines) throws IOException {
        try (RandomAccessFile file = new RandomAccessFile(logFilePath, "r")) {
            BasicFileAttributes attributes = Files.readAttributes(Path.of(logFilePath), BasicFileAttributes.class);
            long length = file.length();
            boolean replaced = lastPosition <= length && ((lastFileKey != null && !Objects.equals(lastFileKey, attributes.fileKey()))
                    || (lastMarker != null && !Arrays.equals(lastMarker, readMarker(file, lastPosition))));
            boolean truncated = lastPosition > length || replaced;
            if (reload || lastPosition == 0 || truncated) {
                TailResult tail = readTailLines(logFilePath, maxLines);
                return new LogResult(tail.lines(), tail.position(), truncated, false, false, attributes.fileKey(), readMarker(file, tail.position()));
            }
            if (lastPosition == length) return new LogResult(List.of(), length, false, false, false, attributes.fileKey(), lastMarker);
            AppendedLines appended = readAppendedLines(logFilePath, lastPosition, length, maxAppendedLines);
            return new LogResult(appended.lines(), appended.position(), appended.truncatedCatchup(), appended.continuesPreviousLine(), appended.dropped(), attributes.fileKey(), readMarker(file, length));
        }
    }

    private static boolean overlaps(int start, int end, List<int[]> ranges) {
        return ranges.stream().anyMatch(range -> start < range[1] && end > range[0]);
    }

    private static void addMatches(String raw, List<Span> spans, Pattern pattern, String color, int priority, int limit, List<int[]> skip, boolean levelColors) {
        Matcher matcher = pattern.matcher(raw);
        int matched = 0;
        while (matcher.find()) {
            if (skip != null && overlaps(matcher.start(), matcher.end(), skip)) continue;
            String spanColor = levelColors ? LEVEL_COLORS.get(matcher.group().toUpperCase()) : color;
            spans.add(new Span(matcher.start(), matcher.end(), spanColor, priority));
            if (limit > 0 && ++matched >= limit) return;
        }
    }

    private static List<Span> computeSpans(String raw) {
        if (STACK_TRACE.matcher(raw).find()) return List.of(new Span(0, raw.length(), "muted", 100));
        List<Span> spans = new ArrayList<>();
        List<int[]> quotes = new ArrayList<>();
        Deque<int[]> brackets = new ArrayDeque<>(); // character, index, depth
        Character quote = null;
        int quoteStart = -1;
        for (int i = 0; i < raw.length(); i++) {
            char ch = raw.charAt(i);
            if (ch == '\\' && i + 1 < raw.length()) { i++; continue; }
            if (quote != null) {
                if (ch == quote) {
                    quotes.add(new int[]{quoteStart, i + 1});
                    spans.add(new Span(quoteStart, quoteStart + 1, "quote", 60));
                    spans.add(new Span(i, i + 1, "quote", 60));
                    quote = null;
                }
                continue;
            }
            if (ch == '\'' || ch == '"') { quote = ch; quoteStart = i; continue; }
            if ("({[".indexOf(ch) >= 0) { brackets.push(new int[]{ch, i, brackets.size()}); continue; }
            if (")}]".indexOf(ch) >= 0) {
                if (!brackets.isEmpty() && matches((char) brackets.peek()[0], ch)) {
                    int[] open = brackets.pop();
                    String color = BRACKET_COLORS[open[2] % BRACKET_COLORS.length];
                    spans.add(new Span(open[1], open[1] + 1, color, 15));
                    spans.add(new Span(i, i + 1, color, 15));
                } else spans.add(new Span(i, i + 1, "error", 15));
            }
        }
        for (int[] open : brackets) spans.add(new Span(open[1], open[1] + 1, "error", 15));
        addMatches(raw, spans, LOGGER, "logger", 20, 1, quotes, false);
        addMatches(raw, spans, ALERT, "error", 30, 0, null, false);
        addMatches(raw, spans, TIMESTAMP, "muted", 40, 0, null, false);
        addMatches(raw, spans, LEVEL, null, 50, 1, null, true);
        return spans;
    }

    private static boolean matches(char open, char close) {
        return (open == '(' && close == ')') || (open == '{' && close == '}') || (open == '[' && close == ']');
    }

    private static String highlightAnsi(String raw) {
        String[] colors = new String[raw.length()];
        int[] priorities = new int[raw.length()];
        Arrays.fill(priorities, -1);
        for (Span span : computeSpans(raw)) for (int i = Math.max(0, span.start()); i < Math.min(raw.length(), span.end()); i++) {
            if (span.priority() >= priorities[i]) { priorities[i] = span.priority(); colors[i] = span.color(); }
        }
        StringBuilder out = new StringBuilder();
        String current = null;
        for (int i = 0; i < raw.length(); i++) {
            if (!Objects.equals(current, colors[i])) {
                if (current != null) out.append(RESET);
                if (colors[i] != null) out.append(ANSI.get(colors[i]));
                current = colors[i];
            }
            out.append(raw.charAt(i));
        }
        return current == null ? out.toString() : out.append(RESET).toString();
    }

    private static void printCliLines(Collection<String> lines, long skipped) {
        if (skipped > 0) System.out.println("[tail-viewer skipped " + skipped + " stale lines]");
        boolean color = skipped == 0 && lines.size() < CLI_BATCH_MAX_LINES;
        for (String line : lines) System.out.println(color ? highlightAnsi(line) : line);
    }

    private static void runCliStdin() throws InterruptedException {
        Deque<String> pending = new ArrayDeque<>();
        Object lock = new Object();
        long[] skipped = {0};
        boolean[] closed = {false};
        Thread.ofVirtual().start(() -> {
            try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = input.readLine()) != null) {
                    synchronized (lock) {
                        if (pending.size() == CLI_PENDING_MAX_LINES) { pending.removeFirst(); skipped[0]++; }
                        pending.addLast(line);
                        lock.notify();
                    }
                }
            } catch (IOException ignored) {
            } finally {
                synchronized (lock) { closed[0] = true; lock.notify(); }
            }
        });
        while (true) {
            List<String> lines;
            long batchSkipped;
            synchronized (lock) {
                while (pending.isEmpty() && !closed[0]) lock.wait();
                if (pending.isEmpty()) return;
                batchSkipped = skipped[0];
                skipped[0] = 0;
                while (pending.size() > CLI_BATCH_MAX_LINES) { pending.removeFirst(); batchSkipped++; }
                lines = new ArrayList<>(pending);
                pending.clear();
            }
            printCliLines(lines, batchSkipped);
        }
    }

    private static void runCli(Options options) throws IOException, InterruptedException {
        if (options.path() == null) {
            runCliStdin();
            return;
        }
        long position = 0;
        Object fileKey = null;
        byte[] marker = null;
        while (true) {
            BasicFileAttributes attributes = Files.readAttributes(Path.of(options.path()), BasicFileAttributes.class);
            long size = attributes.size();
            boolean rotated = (fileKey != null && !Objects.equals(fileKey, attributes.fileKey()))
                    || (marker != null && size >= position && !Arrays.equals(marker, readMarker(options.path(), position)));
            if (position == 0 || position > size || rotated) {
                TailResult tail = readTailLines(options.path(), options.lines());
                printCliLines(tail.lines(), 0);
                position = tail.position();
                fileKey = attributes.fileKey();
                marker = readMarker(options.path(), position);
            } else if (position < size) {
                AppendedLines appended = readAppendedLines(options.path(), position, size, CLI_BATCH_MAX_LINES);
                printCliLines(appended.lines(), appended.skipped());
                position = appended.position();
                marker = readMarker(options.path(), position);
            }
            Thread.sleep(300);
        }
    }

    private void showUI() {
        frame = new JFrame("Tail GUI");
        frame.setDefaultCloseOperation(WindowConstants.EXIT_ON_CLOSE);
        frame.setSize(1000, 600);
        frame.setLocationRelativeTo(null);
        JPanel controls = new JPanel(new FlowLayout(FlowLayout.LEFT));
        JButton open = new JButton("Open file");
        open.addActionListener(e -> openFile());
        controls.add(open);
        controls.add(new JLabel("Lines:"));
        lineCountInput = new JTextField(String.valueOf(maxLines), 8);
        controls.add(lineCountInput);
        wrapBox = new JCheckBox("Wrap");
        wrapBox.addActionListener(e -> {
            logDisplay.setEditorKit(wrapBox.isSelected() ? new WrapEditorKit() : new NoWrapEditorKit());
            scrollPane.setHorizontalScrollBarPolicy(wrapBox.isSelected() ? ScrollPaneConstants.HORIZONTAL_SCROLLBAR_NEVER : ScrollPaneConstants.HORIZONTAL_SCROLLBAR_AS_NEEDED);
            renderLines();
        });
        controls.add(wrapBox);
        controls.add(new JLabel("Search:"));
        searchInput = new JTextField(20);
        controls.add(searchInput);
        JButton previous = new JButton("Prev"); previous.addActionListener(e -> findPrevious()); controls.add(previous);
        JButton next = new JButton("Next"); next.addActionListener(e -> findNext()); controls.add(next);
        searchStatus = new JLabel(); controls.add(searchStatus);
        resumeButton = new JButton("Resume"); resumeButton.addActionListener(e -> resumeTail()); resumeButton.setEnabled(false); controls.add(resumeButton);
        frame.add(controls, BorderLayout.NORTH);

        logDisplay = new JTextPane() {
            @Override public boolean getScrollableTracksViewportWidth() { return wrapBox.isSelected(); }
        };
        logDisplay.setEditorKit(new NoWrapEditorKit());
        logDisplay.setEditable(false);
        logDisplay.setBackground(Color.decode("#1e1e1e"));
        logDisplay.setForeground(Color.decode("#d4d4d4"));
        logDisplay.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12));
        scrollPane = new JScrollPane(logDisplay);
        scrollPane.getViewport().setBackground(logDisplay.getBackground());
        frame.add(scrollPane, BorderLayout.CENTER);
        lineCountInput.addActionListener(e -> applySettings());
        searchInput.addActionListener(e -> findNext());
        searchInput.getDocument().addDocumentListener(new SimpleDocumentListener() { @Override public void update() { scheduleSearch(); } });
        installDropTarget();
        if (stdinMode) { open.setEnabled(false); lineCountInput.setEnabled(false); startStdinReader(); }
        frame.setVisible(true);
        if (!stdinMode) updateLogContent(true);
        timer = new javax.swing.Timer(UPDATE_INTERVAL_MS, e -> updateLogContent(false));
        timer.start();
    }

    private void installDropTarget() {
        new DropTarget(logDisplay, new DropTargetAdapter() {
            @Override public void drop(DropTargetDropEvent event) {
                try {
                    event.acceptDrop(DnDConstants.ACTION_COPY);
                    List<?> files = (List<?>) event.getTransferable().getTransferData(DataFlavor.javaFileListFlavor);
                    files.stream().filter(File.class::isInstance).map(File.class::cast).filter(File::isFile).findFirst().ifPresent(file -> loadFile(file.getAbsolutePath()));
                } catch (Exception ignored) { }
            }
        });
    }

    private void openFile() {
        JFileChooser chooser = new JFileChooser();
        chooser.setFileFilter(new FileNameExtensionFilter("Log files", "log", "txt"));
        if (chooser.showOpenDialog(frame) == JFileChooser.APPROVE_OPTION) loadFile(chooser.getSelectedFile().getAbsolutePath());
    }

    private void loadFile(String path) { logFilePath = path; lastPosition = 0; lastFileKey = null; lastMarker = null; updateLogContent(true); }

    private boolean hasSelection() { return logDisplay.getSelectionStart() != logDisplay.getSelectionEnd(); }

    // modelToView2D is exact; a scrollbar-fraction threshold was found to land a few pixels short.
    private boolean scrolledAwayFromBottom() {
        try {
            Rectangle2D endRect = logDisplay.modelToView2D(logDisplay.getDocument().getLength());
            return endRect != null && !logDisplay.getVisibleRect().contains(endRect.getX(), endRect.getY());
        } catch (BadLocationException e) {
            return false;
        }
    }

    // Selection always pauses; scrolled-away-from-bottom only pauses passive tail-follow.
    private boolean paused(boolean reload) { return hasSelection() || (!reload && scrolledAwayFromBottom()); }

    private void resumeTail() {
        // Collapses any selection too, so this alone clears both pause triggers.
        logDisplay.setCaretPosition(logDisplay.getDocument().getLength());
    }

    private String baseTitle() {
        if (!stdinMode) return "Tail GUI";
        return stdinClosed ? "Tail GUI (stdin closed)" : "Tail GUI (stdin)";
    }

    private void applySettings() {
        try { maxLines = Integer.parseInt(lineCountInput.getText().trim()); if (maxLines <= 0) throw new NumberFormatException(); updateLogContent(true); }
        catch (NumberFormatException e) { lineCountInput.setText(String.valueOf(maxLines)); }
    }

    private void updateLogContent(boolean reload) {
        if (paused(reload)) { resumeButton.setEnabled(true); frame.setTitle(baseTitle()); return; }
        resumeButton.setEnabled(false);
        if (stdinMode) { pollStdin(); return; }
        frame.setTitle(baseTitle());
        boolean renderAfterError = needsFullRender;
        try {
            needsFullRender = false;
            LogResult result = readLog(reload, CLI_BATCH_MAX_LINES);
            lastPosition = result.position();
            lastFileKey = result.fileKey();
            lastMarker = result.marker();
            if (reload || result.truncated()) {
                // Discontinuity (rotation or re-seek) - prior buffer doesn't line up, start over.
                displayLines.clear();
                displayLines.addAll(result.lines());
                renderLines();
            } else if (renderAfterError) {
                if (!result.lines().isEmpty()) appendLines(result.lines(), result.continuesPreviousLine());
                renderLines();
            } else if (!result.lines().isEmpty()) {
                // A bounded in-window skip (result.dropped()); history is still contiguous, keep appending.
                appendRenderedLines(result.lines(), result.continuesPreviousLine(), appendLines(result.lines(), result.continuesPreviousLine()));
            }
        } catch (IOException e) {
            needsFullRender = true;
            renderLines(List.of("Error reading file: " + e.getMessage()));
        }
    }

    private int appendLines(List<String> lines, boolean continuesPreviousLine) {
        if (lines.isEmpty()) return 0;
        if (continuesPreviousLine && !displayLines.isEmpty()) {
            displayLines.set(displayLines.size() - 1, displayLines.getLast() + lines.getFirst());
            if (lines.size() > 1) displayLines.addAll(lines.subList(1, lines.size()));
        } else displayLines.addAll(lines);
        int overflow = Math.max(0, displayLines.size() - maxLines);
        if (overflow > 0) displayLines.subList(0, overflow).clear();
        return overflow;
    }

    private void appendRenderedLines(List<String> lines, boolean continuesPreviousLine, int trimmedLines) {
        StyledDocument doc = logDisplay.getStyledDocument();
        try {
            int start = 0;
            // Tracks what actually changed this call, so the search rescan below covers just that.
            int changedRegionStart = doc.getLength();
            if (continuesPreviousLine && doc.getLength() > 0 && !displayLines.isEmpty()) {
                Element root = doc.getDefaultRootElement();
                int lastLine = root.getElementCount() - 2;
                int lastLineStart = root.getElement(Math.max(0, lastLine)).getStartOffset();
                changedRegionStart = lastLineStart;
                removeHighlightsInRange(lastLineStart, doc.getLength());
                doc.remove(lastLineStart, doc.getLength() - lastLineStart);
                renderLine(doc, displayLines.get(displayLines.size() - lines.size()));
                start = 1;
            }
            for (int i = start; i < lines.size(); i++) renderLine(doc, lines.get(i));
            int changedRegionEnd = doc.getLength();
            if (trimmedLines > 0) {
                Element root = doc.getDefaultRootElement();
                int trimOffset = root.getElement(trimmedLines).getStartOffset();
                // Swing highlights don't auto-remove on delete like Tk tags - they'd leak, so clear first.
                removeHighlightsInRange(0, trimOffset);
                doc.remove(0, trimOffset);
                changedRegionStart = Math.max(0, changedRegionStart - trimOffset);
                changedRegionEnd -= trimOffset;
            }
            logDisplay.setCaretPosition(doc.getLength());
            addIncrementalSearchHits(changedRegionStart, changedRegionEnd);
        } catch (BadLocationException ignored) {
            needsFullRender = true;
        }
    }

    private void renderLines() { renderLines(displayLines); }
    private void renderLines(List<String> lines) {
        StyledDocument doc = logDisplay.getStyledDocument();
        try {
            doc.remove(0, doc.getLength());
            for (String line : lines) renderLine(doc, line);
            logDisplay.setCaretPosition(doc.getLength());
            updateSearch(true);
        } catch (BadLocationException ignored) { }
    }

    private void renderLine(StyledDocument doc, String line) throws BadLocationException {
        String[] colors = new String[line.length()]; int[] priorities = new int[line.length()]; Arrays.fill(priorities, -1);
        for (Span span : computeSpans(line)) for (int i = Math.max(0, span.start()); i < Math.min(line.length(), span.end()); i++) if (span.priority() >= priorities[i]) { priorities[i] = span.priority(); colors[i] = span.color(); }
        int start = 0;
        while (start < line.length()) {
            int end = start + 1; while (end < line.length() && Objects.equals(colors[start], colors[end])) end++;
            SimpleAttributeSet style = new SimpleAttributeSet(); StyleConstants.setForeground(style, colors[start] == null ? Color.decode("#d4d4d4") : COLORS.get(colors[start]));
            doc.insertString(doc.getLength(), line.substring(start, end), style); start = end;
        }
        doc.insertString(doc.getLength(), "\n", null);
    }

    private void scheduleSearch() {
        if (searchTimer == null) {
            searchTimer = new javax.swing.Timer(250, event -> updateSearch(false));
            searchTimer.setRepeats(false);
        }
        searchTimer.restart();
    }

    private void cancelScheduledSearch() {
        if (searchTimer != null) searchTimer.stop();
    }

    // Reads matches straight from the Highlighter - offsets stay correct across edits for free.
    private List<int[]> liveSearchHits() {
        List<int[]> hits = new ArrayList<>();
        for (Highlighter.Highlight h : logDisplay.getHighlighter().getHighlights()) {
            if (h.getPainter() == SEARCH_HIT_PAINTER) hits.add(new int[]{h.getStartOffset(), h.getEndOffset()});
        }
        hits.sort(Comparator.comparingInt(a -> a[0]));
        return hits;
    }

    // Swing highlights don't auto-remove on delete like Tk tags do - call before deleting a range.
    private void removeHighlightsInRange(int start, int end) {
        if (end <= start) return;
        Highlighter highlighter = logDisplay.getHighlighter();
        List<Highlighter.Highlight> toRemove = new ArrayList<>();
        for (Highlighter.Highlight h : highlighter.getHighlights()) {
            if ((h.getPainter() == SEARCH_HIT_PAINTER || h.getPainter() == SEARCH_CURRENT_PAINTER)
                    && h.getStartOffset() >= start && h.getEndOffset() <= end) {
                toRemove.add(h);
            }
        }
        for (Highlighter.Highlight h : toRemove) {
            highlighter.removeHighlight(h);
            if (h.getPainter() == SEARCH_CURRENT_PAINTER) { currentSearchHighlight = null; searchMatchIndex = -1; }
        }
    }

    private void tagHitsInRegion(int regionStart, int regionEnd, String query) {
        if (query.isEmpty() || regionEnd <= regionStart) return;
        int remaining = SEARCH_MAX_MATCHES - liveSearchHits().size();
        if (remaining <= 0) return;
        String text;
        try { text = logDisplay.getDocument().getText(regionStart, regionEnd - regionStart); }
        catch (BadLocationException ignored) { return; }
        String lower = text.toLowerCase(Locale.ROOT), needle = query.toLowerCase(Locale.ROOT);
        Highlighter highlighter = logDisplay.getHighlighter();
        for (int index = lower.indexOf(needle); index >= 0 && remaining > 0; index = lower.indexOf(needle, index + needle.length())) {
            try {
                highlighter.addHighlight(regionStart + index, regionStart + index + needle.length(), SEARCH_HIT_PAINTER);
                remaining--;
            } catch (BadLocationException ignored) { }
        }
    }

    private String matchCountLabel(int count) { return count >= SEARCH_MAX_MATCHES ? SEARCH_MAX_MATCHES + "+" : String.valueOf(count); }
    private String matchStatusText(int count) { return count == 0 ? "no matches" : matchCountLabel(count) + " matches"; }

    /** Only scans the newly-changed region instead of rescanning the whole
     * buffer, so a busy incoming stream stays responsive with search active. */
    private void addIncrementalSearchHits(int regionStart, int regionEnd) {
        String query = searchInput == null ? "" : searchInput.getText();
        if (query.isEmpty()) return;
        tagHitsInRegion(regionStart, regionEnd, query);
        searchStatus.setText(matchStatusText(liveSearchHits().size()));
    }

    private void updateSearch(boolean preserveCurrent) {
        int previousMatchIndex = preserveCurrent ? searchMatchIndex : -1;
        Highlighter highlighter = logDisplay.getHighlighter(); highlighter.removeAllHighlights(); currentSearchHighlight = null; searchMatchIndex = -1;
        String query = searchInput == null ? "" : searchInput.getText();
        if (query.isEmpty()) { searchStatus.setText(""); return; }
        tagHitsInRegion(0, logDisplay.getDocument().getLength(), query);
        List<int[]> matches = liveSearchHits();
        if (previousMatchIndex >= 0 && !matches.isEmpty()) goToMatch(Math.min(previousMatchIndex, matches.size() - 1));
        else searchStatus.setText(matchStatusText(matches.size()));
    }

    private void findNext() {
        boolean pending = searchTimer != null && searchTimer.isRunning(); cancelScheduledSearch();
        if (pending || liveSearchHits().isEmpty()) updateSearch(false);
        if (!liveSearchHits().isEmpty()) goToMatch(searchMatchIndex + 1);
    }
    private void findPrevious() {
        boolean pending = searchTimer != null && searchTimer.isRunning(); cancelScheduledSearch();
        if (pending || liveSearchHits().isEmpty()) updateSearch(false);
        if (!liveSearchHits().isEmpty()) goToMatch(searchMatchIndex - 1);
    }
    private void goToMatch(int index) {
        List<int[]> matches = liveSearchHits();
        if (matches.isEmpty()) { searchStatus.setText(matchStatusText(0)); return; }
        Highlighter highlighter = logDisplay.getHighlighter();
        if (currentSearchHighlight != null) highlighter.removeHighlight(currentSearchHighlight);
        searchMatchIndex = Math.floorMod(index, matches.size());
        int[] match = matches.get(searchMatchIndex);
        try {
            currentSearchHighlight = highlighter.addHighlight(match[0], match[1], SEARCH_CURRENT_PAINTER);
            logDisplay.setCaretPosition(match[0]);
            logDisplay.scrollRectToVisible(logDisplay.modelToView2D(match[0]).getBounds());
        } catch (BadLocationException ignored) { }
        searchStatus.setText((searchMatchIndex + 1) + "/" + matchCountLabel(matches.size()) + " matches");
    }

    private void startStdinReader() {
        Thread.ofVirtual().start(() -> {
            try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = input.readLine()) != null) {
                    if (!stdinLines.offer(line)) {
                        stdinLines.poll();
                        stdinSkipped.incrementAndGet();
                        stdinLines.offer(line);
                    }
                }
            } catch (IOException ignored) { } finally { stdinClosed = true; }
        });
    }

    private void pollStdin() {
        long skipped = stdinSkipped.getAndSet(0);
        while (stdinLines.size() > CLI_BATCH_MAX_LINES && stdinLines.poll() != null) skipped++;
        List<String> lines = new ArrayList<>();
        stdinLines.drainTo(lines, CLI_BATCH_MAX_LINES);
        // Dropped lines were never shown, so the buffer isn't stale - keep appending, don't wipe it.
        if (!lines.isEmpty()) appendRenderedLines(lines, false, appendLines(lines, false));
        String title = stdinClosed ? "Tail GUI (stdin closed)" : "Tail GUI (stdin)";
        frame.setTitle(skipped > 0 ? title + " [skipped " + skipped + "]" : title);
    }

    private static class NoWrapEditorKit extends StyledEditorKit {
        @Override public ViewFactory getViewFactory() {
            ViewFactory delegate = super.getViewFactory();
            return element -> element.getName().equals(AbstractDocument.ParagraphElementName)
                    ? new ParagraphView(element) { @Override public void layout(int width, int height) { super.layout(Short.MAX_VALUE, height); } }
                    : delegate.create(element);
        }
    }
    private static class WrapEditorKit extends StyledEditorKit {
        @Override public ViewFactory getViewFactory() {
            ViewFactory delegate = super.getViewFactory();
            return element -> element.getName().equals(AbstractDocument.ParagraphElementName)
                    ? new ParagraphView(element) { @Override public float getMinimumSpan(int axis) { return axis == View.X_AXIS ? 0 : super.getMinimumSpan(axis); } }
                    : delegate.create(element);
        }
    }
    private interface SimpleDocumentListener extends javax.swing.event.DocumentListener {
        void update(); default void insertUpdate(javax.swing.event.DocumentEvent e) { update(); } default void removeUpdate(javax.swing.event.DocumentEvent e) { update(); } default void changedUpdate(javax.swing.event.DocumentEvent e) { update(); }
    }

    public static void main(String[] args) {
        try {
            Options options = parseArgs(args);
            boolean stdin = options.path() == null && System.console() == null;
            if (!options.gui()) { if (options.path() == null && !stdin) { System.out.println("Usage: TailViewer [--gui] [-f] [-n N|--lines=N] [logfile]"); return; } runCli(options); return; }
            SwingUtilities.invokeLater(() -> new TailViewer(options.path() == null ? DEFAULT_LOG_FILE : options.path(), options.lines(), stdin).showUI());
        } catch (IllegalArgumentException e) { System.err.println(e.getMessage()); } catch (IOException | InterruptedException e) { System.err.println("Error: " + e.getMessage()); Thread.currentThread().interrupt(); }
    }
}
