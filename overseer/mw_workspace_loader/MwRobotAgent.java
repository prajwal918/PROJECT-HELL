import java.awt.*;
import java.awt.event.*;
import java.io.*;
import java.lang.instrument.Instrumentation;
import javax.swing.*;

public class MwRobotAgent {

    static final int WAIT_SHORT  = 400;
    static final int WAIT_MEDIUM = 1000;
    static final int WAIT_LONG   = 2000;
    static final int WAIT_EXTRA  = 3000;

    static Robot robot;
    static String workspaceName = "hi";
    static String logFile;
    static volatile boolean windowFocused = false;
    static volatile boolean consoleFound = false;

    public static void agentmain(String args, Instrumentation inst) {
        if (args != null && !args.isEmpty()) {
            workspaceName = args.split(",")[0];
        }
        logFile = System.getProperty("java.io.tmpdir", "/tmp") + "/mw_robot_agent.log";

        log("=== MwRobotAgent loaded into PID " + getPid() + " ===");
        log("Target workspace: " + workspaceName);
        log("Display: " + System.getenv("DISPLAY"));
        log("Thread: " + Thread.currentThread().getName());

        try {
            robot = new Robot();
            robot.setAutoDelay(50);
            log("Robot initialized (in-JVM!)");
        } catch (AWTException e) {
            log("ERROR creating Robot: " + e.getMessage());
            return;
        }

        // Initial delay for Swing to settle
        robot.delay(3000);

        // Focus the main MotiveWave window on EDT
        runOnEDT(() -> focusMotiveWaveWindow());

        if (!windowFocused) {
            log("WARNING: Could not focus window, sending keystrokes anyway");
        }
        robot.delay(1000);

        // Try strategies
        String[] strategies = {
            "alt_f_r_enter",
            "alt_f_r_down_enter",
            "alt_f_type_name",
            "f10_nav"
        };

        for (String s : strategies) {
            log("\n--- Strategy: " + s + " ---");
            if (runStrategy(s)) {
                log("\n=== WORKSPACE LOADED SUCCESSFULLY ===");
                runOnEDT(() -> listJavaWindows());
                return;
            }
            robot.delay(500);
        }

        log("\nAll strategies exhausted.");
        runOnEDT(() -> listJavaWindows());
    }

    // ---- EDT-safe helper ----

    static void runOnEDT(Runnable task) {
        if (SwingUtilities.isEventDispatchThread()) {
            task.run();
        } else {
            try {
                SwingUtilities.invokeAndWait(task);
            } catch (Exception e) {
                log("EDT error: " + e.getMessage());
            }
        }
    }

    // ---- Window focus (EDT-safe, pure Java) ----

