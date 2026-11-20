# Parasite Eve: REGENESIS — Expansion Design v0.1

Fan-made concept and development specification. No copyrighted game data bundled. Not yet playable.

## Pillars

1. Biological survival horror: living spaces, dread, scarce resources, and audio cues.
2. Tactical mitochondrial combat: new abilities with risk/reward costs.
3. Reversible native mod: original campaign and assets remain available.
4. Authored encounters: predictable triggers for testing; optional adaptive mutations later.

## Campaign

A post-game outbreak connects nervous systems beneath New York. Aya investigates a distributed organism that preserves fragments of its victims' memories.

| Chapter | Location | Core mechanic | Boss |
|---|---|---|---|
| 1 | Central Park: The Red Garden | Infection thresholds and environmental hazards | Weeping Stag |
| 2 | The Hollow Line | Power/visibility and pursuit | The Conductor |
| 3 | St. Lazarus Medical Institute | Contamination and medical puzzles | The Surgeon |
| 4 | The Womb | Living maze and adaptive encounters | The Matriarch |

## Enemy prototypes

| ID | Enemy | Mechanic | Counterplay |
|---|---|---|---|
| RG_STAG | Weeping Stag | Mimics cries, charges from cover | Telegraph audio and lateral dodge |
| RG_HOLLOW | Hollowed | Armor shell cracks under sustained fire | Armor-breaking ammunition |
| HL_WIRE | Wiregnaw | Disables lights and electrical traps | Shock resistance / targeted cables |
| HL_CHOIR | Choir | Sound-based group disorientation | Break line of sight and silence source |
| SL_ORDERLY | Orderly | Injects contamination on grab | Interrupt and antiseptic consumable |
| SL_GRAFT | Graft | Regenerates unless growth nodes destroyed | Target weak points |
| WB_SPAWN | Wombspawn | Splits when struck by certain attacks | Thermal damage and crowd control |

## Weapons

| ID | Weapon | Role | Drawback |
|---|---|---|---|
| W_SABLE | Sable-9 pistol | Accurate sidearm, modest ammo usage | Weak against armored shells |
| W_BREACH | Breach shotgun | Close-range stagger and armor breaking | Slow reload |
| W_ARC | Arc carbine | Electrical suppression | Limited capacitor charge |
| W_CAUTER | Cauterizer | Destroys regenerative tissue | Heat buildup |

## Parasite Energy concepts

| ID | Ability | Effect | Cost / risk |
|---|---|---|---|
| PE_PULSE | Mitochondrial Pulse | Reveals hidden growth nodes | PE cost, alerts sensitive enemies |
| PE_SEAR | Sear | Focused heat damage and regeneration denial | High PE cost |
| PE_VEIL | Veil | Briefly reduces enemy detection | Short duration, movement breaks effect |
| PE_PURGE | Purge | Clears contamination at a health cost | HP sacrifice |
| PE_ECHO | Echo | Exposes memory traces for puzzles | Increases local infection briefly |

## Systems

- Infection state: 0..100 per room, initially offline prototype in `regenesis/infection.py`.
- Contamination: separate character debuff; **not** automatically the same as room infection.
- Threat director: authored spawn pools with cooldowns and safe rooms; deterministic seeded tests first.
- Resource scarcity: ammunition, PE restoratives and antiseptic consumables.
- Save compatibility: never write into native save files until API is verified; maintain separate mod state.
- Original-game fallback: every missing replacement uses original resources.

## Technical milestones and acceptance criteria

### M0 — Asset loader discovery
- Identify installed release build and HD atlas naming and manifest format.
- Obtain screenshot metadata or extracted original room mapping.
- Verify Central Park M374 checkpoint, **not** assume it is the screenshot room.

### M1 — First playable scene
- Compile with PE_MODS=ON and a dedicated pe_regenesis module.
- Static room asset replacement displays with correct original depth, animation and collision.
- Mod disable restores original scene.

### M2 — Enemy vertical slice
- One enemy with spawn, attack, death and drop, verified in actual combat.
- No crash on room transition, save/load, battle exit.

### M3 — Ability and weapon vertical slice
- One weapon and one Parasite Energy ability with UI, costs and persistence.
- Automated simulation and manual game tests.

### M4 — Chapter 1
- Connected Central Park rooms, first boss, progression, checkpoint and audio.

### M5 — Full campaign
- Chapters 2–4, QA, packaging, compatibility and optional endings.

## Current implementation status

Design only for enemies, areas, weapons, spells and story. Infection simulation and safe asset staging are committed separately. No new enemies, maps, weapons or abilities are yet running in the game. This document defines the implementation backlog, not completed functionality.
