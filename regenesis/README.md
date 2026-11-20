# Parasite Eve: REGENESIS

Experimental fan-made expansion framework for the khasinski Parasite Eve PC recompilation.

## Milestone 0.1: Infection-state prototype

This milestone supplies a standalone, standard-library-only Python infection-state engine and tests. It does **not** yet patch the game executable, load assets in-game, or change enemy AI. The next integration step is to connect actual room transitions and background reload hooks in the upstream recompilation.

## Run

From the repository root:

```sh
python -m unittest discover -s regenesis/tests -v
python regenesis/infection.py --state regenesis_state.json --room museum_hall --encounters 2
```

The command records an infection level for a room, prints the corresponding visual stage, and writes a JSON save file atomically. The JSON is a prototype state format, **not** a Parasite Eve save format.

## Visual stage contract

- 0-24: clean
- 25-49: exposed
- 50-74: infested
- 75-100: overrun

These are design defaults, not claims about existing game APIs. For asset staging, see the existing `mods/layeredfs/romfs/HD_BACKGROUNDS/` directory. Real room identifiers and background file names must be obtained from an indexed, user-owned disc and upstream mod documentation. Do not redistribute original game assets.

## Next integration work

1. Validate upstream background override naming and reload semantics against the exact recompilation build.
2. Resolve a real room ID and create an original infected replacement image matching its camera geometry.
3. Connect room-entry and battle-end callbacks to infection updates.
4. Add a toggle and safe fallback to original backgrounds.
5. Verify in-game, then prototype enemy variants and mitochondrial abilities.
