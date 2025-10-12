import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.awt.event.KeyEvent;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.concurrent.ThreadLocalRandom;

public class JvaScheduler extends JPanel {
  private LocalDateTime clickTime;
  private final JLabel label;
  private final Timer timer;

  public JvaScheduler() {
    setLayout(new GridBagLayout());
    GridBagConstraints gbc = new GridBagConstraints();
    gbc.gridwidth = GridBagConstraints.REMAINDER;

    label = new JLabel("...");
    gbc.insets = new Insets(20, 60, 5, 60);
    add(label, gbc);

    JButton btn = new JButton("Start");
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
    gbc.insets = new Insets(5, 70, 20, 70);
    add(btn, gbc);

    final Robot robot;
    try {
      robot = new Robot();
    } catch (AWTException e) {
      throw new RuntimeException(e);
    }
    timer =
        new Timer(
            500,
            e -> {
              LocalDateTime now = LocalDateTime.now();
              Duration duration = Duration.between(now, clickTime);
              label.setText(format(duration));
              if (duration.isNegative()) {
                robot.keyPress(KeyEvent.VK_NUM_LOCK);
                robot.keyRelease(KeyEvent.VK_NUM_LOCK);
                clickTime =
                    LocalDateTime.now()
                        .plusMinutes(3)
                        .plusSeconds(ThreadLocalRandom.current().nextLong(30));
              }
            });
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

          JFrame frame = new JFrame("Window");
          frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
          frame.add(new JvaScheduler());
          frame.pack();
          frame.setLocationRelativeTo(null);
          frame.setVisible(true);
        });
  }
}
