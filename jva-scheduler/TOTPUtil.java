import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.ByteBuffer;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;

public class TOTPUtil {

    private static final String HMAC_SHA1 = "HmacSHA1";
    private static final int DEFAULT_DIGITS = 6;
    private static final int DEFAULT_PERIOD = 30;

    public static String generateTOTP(String base32Secret) {
        return generateTOTP(base32Secret, DEFAULT_DIGITS, DEFAULT_PERIOD);
    }

    public static String generateTOTP(String base32Secret, int digits, int period) {
        long currentTimeSeconds = System.currentTimeMillis() / 1000;
        long timeStep = currentTimeSeconds / period;
        return generateTOTP(base32Secret, timeStep, digits);
    }

    public static String generateTOTP(String base32Secret, long timeStep, int digits) {
        byte[] secret = base32Decode(base32Secret);
        byte[] timeBytes = ByteBuffer.allocate(8).putLong(timeStep).array();

        Mac mac;
        try {
            mac = Mac.getInstance(HMAC_SHA1);
            mac.init(new SecretKeySpec(secret, HMAC_SHA1));
        } catch (NoSuchAlgorithmException | InvalidKeyException e) {
            throw new RuntimeException("Failed to initialize HMAC", e);
        }

        byte[] hash = mac.doFinal(timeBytes);
        int offset = hash[hash.length - 1] & 0xf;
        int binary = ((hash[offset] & 0x7f) << 24)
                | ((hash[offset + 1] & 0xff) << 16)
                | ((hash[offset + 2] & 0xff) << 8)
                | (hash[offset + 3] & 0xff);

        int otp = binary % (int) Math.pow(10, digits);
        return String.format("%0" + digits + "d", otp);
    }

    public static int getSecondsUntilNextUpdate(int period) {
        long currentTimeSeconds = System.currentTimeMillis() / 1000;
        return period - (int) (currentTimeSeconds % period);
    }

    private static byte[] base32Decode(String base32) {
        base32 = base32.toUpperCase().replaceAll("[^A-Z2-7]", "");

        int length = base32.length();
        byte[] result = new byte[length * 5 / 8];
        int buffer = 0;
        int bufferLength = 0;
        int index = 0;

        for (int i = 0; i < length; i++) {
            char c = base32.charAt(i);
            int value = base32CharToValue(c);

            buffer = (buffer << 5) | value;
            bufferLength += 5;

            if (bufferLength >= 8) {
                bufferLength -= 8;
                result[index++] = (byte) (buffer >> bufferLength);
            }
        }

        return result;
    }

    private static int base32CharToValue(char c) {
        if (c >= 'A' && c <= 'Z') {
            return c - 'A';
        } else if (c >= '2' && c <= '7') {
            return c - '2' + 26;
        } else {
            throw new IllegalArgumentException("Invalid Base32 character: " + c);
        }
    }
}
