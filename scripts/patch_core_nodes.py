with open("scripts/data_collector_tiago.py", "r") as f:
    content = f.read()

patch = """
    # Extensions needed for headless ActionGraph
    from omni.isaac.core.utils.extensions import enable_extension
    enable_extension("omni.isaac.ros2_bridge")
    enable_extension("omni.replicator.isaac")
    enable_extension("omni.isaac.synthetic_utils")
    enable_extension("omni.isaac.core_nodes")
"""

content = content.replace('    enable_extension("omni.isaac.synthetic_utils")', '    enable_extension("omni.isaac.synthetic_utils")\n    enable_extension("omni.isaac.core_nodes")')

with open("scripts/data_collector_tiago.py", "w") as f:
    f.write(content)
