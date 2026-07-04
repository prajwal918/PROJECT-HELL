import java.awt.*;
import java.awt.event.*;
import java.io.*;
import java.lang.instrument.Instrumentation;

public class MwAgentFinal {

    static Robot robot;
    static String workspaceName = "hi";
    static String logFile;
    static int winX = 67, winY = 73, winW = 890, winH = 550;

    public static void agentmain(String args, Instrumentation inst) {
        if (args != null && !args.isEmpty()) workspaceName = args.split(",")[0];
        logFile = "/tmp/mw_agent_final.log";

        log("=== MwAgentFinal loaded ===");
        log("Workspace: " + workspaceName);

        try {
            robot = new Robot();
            robot.setAutoDelay(50);
            log("Robot OK");
        } catch (AWTException e) {
            log("Robot error: " + e.getMessage());
            return;
        }

        robot.delay(2000);

        // Find and activate MotiveWave window + get actual geometry
        try {
            String id = execGet("xdotool search --name MotiveWave 2>/dev/null | tail -1").trim();
            if (!id.isEmpty()) {
                log("MW window: " + id);
                exec("xdotool windowactivate --sync " + id + " 2>/dev/null");
                robot.delay(1500);
                // Get actual window geometry
                String geo = execGet("xdotool getwindowgeometry " + id + " 2>/dev/null | grep -E 'Position|Geometry'").trim();
                log("Geo: " + geo.replace("\n", " | "));
                // Parse coordinates
                for (String line : geo.split("\n")) {
                    String nums = line.replaceAll("[^0-9]", " ").trim();
                    String[] parts = nums.split("\\s+");
                    if (line.contains("Position") && parts.length >= 2) {
                        winX = Integer.parseInt(parts[0]);
                        winY = Integer.parseInt(parts[1]);
                    } else if (line.contains("Geometry") && parts.length >= 2) {
                        winW = Integer.parseInt(parts[0]);
                        winH = Integer.parseInt(parts[1]);
                    }
                }
                log("Parsed: x=" + winX + " y=" + winY + " w=" + winW + " h=" + winH);
            }
        } catch (Exception e) {
            log("Window error: " + e.getMessage());
        }

        // Try strategies - mouse clicks first, then keyboard
        String[] strats = {
            "click_file_down_recent_right_down_enter",
            "click_file_r_enter",
            "click_file_r_down_enter",
            "click_title_ctrl_o_type",
            "ctrl_o_type_name",
            "alt_f_r_enter",
            "f10_nav"
        };
        for (String s : strats) {
            log("\n--- " + s + " ---");
            if (runStrategy(s)) { log("\n=== WORKSPACE LOADED ==="); return; }
            robot.delay(300);
        }
        log("All strategies exhausted.");
    }

