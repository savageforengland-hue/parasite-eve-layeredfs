# Parasite Eve PC Recompilation (v0.12-alpha+) — LayeredFS Asset Override System

Updated for the latest [`khasinski/parasite-eve-pc` v0.12-alpha release and `main` branch](https://github.com/khasinski/parasite-eve-pc/releases) ([Mods Documentation](https://github.com/khasinski/parasite-eve-pc/blob/main/mods/README.md), [Decompilation Repository](https://github.com/khasinski/parasite-eve-decomp)).

## What's New for `0.12-alpha` / `main`

- **`.chd` & `.bin`/`.cue` Disc Support**: Reads both MAME `.chd` v5 images (`chdman createcd`) and `.bin`/`.cue` images.
- **North American & Japanese Disc Regions**: Auto-detects `SLUS_006.62` / `SLUS_006.68` (USA) and `SLPS_012.30` / `SLPS_012.31` (JPN).
- **Portable Mode (`portable.txt` / `userdata/`) & `PE_CONFIG_HOME`**: Automatically resolves and syncs overrides when `0.12-alpha` runs in portable mode.
- **Unified `romfs/` Routing for All `0.12-alpha` Asset Subsystems**:
  - `romfs/DISC1/` & `romfs/DISC2/`: Granular `PE.IMG` package and 12-category sub-asset splicing ([ZenHAX PE.IMG Spec](https://zenhax.com/viewtopic.php@t=14615.html)).
  - `romfs/SKINS/` & `romfs/PACKS/`: Syncs Wardrobe skins (`pe_skins/`) and `pack.json` v1 character packs (`packs/`) for `pe_wardrobe`.
  - `romfs/FONTS/`: Syncs custom `.png` dialogue fonts into `mods/fonts/` (`pe_fonts` / `PE_HOOK_TIM_UPLOAD`).
  - `romfs/CALLS/`: Syncs custom phone call scripts into `pe_calls/` (`pe_phone`).
  - `romfs/LANG/`: Syncs `.pelang` language packs into `lang/` (`pe_lang`).
  - `romfs/HD_BACKGROUNDS/`: Syncs WebP/PNG HD background layers into `backgrounds/` for immediate scene reload.
