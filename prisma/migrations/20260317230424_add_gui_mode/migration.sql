-- CreateTable
CREATE TABLE "Config" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT DEFAULT 1,
    "appName" TEXT NOT NULL DEFAULT 'RoboLab MVP Console',
    "isaacHost" TEXT NOT NULL DEFAULT 'localhost',
    "isaacSessionMode" TEXT NOT NULL DEFAULT 'launch_new',
    "runnerMode" TEXT NOT NULL DEFAULT 'LOCAL_RUNNER',
    "isaacSshPort" INTEGER NOT NULL DEFAULT 22,
    "isaacUser" TEXT NOT NULL DEFAULT 'max',
    "isaacAuthMode" TEXT NOT NULL DEFAULT 'password',
    "sshKeyPath" TEXT NOT NULL DEFAULT '',
    "sshPassword" TEXT NOT NULL DEFAULT '',
    "isaacInstallPath" TEXT NOT NULL DEFAULT 'C:\Users\max\Documents\IsaacSim',
    "rosDomainId" INTEGER NOT NULL DEFAULT 77,
    "rosNamespace" TEXT NOT NULL DEFAULT '/tiago',
    "rmwImplementation" TEXT NOT NULL DEFAULT 'rmw_cyclonedds_cpp',
    "cycloneDdsConfigPath" TEXT NOT NULL DEFAULT '',
    "ros2SetupCommand" TEXT NOT NULL DEFAULT '',
    "defaultOutputDir" TEXT NOT NULL DEFAULT 'C:\RoboLab_Data',
    "streamingMode" TEXT NOT NULL DEFAULT 'none',
    "streamingHint" TEXT NOT NULL DEFAULT '',
    "defaultRecordTopics" TEXT NOT NULL DEFAULT '[]',
    "futurePlaceholders" TEXT NOT NULL DEFAULT '{}',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "Scene" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "stageUsdPath" TEXT NOT NULL,
    "mapPath" TEXT,
    "robotSpawnPose" TEXT NOT NULL DEFAULT '{}',
    "capabilities" TEXT NOT NULL DEFAULT '[]',
    "notes" TEXT NOT NULL DEFAULT '',
    "tags" TEXT NOT NULL DEFAULT '[]',
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "ObjectSet" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "categories" TEXT NOT NULL DEFAULT '[]',
    "assetPaths" TEXT NOT NULL DEFAULT '[]',
    "notes" TEXT NOT NULL DEFAULT '',
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "LaunchProfile" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "runnerMode" TEXT NOT NULL DEFAULT 'SSH_RUNNER',
    "scriptName" TEXT NOT NULL DEFAULT 'data_collector_tiago.py',
    "environmentUsd" TEXT NOT NULL DEFAULT 'C:\RoboLab_Data\scenes\Small_House_Interactive.usd',
    "enableWebRTC" BOOLEAN NOT NULL DEFAULT false,
    "enableGuiMode" BOOLEAN NOT NULL DEFAULT false,
    "enableVrTeleop" BOOLEAN NOT NULL DEFAULT false,
    "enableMoveIt" BOOLEAN NOT NULL DEFAULT false,
    "robotPovCameraPrim" TEXT NOT NULL DEFAULT '/World/Tiago',
    "ros2SetupCommand" TEXT NOT NULL DEFAULT '',
    "isaacLaunchTemplate" TEXT NOT NULL DEFAULT '',
    "rosbagLaunchTemplate" TEXT NOT NULL DEFAULT '',
    "teleopLaunchTemplate" TEXT NOT NULL DEFAULT '',
    "stopTemplate" TEXT NOT NULL DEFAULT '',
    "environmentOverrides" TEXT NOT NULL DEFAULT '{}',
    "enabled" BOOLEAN NOT NULL DEFAULT true
);

-- CreateTable
CREATE TABLE "Episode" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "sceneId" TEXT NOT NULL,
    "objectSetId" TEXT,
    "launchProfileId" TEXT,
    "tasks" TEXT NOT NULL DEFAULT '[]',
    "sensors" TEXT NOT NULL DEFAULT '[]',
    "randomizationConfig" TEXT NOT NULL DEFAULT '{}',
    "seed" INTEGER NOT NULL DEFAULT 42,
    "durationSec" INTEGER NOT NULL DEFAULT 60,
    "status" TEXT NOT NULL DEFAULT 'created',
    "startedAt" DATETIME,
    "stoppedAt" DATETIME,
    "outputDir" TEXT NOT NULL DEFAULT '',
    "bagPath" TEXT NOT NULL DEFAULT '',
    "metadataPath" TEXT NOT NULL DEFAULT '',
    "frozenConfigSnapshot" TEXT NOT NULL DEFAULT '{}',
    "notes" TEXT NOT NULL DEFAULT '',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Episode_sceneId_fkey" FOREIGN KEY ("sceneId") REFERENCES "Scene" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "Episode_objectSetId_fkey" FOREIGN KEY ("objectSetId") REFERENCES "ObjectSet" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "Episode_launchProfileId_fkey" FOREIGN KEY ("launchProfileId") REFERENCES "LaunchProfile" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "HostLock" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "host" TEXT NOT NULL,
    "episodeId" TEXT NOT NULL,
    "lockType" TEXT NOT NULL DEFAULT 'interactive_session',
    "acquiredAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "HostLock_host_key" ON "HostLock"("host");
