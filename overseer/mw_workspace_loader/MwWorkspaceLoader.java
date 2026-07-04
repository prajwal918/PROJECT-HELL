import java.awt.*;
import java.awt.event.*;
import java.io.*;

public class MwWorkspaceLoader {

    static final int WAIT_SHORT  = 400;
    static final int WAIT_MEDIUM = 1000;
    static final int WAIT_LONG   = 2000;

    static Robot robot;
    static String workspaceName;
    static int winX, winY, winW, winH;

    public static void main(String[] args) throws Exception {
        workspaceName = args.length > 0 ? args[0] : "hi";

        System.out.println("=== MwWorkspaceLoader (Robot) ===");
        System.out.println("DISPLAY=" + System.getenv("DISPLAY"));
        System.out.println("Target workspace: " + workspaceName);
        System.out.println();

        robot = new Robot();
        robot.setAutoDelay(50);
        System.out.println("Robot initialized");

        if (!getWindowGeometry()) {
            System.err.println("ERROR: Cannot find/parse MotiveWave window");
            System.exit(1);
        }

        // Try strategies in order
        String[] strategies = {
            "click_center_then_alt_f_r_enter",
            "click_title_then_alt_f_r_down_enter",
            "click_center_then_f10_nav",
            "click_menu_file_then_nav_recent",
            "click_menu_coords"
        };

        String strategy = System.getenv("STRATEGY");
        if (strategy != null) {
            System.out.println("Using STRATEGY from env: " + strategy);
            if (runStrategy(strategy)) { reportSuccess(); return; }
        } else {
            for (String s : strategies) {
                System.out.println("\n--- Strategy: " + s + " ---");
                if (runStrategy(s)) {
                    reportSuccess();
                    return;
                }
            }
        }

        System.out.println("\nAll strategies exhausted.");
        printWindows();
        System.exit(1);
    }

    static boolean runStrategy(String strategy) throws Exception {
        switch (strategy) {
            case "click_center_then_alt_f_r_enter":
                clickCenter();
                altF();
                typeLetter('R');
                robot.delay(WAIT_LONG);
                pressEnter();
                robot.delay(WAIT_LONG);
                return checkConsole();

            case "click_title_then_alt_f_r_down_enter":
                clickTitleBar();
                altF();
                typeLetter('R');
                robot.delay(WAIT_LONG);
                pressDown();
                robot.delay(WAIT_SHORT);
                pressEnter();
                robot.delay(WAIT_LONG);
                return checkConsole();

            case "click_center_then_f10_nav":
                clickCenter();
                robot.delay(500);
                robot.keyPress(KeyEvent.VK_F10);
                robot.delay(100);
                robot.keyRelease(KeyEvent.VK_F10);
                robot.delay(WAIT_MEDIUM);
                for (int i = 0; i < 10; i++) {
                    pressDown();
                    robot.delay(200);
                }
                pressRight();
                robot.delay(WAIT_MEDIUM);
                for (int i = 0; i < 5; i++) {
                    pressDown();
                    robot.delay(200);
                }
                pressEnter();
                robot.delay(WAIT_LONG);
                return checkConsole();

            case "click_menu_coords":
                clickAt(winX + 20, winY + 15);
                robot.delay(WAIT_MEDIUM);
                typeLetter('R');
                robot.delay(WAIT_LONG);
                clickAt(winX + 150, winY + 120);
                robot.delay(WAIT_LONG);
                return checkConsole();

            case "click_menu_file_then_nav_recent":
                clickAt(winX + 20, winY + 15);
                robot.delay(WAIT_MEDIUM);
                for (int i = 0; i < 8; i++) {
                    pressDown();
                    robot.delay(150);
                }
                pressRight();
                robot.delay(WAIT_MEDIUM);
                pressDown();
                robot.delay(WAIT_SHORT);
                pressEnter();
                robot.delay(WAIT_LONG);
                return checkConsole();
        }
        return false;
    }

    // ---- Mouse helpers ----

    static void clickCenter() {
        clickAt(winX + winW / 2, winY + winH / 2);
    }

    static void clickTitleBar() {
        clickAt(winX + winW / 2, winY + 10);
    }

    static void clickAt(int x, int y) {
        System.out.println("Click at (" + x + ", " + y + ")");
        robot.mouseMove(x, y);
        robot.delay(100);
        robot.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        robot.delay(50);
        robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        robot.delay(300);
    }

    // ---- Keyboard helpers ----