    static boolean runStrategy(String s) {
        try {
            switch (s) {
                case "click_file_down_recent_right_down_enter":
                    // Click File menu, Down 8x to Recent Workspaces, Right, Down, Enter
                    clickFileMenu();
                    for (int i = 0; i < 8; i++) { pressDown(); robot.delay(200); }
                    pressRight(); robot.delay(1000);
                    pressDown(); robot.delay(300);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();

                case "click_file_r_enter":
                    // Click File, R (Recent Workspaces mnemonic), Enter
                    clickFileMenu();
                    typeLetter('R'); robot.delay(1500);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();

                case "click_file_r_down_enter":
                    // Click File, R, Down, Enter
                    clickFileMenu();
                    typeLetter('R'); robot.delay(1500);
                    pressDown(); robot.delay(400);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();

                case "click_title_ctrl_o_type":
                    // Click title bar to focus, Ctrl+O, type name
                    clickAt(winX + winW/2, winY + 10);
                    robot.delay(500);
                    ctrlO(); robot.delay(1500);
                    typeString(workspaceName); robot.delay(500);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();

                case "ctrl_o_type_name":
                    ctrlO(); robot.delay(1500);
                    typeString(workspaceName); robot.delay(500);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();

                case "alt_f_r_enter":
                    altF(); robot.delay(1200);
                    typeLetter('R'); robot.delay(1500);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();

                case "f10_nav":
                    robot.keyPress(KeyEvent.VK_F10); robot.delay(100);
                    robot.keyRelease(KeyEvent.VK_F10); robot.delay(1200);
                    for (int i = 0; i < 10; i++) { pressDown(); robot.delay(150); }
                    pressRight(); robot.delay(1000);
                    pressDown(); robot.delay(300);
                    pressEnter(); robot.delay(3000);
                    return checkConsole();
            }
        } catch (Exception e) {
            log("Error: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
        return false;
    }

    // ---- Mouse helpers ----

    static void clickFileMenu() {
        // File menu is at top-left of window
        clickAt(winX + 20, winY + 20);
        robot.delay(1000);
    }

    static void clickAt(int x, int y) {
        log("Click (" + x + "," + y + ")");
        robot.mouseMove(x, y);
        robot.delay(100);
        robot.mousePress(InputEvent.BUTTON1_DOWN_MASK);
        robot.delay(50);
        robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        robot.delay(300);
    }

    // ---- Keyboard helpers ----

    static void ctrlO() {
        log("Ctrl+O");
        robot.keyPress(KeyEvent.VK_CONTROL); robot.delay(50);
        robot.keyPress(KeyEvent.VK_O); robot.delay(100);
        robot.keyRelease(KeyEvent.VK_O); robot.delay(50);
        robot.keyRelease(KeyEvent.VK_CONTROL); robot.delay(1000);
    }

    static void altF() {
        log("Alt+F");
        robot.keyPress(KeyEvent.VK_ALT); robot.delay(50);
        robot.keyPress(KeyEvent.VK_F); robot.delay(100);
        robot.keyRelease(KeyEvent.VK_F); robot.delay(50);
        robot.keyRelease(KeyEvent.VK_ALT);
    }

    static void typeLetter(char c) {
        int k = toVk(c);
        boolean s = Character.isUpperCase(c);
        if (s) robot.keyPress(KeyEvent.VK_SHIFT);
        robot.keyPress(k); robot.delay(50); robot.keyRelease(k);
        if (s) robot.keyRelease(KeyEvent.VK_SHIFT);
    }

    static void typeString(String s) {
        for (char c : s.toCharArray()) {
            typeLetter(c);
            robot.delay(30);
        }
    }

    static void pressEnter() { robot.keyPress(KeyEvent.VK_ENTER); robot.delay(50); robot.keyRelease(KeyEvent.VK_ENTER); }
    static void pressDown() { robot.keyPress(KeyEvent.VK_DOWN); robot.delay(50); robot.keyRelease(KeyEvent.VK_DOWN); }
    static void pressRight() { robot.keyPress(KeyEvent.VK_RIGHT); robot.delay(50); robot.keyRelease(KeyEvent.VK_RIGHT); }

    static int toVk(char c) {
        char u = Character.toUpperCase(c);
        if (u >= 'A' && u <= 'Z') return KeyEvent.VK_A + (u - 'A');
        if (u >= '0' && u <= '9') return KeyEvent.VK_0 + (u - '0');
        return KeyEvent.VK_H;
    }

    // ---- Console check ----

    static boolean checkConsole() {
        try {
            String r = execGet("xdotool search --name Console 2>/dev/null").trim();
            boolean found = !r.isEmpty();
            log(found ? "Console found!" : "No Console");
            return found;
        } catch (Exception e) { log("Check error: " + e.getMessage()); return false; }
    }

    // ---- Exec helpers ----

    static String execGet(String cmd) throws Exception {
        Process p = Runtime.getRuntime().exec(new String[]{"bash", "-c", cmd});
        BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()));
        StringBuilder sb = new StringBuilder(); String line;
        while ((line = r.readLine()) != null) sb.append(line).append("\n");
        p.waitFor(); return sb.toString();
    }

    static void exec(String cmd) throws Exception {
        Runtime.getRuntime().exec(new String[]{"bash", "-c", cmd});
    }

    // ---- Logging ----

    static void log(String msg) {
        String ts = new java.text.SimpleDateFormat("HH:mm:ss").format(new java.util.Date());
        String line = "[" + ts + "] " + msg;
        System.out.println(line);
        try (FileWriter fw = new FileWriter(logFile, true); PrintWriter pw = new PrintWriter(fw)) {
            pw.println(line);
        } catch (IOException e) {}
    }
}
