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

  // 3. Seed Object Sets
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
  console.log({ officeScene, kitchenScene, kitchenObjects })
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(async () => {
    await prisma.$disconnect()
  })
