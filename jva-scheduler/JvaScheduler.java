import javax.swing.*;
import javax.swing.border.Border;
import java.awt.*;
import java.awt.datatransfer.StringSelection;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.awt.event.KeyEvent;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

public class JvaScheduler extends JPanel {
    private static final Color ROW_BORDER_COLOR = new Color(200, 200, 200);

    private static Border createRowBorder() {
        return BorderFactory.createCompoundBorder(
                BorderFactory.createEmptyBorder(10, 10, 10, 10),
                BorderFactory.createMatteBorder(0, 0, 1, 0, ROW_BORDER_COLOR));
    }

    private LocalDateTime clickTime;
    private final JLabel label;
    private final Timer timer;
    private final Timer otpTimer;
    private List<OTPConfig> otpConfigs;
    private List<JLabel> otpLabels;
    private List<JLabel> countdownLabels;
    private List<JProgressBar> progressBars;

    public JvaScheduler() {
        setLayout(new BorderLayout());

        JPanel listPanel = new JPanel();
        listPanel.setLayout(new BoxLayout(listPanel, BoxLayout.Y_AXIS));
        listPanel.setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10));

        JPanel timerPanel = new JPanel(new GridBagLayout());
        timerPanel.setBorder(createRowBorder());
        timerPanel.setMaximumSize(new Dimension(Integer.MAX_VALUE, 100));

        GridBagConstraints gbc = new GridBagConstraints();

        label = new JLabel("...");
        label.setFont(new Font("Arial", Font.PLAIN, 12));
        gbc.gridx = 0;
        gbc.gridy = 0;
        gbc.weightx = 1.0;
        gbc.insets = new Insets(0, 0, 0, 10);
        gbc.anchor = GridBagConstraints.WEST;
        timerPanel.add(label, gbc);

        JButton btn = new JButton("Start");
        btn.setPreferredSize(new Dimension(80, 50));
        btn.addActionListener(
                new ActionListener() {
                    @Override
                    public void actionPerformed(ActionEvent e) {
                        if (timer.isRunning()) {
                            timer.stop();
                            clickTime = null;
                            btn.setText("Start");
                        } else {
                            clickTime = LocalDateTime.now();
                            timer.start();
                            btn.setText("Stop");
                        }
                    }
                });
        gbc.gridx = 1;
        gbc.gridy = 0;
        gbc.weightx = 0.0;
        gbc.insets = new Insets(0, 10, 0, 0);
        gbc.anchor = GridBagConstraints.EAST;
        timerPanel.add(btn, gbc);

        listPanel.add(timerPanel);

        otpConfigs = OTPConfigManager.loadConfigs();
        otpLabels = new ArrayList<>();
        countdownLabels = new ArrayList<>();
        progressBars = new ArrayList<>();

        for (OTPConfig config : otpConfigs) {
            JPanel otpPanel = new JPanel(new BorderLayout());
            otpPanel.setBorder(createRowBorder());
            otpPanel.setMaximumSize(new Dimension(Integer.MAX_VALUE, 100));

            JPanel contentPanel = new JPanel(new GridBagLayout());
            GridBagConstraints gbcTop = new GridBagConstraints();

            JLabel nameLabel = new JLabel(config.getName());
            nameLabel.setFont(new Font("Arial", Font.BOLD, 14));
            gbcTop.gridx = 0;
            gbcTop.gridy = 0;
            gbcTop.weightx = 0.0;
            gbcTop.insets = new Insets(0, 0, 0, 10);
            gbcTop.anchor = GridBagConstraints.WEST;
            contentPanel.add(nameLabel, gbcTop);

            JLabel otpLabel = new JLabel("------");
            otpLabel.setFont(new Font("Monospaced", Font.BOLD, 28));
            otpLabel.setPreferredSize(new Dimension(120, 25));
            gbcTop.gridx = 1;
            gbcTop.gridy = 0;
            gbcTop.weightx = 1.0;
            gbcTop.insets = new Insets(0, 10, 0, 10);
            gbcTop.anchor = GridBagConstraints.CENTER;
            contentPanel.add(otpLabel, gbcTop);
            otpLabels.add(otpLabel);

            JButton copyButton = new JButton("Copy");
            copyButton.setPreferredSize(new Dimension(80, 50));
            copyButton.addActionListener(e -> {
                String token = otpLabel.getText();
                if (!token.equals("------") && !token.equals("ERROR")) {
                    Toolkit.getDefaultToolkit().getSystemClipboard().setContents(
                            new StringSelection(token), null);
                }
            });
            gbcTop.gridx = 2;
            gbcTop.gridy = 0;
            gbcTop.weightx = 0.0;
            gbcTop.insets = new Insets(0, 10, 0, 0);
            gbcTop.anchor = GridBagConstraints.EAST;
            contentPanel.add(copyButton, gbcTop);

            otpPanel.add(contentPanel, BorderLayout.CENTER);

            JPanel bottomPanel = new JPanel(new BorderLayout());
            JLabel countdownLabel = new JLabel("Updating in: --s");
            countdownLabel.setFont(new Font("Arial", Font.PLAIN, 11));
            bottomPanel.add(countdownLabel, BorderLayout.WEST);
            countdownLabels.add(countdownLabel);

            JProgressBar progressBar = new JProgressBar(0, config.getPeriod());
            progressBar.setValue(config.getPeriod());
            progressBar.setStringPainted(false);
            progressBar.setPreferredSize(new Dimension(200, 15));
            JPanel progressPanel = new JPanel(new FlowLayout(FlowLayout.RIGHT));
            progressPanel.add(progressBar);
            bottomPanel.add(progressPanel, BorderLayout.EAST);
            progressBars.add(progressBar);

            otpPanel.add(bottomPanel, BorderLayout.SOUTH);

            listPanel.add(otpPanel);
        }

        JScrollPane scrollPane = new JScrollPane(listPanel);
        scrollPane.setVerticalScrollBarPolicy(JScrollPane.VERTICAL_SCROLLBAR_AS_NEEDED);
        scrollPane.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_NEVER);
        add(scrollPane, BorderLayout.CENTER);

        final Robot robot;
        try {
            robot = new Robot();
        } catch (AWTException e) {
            throw new RuntimeException(e);
        }
        timer = new Timer(
                500,
                e -> {
                    LocalDateTime now = LocalDateTime.now();
                    Duration duration = Duration.between(now, clickTime);
                    label.setText(format(duration));
                    if (duration.isNegative()) {
                        // Options: NUMLOCK, SCROLL_LOCK, CAPS_LOCK, SPACE, ENTER
                        robot.keyPress(KeyEvent.VK_NUM_LOCK);
                        robot.keyRelease(KeyEvent.VK_NUM_LOCK);
                        clickTime = LocalDateTime.now()
                                .plusMinutes(3)
                                .plusSeconds(ThreadLocalRandom.current().nextLong(30));
                    }
                });

        otpTimer = new Timer(1000, e -> updateOTPDisplays());
        otpTimer.start();
        updateOTPDisplays();
    }

    private void updateOTPDisplays() {
        for (int i = 0; i < otpConfigs.size(); i++) {
            OTPConfig config = otpConfigs.get(i);
            try {
                String token = TOTPUtil.generateTOTP(config.getSecretKey(), config.getDigits(), config.getPeriod());
                otpLabels.get(i).setText(token);

                int secondsLeft = TOTPUtil.getSecondsUntilNextUpdate(config.getPeriod());
                countdownLabels.get(i).setText(String.format("Updating in: %ds", secondsLeft));
                progressBars.get(i).setValue(secondsLeft);
            } catch (Exception ex) {
                otpLabels.get(i).setText("ERROR");
                countdownLabels.get(i).setText("Error: Invalid secret");
            }
        }
    }

    protected String format(Duration duration) {
        long hours = duration.toHours();
        long mins = duration.minusHours(hours).toMinutes();
        long seconds = duration.minusMinutes(mins).toMillis() / 1000;
        return String.format("%02dh %02dm %02ds", hours, mins, seconds);
    }

    public static void main(String[] args) {
        run();
    }

    static void run() {
        EventQueue.invokeLater(
                () -> {
                    try {
                        UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());
                    } catch (ClassNotFoundException
                            | InstantiationException
                            | IllegalAccessException
                            | UnsupportedLookAndFeelException ex) {
                        ex.printStackTrace();
                    }

                    JFrame frame = new JFrame("JVA Scheduler with TOTP");
                    frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
                    frame.setPreferredSize(new Dimension(500, 600));
                    frame.add(new JvaScheduler());
                    frame.pack();
                    frame.setLocationRelativeTo(null);
                    frame.setVisible(true);
                });
    }
}
