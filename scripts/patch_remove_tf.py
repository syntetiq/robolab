import re

with open("scripts/data_collector_tiago.py", "r") as f:
    content = f.read()

# Delete the ROS 2 Action Graph Setup entirely to ensure it doesn't crash 
# since I don't need ROS2 TF for pure WebRTC teleop via the Next.js API right now.
patch_start = 'print("[RoboLab] Stepping app once to allow OmniGraph nodes to register...")'
patch_end = '# Configure Replicator to use our generated ground truth bounding boxes'

if patch_start in content and patch_end in content:
    pre = content.split(patch_start)[0]
    post = content.split(patch_end)[1]
    new_content = pre + patch_end + post
    with open("scripts/data_collector_tiago.py", "w") as f:
        f.write(new_content)
    print("Action Graph successfully removed for debugging.")
else:
    print("Error: Could not find patch markers in data_collector_tiago.py")
