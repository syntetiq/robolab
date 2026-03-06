import re

with open("scripts/data_collector_tiago.py", "r") as f:
    content = f.read()

# Make sure replication/simulation is stopped completely before App teardown
old_teardown = """
        print(f"[RoboLab] Episode completed successfully. Output saved to: {args.output_dir}")
        simulation_app.close()
"""

new_teardown = """
        print(f"[RoboLab] Episode completed successfully. Output saved to: {args.output_dir}")
        print("[RoboLab] Cleaning up Isaac Sim Session...")
        world.stop()
        simulation_app.update()
        import omni.replicator.core as rep
        rep.orchestrator.stop()
        simulation_app.update()
        simulation_app.close()
"""

if old_teardown in content:
    content = content.replace(old_teardown, new_teardown)
else:
    print("Warning: old teardown not found! It might already be patched.")

with open("scripts/data_collector_tiago.py", "w") as f:
    f.write(content)