    static void focusMotiveWaveWindow() {
        log("\nAttempting to focus MotiveWave window (EDT)...");
        try {
            // Try Frame.getFrames() first
            Frame[] frames = Frame.getFrames();
            log("Frame.getFrames(): " + frames.length + " frames");
            for (Frame f : frames) {
                String title = f.getTitle();
                log("  Frame: \"" + title + "\" visible=" + f.isVisible());
                if (title.toLowerCase().contains("motivewave") && f.isVisible()) {
                    log("Found MotiveWave Frame! Bringing to front...");
                    f.setState(Frame.NORMAL);
                    f.toFront();
                    f.requestFocus();
                    windowFocused = true;
                    log("Window focused: " + title);
                }
            }

            // Also check Window.getWindows()
            Window[] windows = Window.getWindows();
            log("Window.getWindows(): " + windows.length + " windows");
            for (Window w : windows) {
                String title = getWindowTitle(w).toLowerCase();
                log("  Window: \"" + getWindowTitle(w) + "\" vis=" + w.isVisible());
                if (title.contains("motivewave") && w.isVisible() && !windowFocused) {
                    w.toFront();
                    w.requestFocus();
                    windowFocused = true;
                }
            }

            if (!windowFocused) {
                log("WARNING: No visible MotiveWave window found via Java APIs");
                // Try all frames as fallback
                for (Frame f : frames) {
                    if (f.isVisible()) {
                        log("  Attempting to focus: \"" + f.getTitle() + "\"");
                        f.setState(Frame.NORMAL);
                        f.toFront();
                        f.requestFocus();
                        windowFocused = true;
                        break;
                    }
                }
            }
        } catch (Exception e) {
            log("focus error: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    // ---- Strategies ----

    static boolean runStrategy(String strategy) {
        try {
            switch (strategy) {
                case "alt_f_r_enter":
                    altF();
                    typeLetter('R');
                    robot.delay(WAIT_LONG);
                    pressEnter();
                    robot.delay(WAIT_EXTRA);
                    return checkConsole();

                case "alt_f_r_down_enter":
                    altF();
                    typeLetter('R');
                    robot.delay(WAIT_LONG);
                    pressDown();
                    robot.delay(WAIT_SHORT);
                    pressEnter();
                    robot.delay(WAIT_EXTRA);
                    return checkConsole();

                case "alt_f_type_name":
                    altF();
                    robot.delay(WAIT_MEDIUM);
                    typeString(workspaceName);
                    robot.delay(WAIT_SHORT);
                    pressEnter();
                    robot.delay(WAIT_EXTRA);
                    return checkConsole();

                case "f10_nav":
                    robot.keyPress(KeyEvent.VK_F10);
                    robot.delay(100);
                    robot.keyRelease(KeyEvent.VK_F10);
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
                    robot.delay(WAIT_EXTRA);
                    return checkConsole();
            }
        } catch (Exception e) {
            log("ERROR in " + strategy + ": " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
        return false;
    }

    // ---- Keyboard helpers ----

    static void altF() {
        log("Send Alt+F");
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

    // ---- Console detection (EDT-safe, pure Java) ----

    static boolean checkConsole() {
        log("Checking for Console window...");
        consoleFound = false;
        runOnEDT(() -> {
            try {
                // Check Frame.getFrames()
                for (Frame f : Frame.getFrames()) {
                    String title = f.getTitle().toLowerCase();
                    if (title.contains("console") && f.isVisible()) {
                        log("OK: Console Frame FOUND! \"" + f.getTitle() + "\"");
                        consoleFound = true;
                        return;
                    }
                }
                // Check Window.getWindows()
                for (Window w : Window.getWindows()) {
                    String title = getWindowTitle(w).toLowerCase();
                    if (title.contains("console") && w.isVisible()) {
                        log("OK: Console Window FOUND! \"" + getWindowTitle(w) + "\"");
                        consoleFound = true;
                        return;
                    }
                }
            } catch (Exception e) {
                log("checkConsole error: " + e.getMessage());
            }
        });
        if (!consoleFound) {
            log("No Console window found");
        }
        return consoleFound;
    }

    static String getWindowTitle(Window w) {
        if (w instanceof Frame) return ((Frame)w).getTitle();
        if (w instanceof Dialog) return ((Dialog)w).getTitle();
        return w.getName() != null ? w.getName() : "(unnamed " + w.getClass().getSimpleName() + ")";
    }

    static void listJavaWindows() {
        log("\n--- Java Window List (EDT) ---");
        try {
            Frame[] frames = Frame.getFrames();
            log("Frames: " + frames.length);
            for (Frame f : frames) {
                log("  [Frame] \"" + f.getTitle() + "\" vis=" + f.isVisible() + " state=" + f.getState());
            }
            Window[] windows = Window.getWindows();
            log("Windows: " + windows.length);
            for (Window w : windows) {
                log("  [" + w.getClass().getSimpleName() + "] \"" + getWindowTitle(w) + "\" vis=" + w.isVisible());
            }
        } catch (Exception e) {
            log("list error: " + e.getMessage());
        }
        log("--- End ---\n");
    }

    // ---- Utilities ----

    static String getPid() {
        try {
            return java.lang.management.ManagementFactory.getRuntimeMXBean().getName().split("@")[0];
        } catch (Exception e) {
            return "?";
        }
    }

    static void log(String msg) {
        String ts = new java.text.SimpleDateFormat("HH:mm:ss.SSS").format(new java.util.Date());
        String line = "[" + ts + "] " + msg;
        System.out.println(line);
        try (FileWriter fw = new FileWriter(logFile, true);
             BufferedWriter bw = new BufferedWriter(fw);
             PrintWriter pw = new PrintWriter(bw)) {
            pw.println(line);
        } catch (IOException e) {}
    }
}
