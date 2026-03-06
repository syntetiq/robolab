import re

with open("scripts/data_collector_tiago.py", "r") as f:
    content = f.read()

# Replace the graph setup part with a delayed setup mechanism
old_setup = """
print("[RoboLab] Setting up ROS 2 Action Graphs...")
keys = og.Controller.Keys
(ros2_graph, _, _, _) = og.Controller.edit(
"""

new_setup = """
print("[RoboLab] Stepping app once to allow OmniGraph nodes to register...")
simulation_app.update()
simulation_app.update()

print("[RoboLab] Setting up ROS 2 Action Graphs...")
keys = og.Controller.Keys
(ros2_graph, _, _, _) = og.Controller.edit(
"""

content = content.replace(old_setup, new_setup)

with open("scripts/data_collector_tiago.py", "w") as f:
    f.write(content)