    static void altF() {
        System.out.println("Send Alt+F");
        robot.keyPress(KeyEvent.VK_ALT);
        robot.delay(50);
        robot.keyPress(KeyEvent.VK_F);
        robot.delay(100);
        robot.keyRelease(KeyEvent.VK_F);
        robot.delay(50);
        robot.keyRelease(KeyEvent.VK_ALT);
        robot.delay(WAIT_MEDIUM);
    }

    static void typeLetter(char c) {
        int code = toVk(c);
        boolean shift = Character.isUpperCase(c);
        if (shift) robot.keyPress(KeyEvent.VK_SHIFT);
        robot.keyPress(code);
        robot.delay(50);
        robot.keyRelease(code);
        if (shift) robot.keyRelease(KeyEvent.VK_SHIFT);
    }

    static void typeString(String s) {
        for (char c : s.toCharArray()) {
            typeLetter(c);
            robot.delay(30);
        }
    }

    static void pressEnter() {
        robot.keyPress(KeyEvent.VK_ENTER);
        robot.delay(50);
        robot.keyRelease(KeyEvent.VK_ENTER);
    }

    static void pressDown() {
        robot.keyPress(KeyEvent.VK_DOWN);
        robot.delay(50);
        robot.keyRelease(KeyEvent.VK_DOWN);
    }

    static void pressRight() {
        robot.keyPress(KeyEvent.VK_RIGHT);
        robot.delay(50);
        robot.keyRelease(KeyEvent.VK_RIGHT);
    }

    static int toVk(char c) {
        char u = Character.toUpperCase(c);
        if (u >= 'A' && u <= 'Z') return KeyEvent.VK_A + (u - 'A');
        if (u >= '0' && u <= '9') return KeyEvent.VK_0 + (u - '0');
        return KeyEvent.VK_H;
    }

    // ---- Window management ----

    static boolean getWindowGeometry() throws Exception {
        String mwId = execGet("xdotool search --name MotiveWave 2>/dev/null | tail -1").trim();
        if (mwId.isEmpty()) {
            System.err.println("ERROR: No MotiveWave window");
            return false;
        }
        System.out.println("MotiveWave window ID: " + mwId);

        // Activate window
        exec("xdotool windowactivate --sync " + mwId + " 2>/dev/null");
        robot.delay(500);

        // Get geometry
        String out = execGet("xdotool getwindowgeometry " + mwId + " 2>/dev/null | grep -E 'Position|Geometry'").trim();
        System.out.println("Raw geometry: " + out.replace("\n", " | "));

        // Parse: "Position: 67,73\nGeometry: 890x550"
        // Replace all non-digit chars with space, then split and parse
        String[] lines = out.split("\n");
        for (String line : lines) {
            // Extract all numbers from the line
            String nums = line.replaceAll("[^0-9]", " ").trim();
            String[] parts = nums.split("\\s+");
            if (line.toLowerCase().contains("position") && parts.length >= 2) {
                winX = Integer.parseInt(parts[0]);
                winY = Integer.parseInt(parts[1]);
                System.out.println("  Position: " + winX + ", " + winY);
            } else if (line.toLowerCase().contains("geometry") && parts.length >= 2) {
                winW = Integer.parseInt(parts[0]);
                winH = Integer.parseInt(parts[1]);
                System.out.println("  Size: " + winW + "x" + winH);
            }
        }

        return winW > 0 && winH > 0;
    }

    static boolean checkConsole() throws Exception {
        String result = execGet("xdotool search --name Console 2>/dev/null").trim();
        boolean found = !result.isEmpty();
        System.out.println(found ? "\u2713 Console window! (ID: " + result.split("\n")[0] + ")" : "\u2717 No Console window");
        return found;
    }

    static void reportSuccess() throws Exception {
        System.out.println("\n=== \u2705 WORKSPACE LOADED SUCCESSFULLY ===");
        printWindows();
    }

    static void printWindows() throws Exception {
        System.out.println("\nCurrent windows:");
        System.out.print(execGet("for id in $(xdotool search '.*' 2>/dev/null); do " +
                "name=$(xdotool getwindowname $id 2>/dev/null); " +
                "if [ -n \"$name\" ] && [ \"$name\" != \"Openbox\" ]; then " +
                "echo \"  $name\"; fi; done"));
    }

    static String execGet(String cmd) throws Exception {
        Process p = Runtime.getRuntime().exec(new String[]{"bash", "-c", cmd});
        BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = r.readLine()) != null) sb.append(line).append("\n");
        p.waitFor();
        return sb.toString();
    }

    static void exec(String cmd) throws Exception {
        Runtime.getRuntime().exec(new String[]{"bash", "-c", cmd});
    }
}
