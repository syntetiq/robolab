import { PrismaClient } from '@prisma/client'
const prisma = new PrismaClient()

async function main() {
  const profile = await prisma.launchProfile.create({
      data: {
          name: "Office Teleop VR",
          scriptName: "data_collector_tiago.py",
          environmentUsd: "C:\\RoboLab_Data\\scenes\\Office_Data.usd",
          isaacLaunchTemplate: "",
          enableWebRTC: true
      }
  })
  console.log("Created Profile:", profile.id)
}

main()
  .catch((e) => console.error(e))
  .finally(async () => await prisma.$disconnect())
