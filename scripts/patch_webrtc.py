import re

with open("scripts/data_collector_tiago.py", "r") as f:
    content = f.read()

# Replace old webrtc extension name with the correct one that Isaac Sim 4.0.0+ uses
new_content = content.replace('enable_extension("omni.services.streamclient.webrtc")', 'enable_extension("omni.services.streamclient.webrtc")')
# Wait, Isaac Sim uses omni.services.streamclient.webrtc natively in 2023.1, but in 4.1 it was renamed to omni.kit.livestream.webrtc
new_content = new_content.replace('enable_extension("omni.services.streamclient.webrtc")', 'enable_extension("omni.kit.livestream.webrtc")')

with open("scripts/data_collector_tiago.py", "w") as f:
    f.write(new_content)
