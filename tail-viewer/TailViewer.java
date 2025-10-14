import javax.swing.*;
import javax.swing.text.*;
import java.awt.*;
import java.awt.datatransfer.DataFlavor;
import java.awt.datatransfer.UnsupportedFlavorException;
import java.awt.dnd.*;
import java.awt.event.*;
import java.io.*;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.List;
import java.util.Optional;
import java.util.Timer;
import java.util.regex.Pattern;
import java.util.regex.Matcher;

public class TailViewer {
    // Constants
    private static final int DEFAULT_WINDOW_WIDTH = 800;
    private static final int DEFAULT_WINDOW_HEIGHT = 600;
    private static final int DEFAULT_MAX_LINES = 1000;
    private static final int UPDATE_INTERVAL_MS = 1000;
    private static final String[] DEFAULT_KEYWORDS = {"ERROR"};
    private static final String DEFAULT_LOG_FILE = "sample.log";
    private static final Color HIGHLIGHT_UI_COLOR = Color.ORANGE;
    private static final String HIGHLIGHT_ANSI_START = "\u001B[1;31m";
    private static final String HIGHLIGHT_ANSI_RESET = "\u001B[0m";

    // UI Components
    private JFrame frame;
    private JTextArea logDisplay;
    private JTextField lineCountInput;
    private JTextField keywordInput;

    // State variables
    private final List<String> displayLines = new ArrayList<>();
    private int maxLines = DEFAULT_MAX_LINES;
    private String[] highlightKeywords = DEFAULT_KEYWORDS;
    private String logFilePath;
    private long lastPosition = 0;
    private Timer timer;
    private boolean paused = false;

    private TailViewer(String logFilePath) {
        this.logFilePath = logFilePath;
    }

    private static void printf(String format, Object... args) { System.out.print(String.format(format, args)); }
    private static void printlnf(String format, Object... args) { System.out.println(String.format(format, args)); }

    // Log reading and processing utility class
    private static class LogResult {
        public List<String> lines;
        public long newPosition;
        public boolean fileTruncated;

        public LogResult(List<String> lines, long newPosition, boolean fileTruncated) {
            this.lines = lines;
            this.newPosition = newPosition;
            this.fileTruncated = fileTruncated;
        }
    }

    private LogResult getLogContent(String logFilePath, long lastPosition, int maxLines) throws IOException {
        List<String> fetchedLines = new ArrayList<>();
        boolean fileTruncated;
        try (RandomAccessFile raf = new RandomAccessFile(logFilePath, "r")) {
            long fileLen = raf.length();

            fileTruncated = lastPosition > fileLen; // File was truncated if lastPosition > fileLen
            if (lastPosition == 0 || fileTruncated) {
                fetchedLines = readLastLines(logFilePath, maxLines);
                lastPosition = fileLen;
            } else {
                long newLen = fileLen - lastPosition;
                if (newLen > 0) {
                    // Prevent memory overflow for large files
                    if (newLen > Integer.MAX_VALUE - 8) {
                        newLen = Integer.MAX_VALUE - 8;
                    }

                    byte[] bytes = new byte[(int) newLen];
                    raf.seek(lastPosition);
                    raf.readFully(bytes);
                    lastPosition = raf.getFilePointer();

                    String newContent = new String(bytes, StandardCharsets.UTF_8);
                    // Keep empty segments by using split with limit = -1
                    String[] newLines = newContent.split("\r?\n", -1);
                    fetchedLines = Arrays.asList(newLines);
                }
            }
        }
        return new LogResult(fetchedLines, lastPosition, fileTruncated);
    }

    private List<String> readLastLines(String filePath, int numLines) throws IOException {
        List<String> result = new ArrayList<>(numLines);
        try (RandomAccessFile file = new RandomAccessFile(filePath, "r")) {
            long fileLength = file.length();
            if (fileLength == 0) return result;

            byte[] buffer = new byte[8192];
            long pos = fileLength;
            int lines = 0;
            StringBuilder line = new StringBuilder();

            while (pos > 0 && lines < numLines) {
                int readSize = (int) Math.min(buffer.length, pos);
                pos -= readSize;
                file.seek(pos);
                file.readFully(buffer, 0, readSize);

                // Process buffer from end to beginning
                for (int i = readSize - 1; i >= 0 && lines < numLines; i--) {
                    char c = (char) buffer[i];
                    if (c == '\n') {
                        if (line.length() > 0) {
                            result.add(0, line.toString());
                            line.setLength(0);
                            lines++;
                        }
                    } else if (c != '\r') {
                        line.insert(0, c);
                    }
                }
            }

            // Handle last line if exists and not reached line limit
            if (line.length() > 0 && lines < numLines) {
                result.add(0, line.toString());
            }
        }
        return result;
    }


    private void applySettings() {
        updateMaxLines();
        updateHighlighter();
        updateLogContent(true);
    }

