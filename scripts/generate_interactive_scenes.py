from create_interactive_scenes import generate_scene
from pathlib import Path
import argparse


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compatibility wrapper for scene generation.")
    parser.add_argument("--output-dir", type=str, default="C:\\RoboLab_Data\\scenes")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    try:
        output_dir = Path(args.output_dir)
        generate_scene("small_house", output_dir / "Small_House_Interactive.usd", args.seed)
        generate_scene("office", output_dir / "Office_Interactive.usd", args.seed)
        print("[RoboLab] Generated Small House and Office scenes.")
    finally:
        app.close()
