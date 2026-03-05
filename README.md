# RoboLab MVP Console

A self-hosted MVP web application operator console for configuring and running teleoperation data-collection experiments in Isaac Sim using TIAGo Omni / TIAGo++.

## Features

- **Configuration Management**: Configure Isaac Sim host, user, ROS2 topics, streaming methods.
- **Scene and Object Set Management**: Maintain a library of scenes and object sets for task diversity.
- **Launch Profiles**: Customizable ROS and Isaac Sim command templates per runner type.
- **Episodes (Data Collection Runs)**: Step-by-step wizard to define metadata (Tasks, Sensors, Duration) and execute data logging safely.
- **Runner Abstraction**: Expandable architecture to run jobs locally (`LOCAL_RUNNER`), remotely via SSH (`SSH_RUNNER`), or via future agent orchestrators (`AGENT_RUNNER`).
- **Interactive UI**: Clean, responsive layout with Tailwind CSS and Next.js App Router. Features Server-Sent Events (SSE) for live streaming logs and status updates to the Episode Detail page.

## Prerequisite

- Node.js 20+
- npm

## Setup & Run

1. **Install Dependencies**
   ```bash
   npm install
   ```

2. **Initialize Database**
   Since this uses SQLite, Prisma schema is pre-configured. Generate the client and run the seed script:
   ```bash
   npx prisma generate
   npx prisma db push
   npx prisma db seed
   ```
   > The seed script automatically supplies initial defaults: Config `192.168.0.21`, scenes for Home and Office, and a demo Object Set.

3. **Run Development Server**
   ```bash
   npm run dev
   ```
   The application will be accessible at [http://localhost:3000](http://localhost:3000).

## Testing

This project uses `vitest` for unit tests. To run tests:

```bash
npm run test
```

Tests ensure correctness of Configuration Zod Schemas, the `HostLock` concurrent episode runner locking logic, and the `Runner` factory.

## Future Hooks

- **ROS2 & MoveIt**: Hooks in the Episode runner logic allow injecting pre/post-operation verification scripts.
- **Agent API**: The `AGENT_RUNNER` stub expects cloud-based task definitions in a later iteration.
- **Teleoperation**: The Dashboard and Episode pages render explicit setup instructions when external WebRTC streaming Mode is configured for the Vive VR headsets.
