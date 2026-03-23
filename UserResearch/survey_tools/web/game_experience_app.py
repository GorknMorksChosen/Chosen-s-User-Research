import runpy
from pathlib import Path


def main():
    base_dir = Path(__file__).resolve().parents[2]
    script_path = base_dir / "game_analyst.py"
    runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()

