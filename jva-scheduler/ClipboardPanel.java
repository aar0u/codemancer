import javax.swing.*;
import java.awt.*;
import java.awt.datatransfer.*;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.io.File;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * ClipboardPanel monitors the system clipboard every second and displays
 * the last 10 entries as clickable rows. Clicking a row restores it to the clipboard.
 */
public class ClipboardPanel extends JPanel {
    private static final int MAX_ENTRIES = 10;
    private static final int POLL_INTERVAL_MS = 1000;
    private static final int MAX_TEXT_CHARS = 100_000;
    private static final DateTimeFormatter TIME_FMT = DateTimeFormatter.ofPattern("HH:mm:ss");
    private static final Color ROW_BORDER_COLOR = new Color(200, 200, 200);
    private static final Color HOVER_COLOR  = new Color(230, 240, 255);
    private static final Color COPIED_COLOR = new Color(180, 230, 180);

    /** Represents a single clipboard entry (text, image, or file list). */
    private static class ClipEntry {
        enum Type { TEXT, IMAGE, FILE }

        final Type type;
        final String displayText;   // truncated to 2 lines for display; see createRow
        final String fullText;      // full original text for tooltip / restore
        final Transferable transferable;

        ClipEntry(Type type, String displayText, String fullText, Transferable transferable) {
            this.type = type;
            this.displayText = displayText;
            this.fullText = fullText;
            this.transferable = transferable;
        }
    }

    private final List<ClipEntry> entries = new ArrayList<>();
    private final JPanel rowsPanel;
    private volatile String lastText = null;          // last seen text content
    private volatile long lastContentHash = 0L;       // last aHash for non-text content
    private volatile boolean ignoreNext = false;  // flag to break the copy-back loop

