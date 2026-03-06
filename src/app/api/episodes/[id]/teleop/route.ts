import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { NodeSSH } from "node-ssh";

const getConfig = () => {
    return {
        isaacHost: process.env.ISAAC_HOST || "192.168.0.21",
        isaacSshPort: parseInt(process.env.ISAAC_SSH_PORT || "22"),
        isaacUser: process.env.ISAAC_USER || "max",
        isaacAuthMode: process.env.ISAAC_AUTH_MODE || "password",
        sshPassword: process.env.SSH_PASSWORD || "3101",
        isaacInstallPath: process.env.ISAAC_INSTALL_PATH || "C:\\Users\\max\\Documents\\IsaacSim"
    };
};

export async function POST(
    req: NextRequest,
    { params }: { params: { id: string } }
) {
    try {
        const episode = await prisma.episode.findUnique({
            where: { id: params.id },
            include: { launchProfile: true }
        });
        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });

        const body = await req.json();
        const command = body.command;

        if (!command) {
            return NextResponse.json({ error: "No command provided" }, { status: 400 });
        }

        const config = getConfig();
        const ssh = new NodeSSH();

        // MVP Connection Setup (replicated from SshRunner)
        const hostPath = config.isaacHost.split('@');
        const username = hostPath.length > 1 ? hostPath[0] : 'max';
        const host = hostPath.length > 1 ? hostPath[1] : config.isaacHost;

        await ssh.connect({
            host: host,
            port: config.isaacSshPort,
            username: config.isaacUser || username,
            password: config.sshPassword
        });

        console.log(`[Teleop] Executing ${command} on ${host} for episode ${episode.id}`);

        // Translate UI commands to ROS2 Twist or JointTrajectory payloads
        // For MVP, we will send basic python snippet execution or ros2 topic pub over SSH

        let sshCmd = "";

        // Assuming Isaac Sim's bundled python or standard ROS2 under WSL/Ubuntu. 
        // For this Windows host, we can drop a quick python snippet that publishes to localhost ROS2 UDP

        if (command === "move_forward") {
            // MVP Example: Sending a dummy message for demonstration on the logs. 
            // In full ROS2 node: `ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"`
            sshCmd = `powershell -Command "echo '[Teleop Web] Pushing Forward Command' >> C:\\RoboLab_Data\\episodes\\${episode.id}_stdout.log"`;
        } else if (command === "move_backward") {
            sshCmd = `powershell -Command "echo '[Teleop Web] Pushing Backward Command' >> C:\\RoboLab_Data\\episodes\\${episode.id}_stdout.log"`;
        } else if (command === "move_left") {
            sshCmd = `powershell -Command "echo '[Teleop Web] Pushing Left Turn Command' >> C:\\RoboLab_Data\\episodes\\${episode.id}_stdout.log"`;
        } else if (command === "move_right") {
            sshCmd = `powershell -Command "echo '[Teleop Web] Pushing Right Turn Command' >> C:\\RoboLab_Data\\episodes\\${episode.id}_stdout.log"`;
        } else if (command === "grasp_mug") {
            // Emulate MoveIt trajectory trigger
            sshCmd = `powershell -Command "echo '[Teleop Web] Commencing IK Grasp Trajectory...' >> C:\\RoboLab_Data\\episodes\\${episode.id}_stdout.log"`;
        } else if (command === "go_home") {
            sshCmd = `powershell -Command "echo '[Teleop Web] Returning arm to home pose...' >> C:\\RoboLab_Data\\episodes\\${episode.id}_stdout.log"`;
        } else {
            return NextResponse.json({ error: "Unknown command" }, { status: 400 });
        }

        const result = await ssh.execCommand(sshCmd);
        ssh.dispose();

        if (result.code !== 0) {
            console.error("[Teleop Error]", result.stderr);
            return NextResponse.json({ error: "Failed to dispatch command to host" }, { status: 500 });
        }

        return NextResponse.json({ success: true, command });
    } catch (e: any) {
        console.error("[Teleop] Error processing command:", e.message);
        return NextResponse.json({ error: e.message }, { status: 500 });
    }
}
