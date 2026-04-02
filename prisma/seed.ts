import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

async function main() {
  // 1. Seed Config
  await prisma.config.upsert({
    where: { id: 1 },
    update: {},
    create: {
      appName: "RoboLab MVP Console",
      isaacHost: "localhost",
      isaacSessionMode: "launch_new",
      runnerMode: "LOCAL_RUNNER",
      isaacSshPort: 22,
      isaacUser: "max",
      isaacAuthMode: "password",
      sshKeyPath: "",
      isaacInstallPath: "C:\\Users\\max\\Documents\\IsaacSim",
      rosDomainId: 77,
      rosNamespace: "/tiago",
      rmwImplementation: "rmw_cyclonedds_cpp",
      cycloneDdsConfigPath: "",
      ros2SetupCommand: "",
      defaultOutputDir: "C:\\RoboLab_Data",
      streamingMode: "none",
      streamingHint: "",
      defaultRecordTopics: JSON.stringify([
        "/joint_states",
        "/tf",
        "/tf_static",
        "/odom",
        "/camera/color/image_raw",
        "/camera/depth/image_raw",
        "/camera/color/camera_info",
        "/points",
        "/gt/object_poses",
        "/cmd_vel",
        "/servo_server/delta_twist_cmds"
      ]),
      futurePlaceholders: JSON.stringify({}),
    },
  })

  // 2. Seed Scenes
  const officeScene = await prisma.scene.create({
    data: {
      name: "Office",
      type: "office",
      stageUsdPath: "C:\\RoboLab_Data\\scenes\\Office_Interactive.usd",
      capabilities: JSON.stringify(["pick_place_sink", "open_close_dishwasher"]),
      tags: JSON.stringify(["office", "desk", "interactive"]),
      robotSpawnPose: JSON.stringify({ x: 0, y: 0, z: 0, yaw: 0 }),
    }
  })

  const kitchenScene = await prisma.scene.create({
    data: {
      name: "Home Kitchen",
      type: "home",
      stageUsdPath: "C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd",
      capabilities: JSON.stringify(["pick_place_sink", "pick_place_fridge", "pick_place_dishwasher", "open_close_fridge", "open_close_dishwasher"]),
      tags: JSON.stringify(["home", "kitchen", "interactive"]),
      robotSpawnPose: JSON.stringify({ x: 1.0, y: -1.0, z: 0, yaw: 1.57 }),
    }
  })

  const kitchenFixedScene = await prisma.scene.create({
    data: {
      name: "Kitchen Fixed (Experiments 1-3)",
      type: "home",
      stageUsdPath: "C:\\RoboLab_Data\\scenes\\kitchen_fixed.usd",
      capabilities: JSON.stringify(["pick_place_table", "pick_place_sink", "open_close_fridge"]),
      tags: JSON.stringify(["home", "kitchen", "fixed", "experiments"]),
      robotSpawnPose: JSON.stringify({ x: 0.8, y: 0.0, z: 0.08, yaw: 0 }),
    }
  })

  const officeFixedScene = await prisma.scene.create({
    data: {
      name: "Office Fixed (Open-space)",
      type: "office",
      stageUsdPath: "C:\\RoboLab_Data\\scenes\\office_fixed.usd",
      capabilities: JSON.stringify(["navigation", "manipulation", "pick_place_table", "open_close_cabinet"]),
      tags: JSON.stringify(["office", "fixed", "open-space"]),
      robotSpawnPose: JSON.stringify({ x: 0, y: 0, z: 0, yaw: 0 }),
    }
  })

  // Experimental Office scene variants (disabled by default, opt-in via feature flag)
  const officeExperimentalPaths = [
    { name: "Office Studio (Experimental)", file: "Office_Studio_TiagoCompatible.usda" },
    { name: "Studio Office Interior (Experimental)", file: "Studio_Office_Interior_TiagoCompatible.usda" },
    { name: "Meeting Room (Experimental)", file: "Meeting_room_TiagoCompatible.usda" },
    { name: "Canonical Hologra Office (Experimental)", file: "Canonical_Hologra_Office_TiagoCompatible.usda" },
  ];
  for (const officeVariant of officeExperimentalPaths) {
    await prisma.scene.create({
      data: {
        name: officeVariant.name,
        type: "office",
        stageUsdPath: `C:\\RoboLab_Data\\scenes\\${officeVariant.file}`,
        capabilities: JSON.stringify(["navigation", "pick_place_table"]),
        tags: JSON.stringify(["office", "experimental"]),
        robotSpawnPose: JSON.stringify({ x: 0, y: 0, z: 0, yaw: 0 }),
        enabled: false,
      }
    })
  }

  // 3. Seed Launch Profile for GUI + MoveIt teleop
  const guiTeleopProfile = await prisma.launchProfile.create({
    data: {
      name: "GUI + MoveIt Teleop (Local)",
      runnerMode: "LOCAL_RUNNER",
      scriptName: "data_collector_tiago.py",
      environmentUsd: "C:\\RoboLab_Data\\scenes\\kitchen_fixed.usd",
      enableWebRTC: false,
      enableGuiMode: true,
      enableVrTeleop: false,
      enableMoveIt: true,
      robotPovCameraPrim: "/World/Tiago",
      ros2SetupCommand: "call C:\\Users\\max\\mambaforge\\envs\\ros2_humble\\Library\\local_setup.bat",
      teleopLaunchTemplate: 'powershell.exe -ExecutionPolicy Bypass -File "{PROJECT}\\scripts\\start_moveit_stack.ps1" -PidFile "{OUTPUT_DIR}\\moveit_stack.pids" -IntentTopic "/tiago/moveit/intent" -RosDomainId 77',
      stopTemplate: 'powershell.exe -ExecutionPolicy Bypass -File "{PROJECT}\\scripts\\start_moveit_stack.ps1" -Stop',
    }
  })

  await prisma.launchProfile.create({
    data: {
      name: "Office Experimental (Local)",
      runnerMode: "LOCAL_RUNNER",
      scriptName: "data_collector_tiago.py",
      environmentUsd: "C:\\RoboLab_Data\\scenes\\Office_Studio_TiagoCompatible.usda",
      enableWebRTC: false,
      enableGuiMode: true,
      enableVrTeleop: false,
      enableMoveIt: true,
      robotPovCameraPrim: "/World/Tiago",
      ros2SetupCommand: "call C:\\Users\\max\\mambaforge\\envs\\ros2_humble\\Library\\local_setup.bat",
      teleopLaunchTemplate: 'powershell.exe -ExecutionPolicy Bypass -File "{PROJECT}\\scripts\\start_moveit_stack.ps1" -PidFile "{OUTPUT_DIR}\\moveit_stack.pids" -IntentTopic "/tiago/moveit/intent" -RosDomainId 77',
      stopTemplate: 'powershell.exe -ExecutionPolicy Bypass -File "{PROJECT}\\scripts\\start_moveit_stack.ps1" -Stop',
      enabled: false,
    }
  })

  // 4. Seed Object Sets
  const kitchenObjects = await prisma.objectSet.create({
    data: {
      name: "Kitchen Mixed Objects",
      categories: JSON.stringify(["mugs", "bottles", "fruits", "containers"]),
      assetPaths: JSON.stringify([
        "/Props/mugs/mug_01.usd",
        "/Props/bottles/bottle_01.usd",
        "/Props/fruits/apple.usd",
        "/Props/containers/box_01.usd"
      ]),
      notes: "Default objects for pick and place in kitchen",
    }
  })

  console.log("Seeding complete.")
  console.log({ officeScene, kitchenScene, guiTeleopProfile, kitchenObjects })
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(async () => {
    await prisma.$disconnect()
  })
