import java.io.*;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.List;
import javax.swing.JOptionPane;

public class OTPConfigManager {
    private static String getConfigFilePath() {
        try {
            String jarPath = OTPConfigManager.class.getProtectionDomain()
                    .getCodeSource().getLocation().toURI().getPath();
            File jarFile = new File(jarPath);
            String jarDir = jarFile.getParent();
            String jarName = jarFile.getName();
            
            String baseName;
            if (jarName.endsWith(".jar")) {
                baseName = jarName.substring(0, jarName.length() - 4);
            } else {
                baseName = jarName;
            }
            
            return new File(jarDir, baseName + ".properties").getAbsolutePath();
        } catch (URISyntaxException e) {
            showError("Failed to get jar file path: " + e.getMessage());
            return "otp_config.properties";
        }
    }
    
    private static void showError(String message) {
        JOptionPane.showMessageDialog(null, message, "Configuration Error", JOptionPane.ERROR_MESSAGE);
    }

    public static List<OTPConfig> loadConfigs() {
        List<OTPConfig> configs = new ArrayList<>();
        String configPath = getConfigFilePath();
        File file = new File(configPath);

        if (!file.exists()) {
            configs.add(new OTPConfig("Example1", "JBSWY3DPEHPK3PXP", 6, 30));
            configs.add(new OTPConfig("Example2", "KVKFKRCPNZQUYMLX", 6, 30));
            saveConfigs(configs);
            return configs;
        }

        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty() || line.startsWith("#")) {
                    continue;
                }

                String[] parts = line.split("=", 2);
                if (parts.length != 2) {
                    continue;
                }

                String name = parts[0].trim();
                String[] values = parts[1].split(",");

                OTPConfig config = new OTPConfig();
                config.setName(name);

                if (values.length >= 1) {
                    config.setSecretKey(values[0].trim());
                }
                if (values.length >= 2) {
                    try {
                        config.setDigits(Integer.parseInt(values[1].trim()));
                    } catch (NumberFormatException e) {
                        config.setDigits(6);
                    }
                }
                if (values.length >= 3) {
                    try {
                        config.setPeriod(Integer.parseInt(values[2].trim()));
                    } catch (NumberFormatException e) {
                        config.setPeriod(30);
                    }
                }

                configs.add(config);
            }
        } catch (IOException e) {
            showError("Failed to load configuration: " + e.getMessage());
        }

        return configs;
    }

    public static void saveConfigs(List<OTPConfig> configs) {
        String configPath = getConfigFilePath();
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(configPath))) {
            writer.write("# OTP Configuration File\n");
            writer.write("# Format: name=secret_key,digits,period\n");
            writer.write("# Example: MyAccount=JBSWY3DPEHPK3PXP,6,30\n\n");

            for (OTPConfig config : configs) {
                writer.write(String.format("%s=%s,%d,%d\n",
                        config.getName(),
                        config.getSecretKey(),
                        config.getDigits(),
                        config.getPeriod()));
            }
        } catch (IOException e) {
            showError("Failed to save configuration: " + e.getMessage());
        }
    }
}