    public ClipboardPanel() {
        setLayout(new BorderLayout());
        setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createEmptyBorder(10, 10, 10, 10),
                BorderFactory.createMatteBorder(0, 0, 1, 0, ROW_BORDER_COLOR)));

        JLabel header = new JLabel("Clipboard History");
        header.setFont(new Font("Arial", Font.BOLD, 13));
        header.setBorder(BorderFactory.createEmptyBorder(0, 0, 6, 0));
        add(header, BorderLayout.NORTH);

        rowsPanel = new JPanel();
        rowsPanel.setLayout(new BoxLayout(rowsPanel, BoxLayout.Y_AXIS));
        add(rowsPanel, BorderLayout.CENTER);

        startMonitor();
    }

    // -------------------------------------------------------------------------
    // Background polling thread
    // -------------------------------------------------------------------------
    private void startMonitor() {
        Thread t = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(POLL_INTERVAL_MS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
                pollClipboard();
            }
        }, "clipboard-monitor");
        t.setDaemon(true);
        t.start();
    }

    private void pollClipboard() {
        try {
            Clipboard cb = Toolkit.getDefaultToolkit().getSystemClipboard();
            Transferable current;
            try {
                current = cb.getContents(null);
            } catch (Exception e) {
                return; // clipboard unavailable (e.g. locked by another process)
            }

            if (current == null) return;

            // Ownership-lost guard: skip when we ourselves just wrote to clipboard
            if (ignoreNext) {
                ignoreNext = false;
                long h = current.isDataFlavorSupported(DataFlavor.stringFlavor)
                        ? 0L : contentHash(current);
                syncState(current, h);
                return;
            }

            // For non-text types compute hash once; reused by hasChanged and syncState
            long newHash = current.isDataFlavorSupported(DataFlavor.stringFlavor)
                    ? 0L : contentHash(current);
            if (!hasChanged(current, newHash)) return;

            ClipEntry entry = buildEntry(current);
            syncState(current, newHash);
            if (entry == null) return;

            SwingUtilities.invokeLater(() -> addEntry(entry));

        } catch (Exception e) {
            // Swallow; clipboard access can be intermittently unavailable
        }
    }

    /** Sync all last-seen state fields to the current Transferable. */
    private void syncState(Transferable t, long hash) {
        if (t.isDataFlavorSupported(DataFlavor.stringFlavor)) {
            try {
                lastText = (String) t.getTransferData(DataFlavor.stringFlavor);
            } catch (Exception ignored) {}
        } else {
            lastText = null;
            lastContentHash = hash;
        }
    }

    /** Returns true if the current clipboard content differs from last seen. */
    private boolean hasChanged(Transferable current, long newHash) {
        if (current.isDataFlavorSupported(DataFlavor.stringFlavor)) {
            try {
                String text = (String) current.getTransferData(DataFlavor.stringFlavor);
                return !text.equals(lastText);
            } catch (Exception e) {
                return true;
            }
        }
        return newHash != lastContentHash;
    }

    /**
     * Compute a perceptual average hash (aHash) for non-text clipboard content.
     * Images: scale to 8x8 grayscale, compare each pixel to the mean → 64-bit hash.
     *   Same image always yields the same hash. BufferedImage is not stored; GC reclaims it.
     * File lists: hash the joined paths.
     */
    private long contentHash(Transferable t) {
        try {
            if (t.isDataFlavorSupported(DataFlavor.imageFlavor)) {
                java.awt.Image img = (java.awt.Image) t.getTransferData(DataFlavor.imageFlavor);
                // Scale to 8x8 grayscale thumbnail
                java.awt.image.BufferedImage thumb = new java.awt.image.BufferedImage(
                        8, 8, java.awt.image.BufferedImage.TYPE_BYTE_GRAY);
                Graphics g = thumb.getGraphics();
                try {
                    g.drawImage(img, 0, 0, 8, 8, null);
                } finally {
                    g.dispose();
                }
                // Compute average of 64 pixels
                int sum = 0;
                int[] pixels = new int[64];
                for (int i = 0; i < 64; i++) {
                    pixels[i] = thumb.getRaster().getSample(i % 8, i / 8, 0);
                    sum += pixels[i];
                }
                int avg = sum / 64;
                // Build 64-bit hash: bit[i] = 1 if pixel >= avg
                long hash = 0L;
                for (int i = 0; i < 64; i++) {
                    if (pixels[i] >= avg) hash |= (1L << i);
                }
                return hash;
            }
            if (t.isDataFlavorSupported(DataFlavor.javaFileListFlavor)) {
                @SuppressWarnings("unchecked")
                java.util.List<java.io.File> files =
                        (java.util.List<java.io.File>) t.getTransferData(DataFlavor.javaFileListFlavor);
                return files.stream().map(java.io.File::getAbsolutePath)
                        .reduce("", (a, b) -> a + b).hashCode();
            }
        } catch (Exception e) {
            // fall through
        }
        return System.identityHashCode(t);
    }

    /** Build a ClipEntry from a Transferable, returns null if unsupported. */
    private ClipEntry buildEntry(Transferable t) {
        try {
            if (t.isDataFlavorSupported(DataFlavor.stringFlavor)) {
                String text = (String) t.getTransferData(DataFlavor.stringFlavor);
                String trimmed = text.trim();
                if (trimmed.isEmpty()) return null;
                String stored = trimmed.length() > MAX_TEXT_CHARS
                        ? trimmed.substring(0, MAX_TEXT_CHARS) + "\n[TRUNCATED — " + trimmed.length() + " chars total]"
                        : trimmed;
                return new ClipEntry(ClipEntry.Type.TEXT, stored, stored, new StringSelection(stored));
            }

            if (t.isDataFlavorSupported(DataFlavor.javaFileListFlavor)) {
                @SuppressWarnings("unchecked")
                List<File> files = (List<File>) t.getTransferData(DataFlavor.javaFileListFlavor);
                String fullText = files.stream().map(File::getAbsolutePath)
                        .reduce((a, b) -> a + "\n" + b).orElse("");
                String display = files.size() == 1
                        ? shorten(files.get(0).getName())
                        : files.size() + " files";
                return new ClipEntry(ClipEntry.Type.FILE, "[File] " + display, fullText, t);
            }

            if (t.isDataFlavorSupported(DataFlavor.imageFlavor)) {
                String label = "[Image] " + LocalDateTime.now().format(TIME_FMT);
                // Do NOT store the Transferable: a BufferedImage can be 10-30MB per screenshot.
                // Stale clipboard images cannot be reliably restored after owner changes anyway.
                return new ClipEntry(ClipEntry.Type.IMAGE, label, label, null);
            }
        } catch (Exception e) {
            // Unsupported or unavailable data
        }
        return null;
    }

    private static String shorten(String s) {
        return s.length() > 20 ? s.substring(0, 20) + "..." : s;
    }

    // -------------------------------------------------------------------------
    // UI update (always on EDT)
    // -------------------------------------------------------------------------
    private void addEntry(ClipEntry entry) {
        entries.add(0, entry);
        if (entries.size() > MAX_ENTRIES) {
            entries.remove(entries.size() - 1);
        }
        rebuildRows();
    }

    private void rebuildRows() {
        rowsPanel.removeAll();
        for (ClipEntry entry : entries) {
            rowsPanel.add(createRow(entry));
        }
        rowsPanel.revalidate();
        rowsPanel.repaint();
    }

    private JPanel createRow(ClipEntry entry) {
        JPanel row = new JPanel(new BorderLayout()) {
            @Override public Dimension getMaximumSize() {
                // Allow full width, but never taller than preferred (prevents BoxLayout stretching)
                return new Dimension(Integer.MAX_VALUE, getPreferredSize().height);
            }
        };
        row.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createMatteBorder(0, 0, 1, 0, new Color(220, 220, 220)),
                BorderFactory.createEmptyBorder(4, 6, 4, 6)));
        row.setAlignmentX(Component.LEFT_ALIGNMENT);

        // Type icon / prefix (ASCII-safe to avoid encoding issues)
        String prefix = switch (entry.type) {
            case IMAGE -> "[IMG] ";
            case FILE -> "[FILE] ";
            default -> "[TXT] ";
        };

        // Truncate to 2 lines; if more exist append "..."
        String[] rawLines = entry.displayText.split("\n", -1);
        String displayText;
        if (rawLines.length > 2) {
            displayText = prefix + rawLines[0] + "\n" + rawLines[1] + "\n...";
        } else {
            displayText = prefix + entry.displayText;
        }

        // Use JTextArea for reliable word-wrap within container width (JLabel stretches on long lines)
        JTextArea textLabel = new JTextArea(displayText);
        textLabel.setFont(new Font("Dialog", Font.PLAIN, 12));
        textLabel.setLineWrap(true);
        textLabel.setWrapStyleWord(true);
        textLabel.setEditable(false);
        textLabel.setOpaque(true);
        textLabel.setBackground(null);
        textLabel.setBorder(null);
        textLabel.setToolTipText("<html><pre style='max-width:480px;white-space:pre-wrap;word-wrap:break-word'>"
                + escapeHtml(entry.fullText) + "</pre></html>");
        row.add(textLabel, BorderLayout.CENTER);

        // Hover & click handling.
        // Both row and textLabel get the same listener to avoid flicker when cursor
        // moves between parent panel and child label. mouseExited also verifies the
        // cursor has actually left the row bounds before clearing the highlight.
        MouseAdapter ma = new MouseAdapter() {
            private void setHighlight(boolean on) {
                Color bg = on ? HOVER_COLOR : null;
                row.setBackground(bg);
                textLabel.setBackground(bg);
            }
            @Override public void mouseEntered(MouseEvent e) { setHighlight(true); }
            @Override public void mouseExited(MouseEvent e) { setHighlight(false); }
            @Override public void mouseClicked(MouseEvent e) {
                if (entry.transferable == null) return;  // IMAGE: nothing to restore, skip feedback
                restoreToClipboard(entry);
                // Visual feedback: green flash + "Copied!" for 400ms
                String original = textLabel.getText();
                row.setBackground(COPIED_COLOR);
                textLabel.setBackground(COPIED_COLOR);
                textLabel.setText("Copied!");
                Timer t = new Timer(400, ev -> {
                    textLabel.setText(original);
                    // Restore to hover color if cursor still inside, else clear
                    Point p2 = MouseInfo.getPointerInfo().getLocation();
                    SwingUtilities.convertPointFromScreen(p2, row);
                    boolean inside = row.contains(p2);
                    row.setBackground(inside ? HOVER_COLOR : null);
                    textLabel.setBackground(inside ? HOVER_COLOR : null);
                });
                t.setRepeats(false);
                t.start();
            }
        };
        row.addMouseListener(ma);
        textLabel.addMouseListener(ma);
        row.setCursor(Cursor.getPredefinedCursor(Cursor.HAND_CURSOR));
        textLabel.setCursor(Cursor.getPredefinedCursor(Cursor.HAND_CURSOR));

        return row;
    }

    /** Copy the entry's transferable back to the system clipboard, suppressing re-detection. */
    private void restoreToClipboard(ClipEntry entry) {
        ignoreNext = true;
        Clipboard cb = Toolkit.getDefaultToolkit().getSystemClipboard();
        try {
            cb.setContents(entry.transferable, (clipboard, contents) -> {
                // ownership lost — nothing to do, we don't re-monitor our own writes
            });
        } catch (Exception e) {
            ignoreNext = false;
        }
    }

    private static String escapeHtml(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }
}