    private void showUI() {
        // Create and configure main frame
        frame = new JFrame("Tail GUI");
        frame.setSize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT);
        frame.setLocationRelativeTo(null);
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosing(WindowEvent e) {
                dispose();
            }
        });
        frame.setLayout(new BorderLayout());
        
        // Create control panel
        JPanel controlPanel = new JPanel(new FlowLayout(FlowLayout.LEFT));
        controlPanel.add(new JLabel("Lines:"));
        lineCountInput = new JTextField(String.valueOf(maxLines), 6);
        controlPanel.add(lineCountInput);
        controlPanel.add(new JLabel("Highlight:"));
        keywordInput = new JTextField(String.join(",", highlightKeywords), 12);
        controlPanel.add(keywordInput);
        JButton updateBtn = new JButton("Apply");
        controlPanel.add(updateBtn);
        frame.add(controlPanel, BorderLayout.NORTH);

        // Create log display area
        logDisplay = new JTextArea();
        logDisplay.setEditable(false);
        JScrollPane scrollPane = new JScrollPane(logDisplay);
        frame.add(scrollPane, BorderLayout.CENTER);

        // Add event listeners
        logDisplay.addCaretListener(e -> {
            paused = logDisplay.getSelectionStart() != logDisplay.getSelectionEnd();
            frame.setTitle(paused ? "Tail GUI [PAUSED]" : "Tail GUI");
        });

        new DropTarget(logDisplay, new DropTargetAdapter() {
            public void drop(DropTargetDropEvent dtde) {
                try {
                    dtde.acceptDrop(DnDConstants.ACTION_COPY);
                    Object data = dtde.getTransferable().getTransferData(DataFlavor.javaFileListFlavor);
                    if (data instanceof List<?>) {
                        List<?> rawList = (List<?>) data;
                        Optional<File> firstFile = rawList.stream()
                                .filter(File.class::isInstance)
                                .map(File.class::cast)
                                .filter(File::isFile)
                                .findFirst();

                        if (firstFile.isPresent()) {
                            File file = firstFile.get();
                            printlnf("Dragged in file: %s", file.getAbsolutePath());
                            logFilePath = file.getAbsolutePath();
                            lastPosition = 0;
                            updateLogContent(true);
                        }
                    }
                } catch (UnsupportedFlavorException | IOException ex) {
                    JOptionPane.showMessageDialog(frame, "Error loading file: " + ex.getMessage(), "File Error", JOptionPane.ERROR_MESSAGE);
                } catch (Exception ex) {
                    JOptionPane.showMessageDialog(frame, "Unexpected error: " + ex.getMessage(), "Error", JOptionPane.ERROR_MESSAGE);
                }
            }
        });

        // Add action listeners for both text fields to trigger update on Enter
        lineCountInput.addActionListener(e -> applySettings());
        keywordInput.addActionListener(e -> applySettings());
        updateBtn.addActionListener(e -> applySettings());
        
        // Show frame and initialize
        frame.setVisible(true);
        updateLogContent(true);
        startTimer();
    }

    private void dispose() {
        if (timer != null) {
            timer.cancel();
            timer = null;
        }
        if (frame != null) {
            frame.dispose();
        }
    }

    private void updateMaxLines() {
        try {
            int newLines = Integer.parseInt(lineCountInput.getText().trim());
            if (newLines > 0) {
                maxLines = newLines;
            }
        } catch (NumberFormatException ex) {
            lineCountInput.setText(String.valueOf(maxLines));
        }
    }

    private void updateHighlighter() {
        String text = keywordInput.getText().trim();
        if (!text.isEmpty()) {
            highlightKeywords = text.split(",");
            for (int i = 0; i < highlightKeywords.length; i++) {
                highlightKeywords[i] = highlightKeywords[i].trim();
            }
        }
    }

    private void startTimer() {
        timer = new Timer();
        timer.schedule(new TimerTask() {
            @Override
            public void run() {
                SwingUtilities.invokeLater(() -> updateLogContent(false));
            }
        }, 0, UPDATE_INTERVAL_MS);
    }

    private void updateLogContent(boolean forceReload) {
        if (paused || !new File(logFilePath).exists()) return;

        long startTime = System.currentTimeMillis();
        try {
            LogResult result = getLogContent(logFilePath, forceReload ? 0 : lastPosition, maxLines);
            lastPosition = result.newPosition;

            if (forceReload || result.fileTruncated) {
                displayLines.clear();
                displayLines.addAll(result.lines);
            } else {
                // Merge the incoming chunk with existing lines:
                // - If the chunk starts without a newline, its first segment belongs to the last existing line
                // - If the chunk starts with a newline, first segment is ""
                if (!displayLines.isEmpty() && !result.lines.isEmpty()) {
                    int lastIdx = displayLines.size() - 1;
                    String merged = displayLines.get(lastIdx) + result.lines.get(0);
                    displayLines.set(lastIdx, merged);
                    if (result.lines.size() > 1) {
                        displayLines.addAll(result.lines.subList(1, result.lines.size()));
                    }
                } else {
                    displayLines.addAll(result.lines);
                }
                if (displayLines.size() > maxLines) {
                    displayLines.subList(0, displayLines.size() - maxLines).clear();
                }
            }

            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < displayLines.size(); i++) {
                String line = displayLines.get(i);
                if (line != null) {
                    sb.append(line);
                    if (i < displayLines.size() - 1) sb.append('\n');
                }
            }

            logDisplay.setText(sb.toString());
            updateHighlights();
            logDisplay.setCaretPosition(logDisplay.getDocument().getLength());

            long updateTime = System.currentTimeMillis() - startTime;
            int newLinesCount = result.lines.size();
            int totalLinesCount = displayLines.size();
            printlnf("[GUI] Loaded: %d lines | Total: %d lines | Time: %dms",
                    newLinesCount, totalLinesCount, updateTime);

        } catch (IOException ex) {
            logDisplay.setText("Error reading file: " + ex.getMessage());
            printlnf("[GUI] Error: %s", ex.getMessage());
        }
    }

    private void updateHighlights() {
        Highlighter highlighter = logDisplay.getHighlighter();
        highlighter.removeAllHighlights();
        String text = logDisplay.getText();
        for (String keyword : highlightKeywords) {
            if (keyword.isEmpty()) continue;
            Pattern pattern = Pattern.compile(Pattern.quote(keyword), Pattern.CASE_INSENSITIVE);
            Matcher matcher = pattern.matcher(text);
            while (matcher.find()) {
                try {
                    highlighter.addHighlight(matcher.start(), matcher.end(),
                            new DefaultHighlighter.DefaultHighlightPainter(HIGHLIGHT_UI_COLOR));
                } catch (BadLocationException ignored) {
                }
            }
        }
    }

    public String updateHighlightsAnsi(List<String> lines, String[] keywords) {
        if (lines == null || lines.isEmpty()) return "";
        if (keywords == null) return "";

        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line == null) continue;
            String colored = line;
            for (String kw : keywords) {
                if (kw != null && !kw.isEmpty()) {
                    Pattern p = Pattern.compile(Pattern.quote(kw), Pattern.CASE_INSENSITIVE);
                    Matcher m = p.matcher(colored);
                    StringBuffer buf = new StringBuffer();
                    while (m.find()) {
                        String coloredGroup = HIGHLIGHT_ANSI_START + m.group() + HIGHLIGHT_ANSI_RESET;
                        m.appendReplacement(buf, Matcher.quoteReplacement(coloredGroup));
                    }
                    m.appendTail(buf);
                    colored = buf.toString();
                }
            }
            sb.append(colored);
            if (i < lines.size() - 1) sb.append('\n');
        }
        return sb.toString();
    }

    public void runCliMode(String[] args) {
        for (int i = 0; i < args.length; i++) {
            if ("--lines".equalsIgnoreCase(args[i]) && i + 1 < args.length) {
                try {
                    maxLines = Integer.parseInt(args[++i]);
                } catch (Exception ignored) {
                }
            } else if ("--keywords".equalsIgnoreCase(args[i]) && i + 1 < args.length) {
                highlightKeywords = args[++i].split(",");
                for (int k = 0; k < highlightKeywords.length; k++) highlightKeywords[k] = highlightKeywords[k].trim();
            }
        }
        
        timer = new Timer();
        timer.schedule(new TimerTask() {
            @Override
            public void run() {
                try {
                    LogResult result = getLogContent(logFilePath, lastPosition, maxLines);
                    lastPosition = result.newPosition;
                    String output = updateHighlightsAnsi(result.lines, highlightKeywords);
                    printf("%s", output);
                } catch (IOException ex) {
                    printlnf("Error reading file: %s", ex.getMessage());
                }
            }
        }, 0, UPDATE_INTERVAL_MS);
    }

    public static void main(String[] args) {
        // Set java.home for GraalVM native image runtime (when java.class.path is null or blank)
        String classPath = System.getProperty("java.class.path");
        if (classPath == null || classPath.trim().isEmpty()) {
            try {
                String path = Paths.get(TailViewer.class.getProtectionDomain().getCodeSource().getLocation().toURI()).getParent().toString();
                System.setProperty("java.home", path);
                printlnf("[INFO] Set java.home to: %s", path);
            } catch (Exception e) { 
                System.setProperty("java.home", ".");
                printlnf("[INFO] Set java.home to: .");
            }
        }

        boolean cliMode = false;
        String logPath = DEFAULT_LOG_FILE;

        for (int i = 0; i < args.length; i++) {
            if ("--cli".equalsIgnoreCase(args[i])) {
                cliMode = true;
            } else if (!args[i].startsWith("--") && DEFAULT_LOG_FILE.equals(logPath)) {
                logPath = args[i];
            }
        }

        TailViewer viewer = new TailViewer(logPath);
        if (cliMode) {
            viewer.runCliMode(args);
        } else {
            viewer.showUI();
        }
    }
}
