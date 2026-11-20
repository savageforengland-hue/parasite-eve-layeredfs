"""Standalone infection-state prototype; no in-game hooks yet."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

STAGES = ((25, "clean"), (50, "exposed"), (75, "infested"), (101, "overrun"))


def clamp(value: int) -> int:
    return max(0, min(100, int(value)))


def stage(level: int) -> str:
    level = clamp(level)
    return next(name for ceiling, name in STAGES if level < ceiling)


class InfectionState:
    def __init__(self, rooms: dict[str, int] | None = None):
        self.rooms = {str(k): clamp(v) for k, v in (rooms or {}).items()}

    def level(self, room: str) -> int:
        return self.rooms.get(room, 0)

    def advance(self, room: str, encounters: int = 1, points_per_encounter: int = 8) -> int:
        if not room or not room.strip():
            raise ValueError("room must be nonempty")
        if encounters < 0 or points_per_encounter < 0:
            raise ValueError("encounters and points must be nonnegative")
        self.rooms[room] = clamp(self.level(room) + encounters * points_per_encounter)
        return self.rooms[room]

    def visual_stage(self, room: str) -> str:
        return stage(self.level(room))

    @classmethod
    def load(cls, path: Path) -> "InfectionState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("rooms"), dict):
            raise ValueError("unsupported infection state")
        if any(not isinstance(v, int) or isinstance(v, bool) for v in data["rooms"].values()):
            raise ValueError("room levels must be integers")
        return cls(data["rooms"])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                    prefix=".regenesis-", suffix=".tmp", delete=False) as f:
                tmp_path = Path(f.name)
                json.dump({"version": 1, "rooms": self.rooms}, f, indent=2, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="REGENESIS offline infection-state prototype")
    parser.add_argument("--state", type=Path, default=Path("regenesis_state.json"))
    parser.add_argument("--room", required=True)
    parser.add_argument("--encounters", type=int, default=1)
    args = parser.parse_args()
    state = InfectionState.load(args.state)
    level = state.advance(args.room, args.encounters)
    state.save(args.state)
    print(f"{args.room}: infection={level}/100 visual_stage={state.visual_stage(args.room)}")


if __name__ == "__main__":
    main()
