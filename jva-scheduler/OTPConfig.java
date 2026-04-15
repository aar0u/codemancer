public class OTPConfig {
    private String name;
    private String secretKey;
    private int digits = 6;
    private int period = 30;
    private String algorithm = "SHA1";

    public OTPConfig() {
    }

    public OTPConfig(String name, String secretKey) {
        this.name = name;
        this.secretKey = secretKey;
    }

    public OTPConfig(String name, String secretKey, int digits, int period) {
        this.name = name;
        this.secretKey = secretKey;
        this.digits = digits;
        this.period = period;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getSecretKey() {
        return secretKey;
    }

    public void setSecretKey(String secretKey) {
        this.secretKey = secretKey;
    }

    public int getDigits() {
        return digits;
    }

    public void setDigits(int digits) {
        this.digits = digits;
    }

    public int getPeriod() {
        return period;
    }

    public void setPeriod(int period) {
        this.period = period;
    }

    public String getAlgorithm() {
        return algorithm;
    }

    public void setAlgorithm(String algorithm) {
        this.algorithm = algorithm;
    }

    @Override
    public String toString() {
        return "OTPConfig{" +
                "name='" + name + '\'' +
                ", secretKey='" + secretKey + '\'' +
                ", digits=" + digits +
                ", period=" + period +
                ", algorithm='" + algorithm + '\'' +
                '}';
    }
}
