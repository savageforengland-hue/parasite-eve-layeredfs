"""Safely stage an explicitly named replacement background for the existing LayeredFS sync.

No assumptions are made about the upstream room IDs or filenames. This command
requires a confirmed filename and a user-created replacement image.
"""
import argparse
import shutil
from pathlib import Path

VALID_STAGES = {"exposed", "infested", "overrun"}
VALID_EXTS = {".png", ".webp"}


def stage_background(source: Path, output_root: Path, target_name: str, infection_stage: str, *, apply=False) -> Path:
    if infection_stage not in VALID_STAGES:
        raise ValueError("stage must be exposed, infested, or overrun")
    if not target_name or Path(target_name).name != target_name or target_name in {".", ".."}:
        raise ValueError("target_name must be a filename, not a path")
    if Path(target_name).suffix.lower() not in VALID_EXTS:
        raise ValueError("target filename must end in .png or .webp")
    if source.suffix.lower() not in VALID_EXTS or not source.is_file():
        raise ValueError("source must be an existing PNG or WebP file")
    # By default, stage into an isolated preview directory. Applying is an
    # explicit second step after confirming the real game's background name.
    relative = Path("mods/layeredfs/romfs/HD_BACKGROUNDS") if apply else Path("regenesis/previews") / infection_stage
    destination = output_root / relative / target_name
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination cannot be the same")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing asset: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description="Stage a REGENESIS infected background safely")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--target-name", required=True, help="Confirmed native override filename")
    parser.add_argument("--stage", choices=sorted(VALID_STAGES), required=True)
    parser.add_argument("--apply", action="store_true", help="Copy to LayeredFS override staging; never overwrite")
    args = parser.parse_args()
    print(stage_background(args.source, args.root, args.target_name, args.stage, apply=args.apply))


if __name__ == "__main__":
    main()
