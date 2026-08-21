import javax.swing.*;
import javax.swing.filechooser.FileNameExtensionFilter;
import javax.swing.text.*;
import java.awt.*;
import java.awt.datatransfer.DataFlavor;
import java.awt.dnd.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TailViewer {
    private static final int DEFAULT_MAX_LINES = 10;
    private static final int STDIN_GUI_MAX_LINES = 50_000;
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
    private JCheckBox wrapBox;
    private JScrollPane scrollPane;
    private final List<String> displayLines = new ArrayList<>();
    private final List<int[]> searchMatches = new ArrayList<>();
    private int searchMatchIndex = -1;
    private int maxLines;
    private String logFilePath;
    private long lastPosition;
    private javax.swing.Timer timer;
    private boolean stdinMode;
    private final Queue<String> stdinLines = new ArrayDeque<>();
    private volatile boolean stdinClosed;

    private TailViewer(String logFilePath, int maxLines, boolean stdinMode) {
        this.logFilePath = logFilePath;
        this.maxLines = stdinMode ? STDIN_GUI_MAX_LINES : maxLines;
        this.stdinMode = stdinMode;
    }

    private record Options(String path, int lines, boolean gui) {}
    private record LogResult(List<String> lines, long position, boolean truncated, boolean continuesPreviousLine) {}
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

    private static List<String> readTailLines(String filePath, int count) throws IOException {
        byte[] bytes = Files.readAllBytes(Path.of(filePath));
        String content = new String(bytes, StandardCharsets.UTF_8).replace("\0", "");
        String[] lines = content.split("\\R");
        int start = Math.max(0, lines.length - count);
        return new ArrayList<>(Arrays.asList(lines).subList(start, lines.length));
    }

    private LogResult readLog(boolean reload) throws IOException {
        try (RandomAccessFile file = new RandomAccessFile(logFilePath, "r")) {
            long length = file.length();
            boolean truncated = lastPosition > length;
            if (reload || lastPosition == 0 || truncated) return new LogResult(readTailLines(logFilePath, maxLines), length, truncated, false);
            if (lastPosition == length) return new LogResult(List.of(), length, false, false);
            file.seek(lastPosition - 1);
            boolean continuesPreviousLine = file.read() != '\n';
            file.seek(lastPosition);
            byte[] bytes = new byte[(int) (length - lastPosition)];
            file.readFully(bytes);
            String content = new String(bytes, StandardCharsets.UTF_8).replace("\0", "");
            List<String> lines = new ArrayList<>(Arrays.asList(content.split("\\R", -1)));
            if (content.endsWith("\n") || content.endsWith("\r")) lines.removeLast();
            return new LogResult(lines, length, false, continuesPreviousLine);
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

    private static void runCli(Options options) throws IOException, InterruptedException {
        if (options.path() == null) {
            try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = input.readLine()) != null) System.out.println(highlightAnsi(line));
            }
            return;
        }
        long position = 0;
        while (true) {
            long size = Files.size(Path.of(options.path()));
            if (position == 0 || position > size) {
                for (String line : readTailLines(options.path(), options.lines())) System.out.println(highlightAnsi(line));
                position = size;
            } else if (position < size) {
                try (RandomAccessFile file = new RandomAccessFile(options.path(), "r")) {
                    file.seek(position);
                    byte[] bytes = new byte[(int) (size - position)];
                    file.readFully(bytes);
                    for (String line : new String(bytes, StandardCharsets.UTF_8).replace("\0", "").split("\\R", -1)) System.out.println(highlightAnsi(line));
                }
                position = size;
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
        wrapBox.addActionListener(e -> { logDisplay.setEditorKit(wrapBox.isSelected() ? new WrapEditorKit() : new StyledEditorKit()); renderLines(); });
        controls.add(wrapBox);
        controls.add(new JLabel("Search:"));
        searchInput = new JTextField(20);
        controls.add(searchInput);
        JButton previous = new JButton("Prev"); previous.addActionListener(e -> findPrevious()); controls.add(previous);
        JButton next = new JButton("Next"); next.addActionListener(e -> findNext()); controls.add(next);
        searchStatus = new JLabel(); controls.add(searchStatus);
        frame.add(controls, BorderLayout.NORTH);

        logDisplay = new JTextPane();
        logDisplay.setEditable(false);
        logDisplay.setBackground(Color.decode("#1e1e1e"));
        logDisplay.setForeground(Color.decode("#d4d4d4"));
        logDisplay.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12));
        logDisplay.addCaretListener(e -> frame.setTitle(logDisplay.getSelectionStart() == logDisplay.getSelectionEnd() ? "Tail GUI" : "Tail GUI [PAUSED]"));
        scrollPane = new JScrollPane(logDisplay);
        frame.add(scrollPane, BorderLayout.CENTER);
        lineCountInput.addActionListener(e -> applySettings());
        searchInput.addActionListener(e -> findNext());
        searchInput.getDocument().addDocumentListener(new SimpleDocumentListener() { @Override public void update() { updateSearch(); } });
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

    private void loadFile(String path) { logFilePath = path; lastPosition = 0; updateLogContent(true); }
    private boolean paused() { return logDisplay.getSelectionStart() != logDisplay.getSelectionEnd(); }

    private void applySettings() {
        try { maxLines = Integer.parseInt(lineCountInput.getText().trim()); if (maxLines <= 0) throw new NumberFormatException(); updateLogContent(true); }
        catch (NumberFormatException e) { lineCountInput.setText(String.valueOf(maxLines)); }
    }

    private void updateLogContent(boolean reload) {
        if (paused()) return;
        if (stdinMode) { pollStdin(); return; }
        try {
            LogResult result = readLog(reload);
            lastPosition = result.position();
            if (reload || result.truncated()) { displayLines.clear(); displayLines.addAll(result.lines()); }
            else appendLines(result.lines(), result.continuesPreviousLine());
            renderLines();
        } catch (IOException e) { renderLines(List.of("Error reading file: " + e.getMessage())); }
    }

    private void appendLines(List<String> lines, boolean continuesPreviousLine) {
        if (lines.isEmpty()) return;
        if (continuesPreviousLine && !displayLines.isEmpty()) {
            displayLines.set(displayLines.size() - 1, displayLines.getLast() + lines.getFirst());
            if (lines.size() > 1) displayLines.addAll(lines.subList(1, lines.size()));
        } else displayLines.addAll(lines);
        if (displayLines.size() > maxLines) displayLines.subList(0, displayLines.size() - maxLines).clear();
    }

    private void renderLines() { renderLines(displayLines); }
    private void renderLines(List<String> lines) {
        StyledDocument doc = logDisplay.getStyledDocument();
        try {
            doc.remove(0, doc.getLength());
            for (String line : lines) renderLine(doc, line);
            logDisplay.setCaretPosition(doc.getLength());
            updateSearch();
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

    private void updateSearch() {
        Highlighter highlighter = logDisplay.getHighlighter(); highlighter.removeAllHighlights(); searchMatches.clear(); searchMatchIndex = -1;
        String query = searchInput == null ? "" : searchInput.getText(); String text = logDisplay.getText();
        if (query.isEmpty()) { searchStatus.setText(""); return; }
        String lower = text.toLowerCase(Locale.ROOT), needle = query.toLowerCase(Locale.ROOT);
        for (int index = lower.indexOf(needle); index >= 0; index = lower.indexOf(needle, index + needle.length())) {
            searchMatches.add(new int[]{index, index + needle.length()});
            try { highlighter.addHighlight(index, index + needle.length(), new DefaultHighlighter.DefaultHighlightPainter(Color.decode("#5a5a00"))); } catch (BadLocationException ignored) { }
        }
        searchStatus.setText(searchMatches.isEmpty() ? "no matches" : searchMatches.size() + " matches");
    }

    private void findNext() { if (searchMatches.isEmpty()) updateSearch(); goToMatch(searchMatchIndex + 1); }
    private void findPrevious() { if (searchMatches.isEmpty()) updateSearch(); goToMatch(searchMatchIndex - 1); }
    private void goToMatch(int index) {
        if (searchMatches.isEmpty()) return;
        searchMatchIndex = Math.floorMod(index, searchMatches.size()); int[] match = searchMatches.get(searchMatchIndex);
        try { logDisplay.getHighlighter().addHighlight(match[0], match[1], new DefaultHighlighter.DefaultHighlightPainter(Color.decode("#c07800"))); } catch (BadLocationException ignored) { }
        logDisplay.setCaretPosition(match[0]); searchStatus.setText((searchMatchIndex + 1) + "/" + searchMatches.size() + " matches");
    }

    private void startStdinReader() {
        Thread.ofVirtual().start(() -> {
            try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                String line; while ((line = input.readLine()) != null) synchronized (stdinLines) { stdinLines.add(line); }
            } catch (IOException ignored) { } finally { stdinClosed = true; }
        });
    }

    private void pollStdin() {
        List<String> lines = new ArrayList<>(); synchronized (stdinLines) { while (!stdinLines.isEmpty()) lines.add(stdinLines.remove()); }
        if (!lines.isEmpty()) { displayLines.addAll(lines); if (displayLines.size() > maxLines) displayLines.subList(0, displayLines.size() - maxLines).clear(); renderLines(); }
        frame.setTitle(stdinClosed ? "Tail GUI (stdin closed)" : "Tail GUI (stdin)");
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
