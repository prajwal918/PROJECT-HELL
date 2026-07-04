import com.sun.tools.attach.VirtualMachine;

/**
 * LoadAgent — Attaches to a running JVM by PID and loads a Java agent.
 * Uses the standard com.sun.tools.attach API.
 */
public class LoadAgent {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: java LoadAgent <pid> <agent-jar-path> [options]");
            System.exit(1);
        }
        String pid = args[0];
        String jarPath = args[1];
        String options = args.length > 2 ? args[2] : "";

        System.out.println("=== LoadAgent ===");
        System.out.println("Target PID: " + pid);
        System.out.println("Agent JAR: " + jarPath);
        System.out.println("Options: " + (options.isEmpty() ? "(none)" : options));

        VirtualMachine vm = VirtualMachine.attach(pid);
        System.out.println("Attached to PID " + pid);

        try {
            vm.loadAgent(jarPath, options);
            System.out.println("Agent loaded successfully!");
        } catch (Exception e) {
            System.err.println("ERROR loading agent: " + e.getClass().getName() + ": " + e.getMessage());
        } finally {
            vm.detach();
            System.out.println("Detached from PID " + pid);
        }
    }
}
