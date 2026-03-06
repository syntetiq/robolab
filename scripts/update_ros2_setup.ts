import { PrismaClient } from "@prisma/client";
const p = new PrismaClient();
const setup =
  "call C:\\Users\\max\\Mambaforge\\envs\\ros2_humble\\Library\\local_setup.bat";

Promise.all([
  p.config.update({ where: { id: 1 }, data: { ros2SetupCommand: setup } }),
  p.launchProfile.updateMany({ data: { ros2SetupCommand: setup } }),
]).then(([, r]) => {
  console.log("Config ros2SetupCommand updated");
  console.log("LaunchProfiles updated:", r.count);
  p.$disconnect();
});
