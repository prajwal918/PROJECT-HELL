import java.awt.*;
import java.awt.event.*;
import java.io.*;
import java.lang.instrument.Instrumentation;
import javax.swing.*;

public class MwRobotAgentV5 {

    static final int WAIT_SHORT  = 400;
    static final int WAIT_MEDIUM = 1000;
    static final int WAIT_LONG   = 2000;
    static final int WAIT_EXTRA  = 3000;

    static Robot robot;
    static String workspaceName = "hi";
    static String logFile;
    static volatile boolean consoleFound = false;

    public static void agentmain(String args, Instrumentation inst) {
        if (args != null && !args.isEmpty()) {
            workspaceName = args.split(",")[0];
        }
        logFile = System.getProperty("java.io.tmpdir", "/tmp") + "/mw_robot_agent5.log";

        log("=== MwRobotAgentV5 loaded ===");
        log("Target: " + workspaceName);
        log("Display: " + System.getenv("DISPLAY"));

        try {
            robot = new Robot();
            robot.setAutoDelay(50);
            log("Robot initialized (in-JVM!)");
        } catch (AWTException e) {
            log("ERROR Robot: " + e.getMessage());
            return;
        }

        // Wait 12s for MotiveWave to fully initialize
        log("Waiting 12s for Swing initialization...");
        robot.delay(12000);

        // Scan windows
        runEDT(() -> scanWindows());

        // Try strategies
        String[] strategies = {
            "alt_f_r_enter",
            "alt_f_r_down_enter",
            "alt_f_type_name",
            "f10_nav"
        };

        for (String s : strategies) {
            log("\n--- " + s + " ---");
            if (runStrategy(s)) {
                log("\n=== WORKSPACE LOADED ===");
                runEDT(() -> listWindows());
                return;
            }
            robot.delay(500);
        }

        log("\nAll strategies exhausted.");
        runEDT(() -> listWindows());
    }

    static void runEDT(Runnable task) {
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

    static void scanWindows() {
        log("\n--- Window Scan ---");
        try {
            log("Frame.getFrames(): " + Frame.getFrames().length + " frames");
            for (Frame f : Frame.getFrames()) {
                log("  Frame: \"" + f.getTitle() + "\" vis=" + f.isVisible() + " state=" + f.getState());
            }
            log("Window.getWindows(): " + Window.getWindows().length + " windows");
            for (Window w : Window.getWindows()) {
                String t = (w instanceof Frame) ? ((Frame)w).getTitle() :
                          (w instanceof Dialog) ? ((Dialog)w).getTitle() : w.getName();
                log("  [" + w.getClass().getSimpleName() + "] \"" + t + "\" vis=" + w.isVisible());
            }
            log("Toolkit: " + Toolkit.getDefaultToolkit().getClass().getName());
            
            // Try to find and focus MotiveWave
            for (Frame f : Frame.getFrames()) {
                if (f.getTitle().toLowerCase().contains("motivewave") && f.isVisible()) {
                    log("FOCUSING: " + f.getTitle());
                    f.setState(Frame.NORMAL);
                    f.toFront();
                    f.requestFocus();
                    
                    // Check for JMenuBar
                    JMenuBar mb = null;
                    if (f instanceof JFrame) {
                        mb = ((JFrame)f).getJMenuBar();
                    }
                    log("  JMenuBar: " + (mb != null ? "YES (" + mb.getMenuCount() + " menus)" : "NO"));
                    if (mb != null) {
                        for (int i = 0; i < mb.getMenuCount(); i++) {
                            JMenu m = mb.getMenu(i);
                            if (m != null) log("  Menu[" + i + "]: \"" + m.getText() + "\"");
                        }
                    }
                    break;
                }
            }
        } catch (Exception e) {
            log("scan error: " + e.getClass().getSimpleName() + ": " + e.getMessage());
            e.printStackTrace();
        }
    }

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
                    for (int i = 0; i < 8; i++) { pressDown(); robot.delay(150); }
                    pressRight();
                    robot.delay(WAIT_MEDIUM);
                    pressDown();
                    robot.delay(WAIT_SHORT);
                    pressEnter();
                    robot.delay(WAIT_EXTRA);
                    return checkConsole();
            }
        } catch (Exception e) {
            log("ERROR " + strategy + ": " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
        return false;
    }

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
        int code = toVk(c); boolean shift = Character.isUpperCase(c);
        if (shift) robot.keyPress(KeyEvent.VK_SHIFT);
        robot.keyPress(code); robot.delay(50); robot.keyRelease(code);
        if (shift) robot.keyRelease(KeyEvent.VK_SHIFT);
    }

    static void typeString(String s) { for (char c : s.toCharArray()) { typeLetter(c); robot.delay(30); } }
    static void pressEnter() { robot.keyPress(KeyEvent.VK_ENTER); robot.delay(50); robot.keyRelease(KeyEvent.VK_ENTER); }
    static void pressDown() { robot.keyPress(KeyEvent.VK_DOWN); robot.delay(50); robot.keyRelease(KeyEvent.VK_DOWN); }
    static void pressRight() { robot.keyPress(KeyEvent.VK_RIGHT); robot.delay(50); robot.keyRelease(KeyEvent.VK_RIGHT); }

    static int toVk(char c) {
        char u = Character.toUpperCase(c);
        if (u >= 'A' && u <= 'Z') return KeyEvent.VK_A + (u - 'A');
        if (u >= '0' && u <= '9') return KeyEvent.VK_0 + (u - '0');
        return KeyEvent.VK_H;
    }

    static boolean checkConsole() {
        consoleFound = false;
        runEDT(() -> {
            for (Frame f : Frame.getFrames()) {
                if (f.getTitle().toLowerCase().contains("console") && f.isVisible()) {
                    log("OK: Console FOUND! \"" + f.getTitle() + "\"");
                    consoleFound = true; return;
                }
            }
            for (Window w : Window.getWindows()) {
                String t = (w instanceof Frame) ? ((Frame)w).getTitle() :
                          (w instanceof Dialog) ? ((Dialog)w).getTitle() : "";
                if (t.toLowerCase().contains("console") && w.isVisible()) {
                    log("OK: Console FOUND! \"" + t + "\"");
                    consoleFound = true; return;
                }
            }
        });
        if (!consoleFound) log("No Console window");
        return consoleFound;
    }

    static void listWindows() {
        log("\n--- Java Windows ---");
        for (Frame f : Frame.getFrames()) {
            log("  Frame: \"" + f.getTitle() + "\" vis=" + f.isVisible());
        }
        log("--- End ---\n");
    }

    static String getPid() {
        try { return java.lang.management.ManagementFactory.getRuntimeMXBean().getName().split("@")[0]; }
        catch (Exception e) { return "?"; }
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
