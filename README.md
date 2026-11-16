# Parasite Eve LayeredFS

**A community-made LayeredFS asset override toolkit for the [Parasite Eve PC recompilation](https://github.com/khasinski/parasite-eve-pc).**

Targeting **v0.12-alpha / main**, this project provides a Python disc-indexing and override-cache tool, ready-made mod folders, Windows helper scripts, and C sources for native integration. Its goal is to let modders replace selected assets while leaving everything else on the original disc.

> **Project status: experimental.** The repository contains source code and tooling, not a prebuilt or verified plug-and-play mod. End-to-end compatibility and in-game behavior have not yet been independently verified. See [Limitations](#limitations-and-status).

## Features

- **Disc indexing:** Python tooling for raw `.bin` images (including typical `.bin/.cue` sets), 2048-byte-sector `.iso` images, and a CHD v5 reader. CHD handling may need further testing with particular compression formats.
- **Two discs, two regions:** Recognition logic for North American `SLUS_006.62` / `SLUS_006.68` and Japanese `SLPS_012.30` / `SLPS_012.31` releases.
- **Selective asset replacement:** Mirror `DISC1` / `DISC2` and `PE.IMG` packages into a mod-friendly directory tree. Unmodified files are intended to fall back to the original game data.
- **PE.IMG sub-assets:** Category folders for scripts, models, animations, sound, textures, backgrounds and other package content (types `00`–`12`).
- **Mod folder synchronization:** Copy skins, character packs, dialogue fonts, phone calls, language files and HD backgrounds into the locations expected by the companion PC project.
- **Override-cache generation:** Compile matching disc-level replacements into `mods/layeredfs/override_cache.bin`.
- **Optional virtual disc:** For non-CHD inputs, the Python tool can create a patched `.bin` and `.cue` without intentionally modifying the original source image.
- **Native integration sources:** A C LayeredFS implementation and CMake fragment are supplied for developers integrating with the host project.

## Requirements

| Requirement | Details |
| --- | --- |
| Host project | [khasinski/parasite-eve-pc](https://github.com/khasinski/parasite-eve-pc), with integration matched to its current source and mod APIs |
| Python | Python 3, available as `python` on your command line; the Python tool uses standard-library modules |
| Disc data | Your own legally obtained Parasite Eve disc image(s); original game data is **not** included |
| Windows helpers | Windows for the included `.bat` scripts; the Python CLI can also be run directly on other operating systems |
| Native C integration | A working build environment for the upstream PC recompilation and its CMake target |

**Note:** Provide the actual `.bin` image to the Python CLI, rather than its accompanying `.cue` file. For CHD inputs, the `--virtual-disc` output path is not implemented.

## Quick start

### 1. Download and place the toolkit

Clone the repository, or choose **Code → Download ZIP** on GitHub:

```bash
git clone https://github.com/savageforengland-hue/parasite-eve-layeredfs.git
```

Copy the toolkit files into the **root of your existing Parasite Eve PC installation/project**, keeping their relative paths intact. For the commands below, run your terminal from that root directory. Back up any existing mod configuration before merging folders.

### 2. Index an original disc

Place an original disc image somewhere accessible. You can use the included `install_layeredfs.bat` for an initial Disc 1 setup when an image is in the root folder, or run the Python CLI explicitly:

```bash
python tools/pe_layeredfs_tool.py init-tree --bin "Disc1.bin" --root . --disc 1
```

This generates `mods/layeredfs/manifest_disc1.json` and mirrors the expected asset structure under `mods/layeredfs/romfs/DISC1/`. The manifest remembers the source image path; keep the original image available for later synchronization.

For Disc 2, run `init-tree` with your Disc 2 image and `--disc 2`. The script also attempts to identify the disc and region from the image.

To extract original assets into the mirrored folders as well as building the structure, add `--extract-all`. **That option copies original game content**, which can consume significant disk space; do not commit extracted copyrighted game assets to this repository.

### 3. Add your modded assets

Put replacement files into the matching locations under `mods/layeredfs/romfs/`. For example, an indexed `PE.IMG` sub-asset may belong at a path shaped like:

```text
mods/layeredfs/romfs/
└── DISC1/
    └── PE_IMG/
        └── pkg_XXXX/
            └── type_09_textures/
                └── asset_ZZZZ.bin
```

`XXXX` and `ZZZZ` are placeholders. **Use the paths generated for your actual disc** instead of assuming these example identifiers are present. The `_DROP_MOD_ASSETS_HERE.txt` files only keep the empty staging directories visible in Git.

You can also stage files in these folders:

| Folder inside `mods/layeredfs/romfs/` | Synced destination |
| --- | --- |
| `SKINS/` | `pe_skins/` under the resolved userdata directory |
| `PACKS/` | `packs/` under userdata |
| `FONTS/` | `mods/fonts/` in the game root |
| `CALLS/` | `pe_calls/` under userdata |
| `LANG/` | `lang/` in the game root |
| `HD_BACKGROUNDS/` | `backgrounds/` under userdata |

The directory tree also includes `TIM_OVERRIDES/` as a staging folder; it is **not** listed among the Python tool's automatic native-folder copy mappings.

### 4. Build the override cache

After changing mod files, run:

```bash
python tools/pe_layeredfs_tool.py sync --root . --disc 1
```

Or run `sync_layeredfs_mods.bat` on Windows. **Important:** that batch script also passes `--virtual-disc`, so it may create a large patched disc image. The plain Python command above only builds the cache and synchronizes native asset folders.

For Disc 2, use `--disc 2` after indexing that disc. The normal sync process produces `mods/layeredfs/override_cache.bin` and may copy that cache to `userdata/layeredfs/` when portable mode is active.

### 5. Optional: generate a virtual disc

If you specifically want a patched `.bin/.cue` output and have a non-CHD source:

```bash
python tools/pe_layeredfs_tool.py sync --root . --disc 1 --virtual-disc
```

The default output basename is `Parasite_Eve_LayeredFS_Disc1`. Ensure you have sufficient free space for a full copy of the source image. This output path has not been validated across all disc formats and is **not supported for CHD input**.

## Directory layout

```text
parasite-eve-layeredfs/
├── README.md                     # This guide
├── README_LAYEREDFS.md           # Original version-specific feature notes
├── install_layeredfs.bat          # Windows initial setup
├── extract_disc_structure.bat     # Disc indexing shortcut
├── sync_layeredfs_mods.bat        # Sync shortcut (also requests virtual disc)
├── tools/
│   └── pe_layeredfs_tool.py       # Python CLI
└── mods/
    ├── pe_layeredfs/
    │   ├── CMakeLists.txt         # Native integration fragment
    │   ├── pe_layeredfs.c
    │   └── pe_layeredfs.h
    └── layeredfs/
        ├── layeredfs.ini          # Default LayeredFS configuration
        └── romfs/
            ├── DISC1/            # Disc 1 package override staging
            ├── DISC2/            # Disc 2 package override staging
            ├── TIM_OVERRIDES/
            ├── SKINS/
            ├── PACKS/
            ├── FONTS/
            ├── CALLS/
            ├── LANG/
            └── HD_BACKGROUNDS/
```

Generated manifests, caches, patched disc images and extracted game assets are **not** part of the included source tree.

## Native C module and configuration

The `mods/pe_layeredfs/` folder contains a C implementation with path resolution, fallback reads, cached sector overrides and a service API. Its `CMakeLists.txt` adds the source to an existing target named `parasite-eve-pc` and defines `PE_LAYEREDFS_NATIVE_MOD=1`.

**The Windows installer and Python CLI do not compile or load this native module.** To use it at runtime, the host recompilation must actually include the CMake fragment, build the sources, and connect the relevant host read/mod hooks. Review the upstream [mod documentation](https://github.com/khasinski/parasite-eve-pc/blob/main/mods/README.md) before modifying its build.

The supplied `mods/layeredfs/layeredfs.ini` has these default settings:

```ini
enabled = 1
profile = default
region = USA
log_reads = 1
```

The native source also contains resolution logic for `PE_CONFIG_HOME`, portable `userdata/` folders and per-profile overrides. Those paths take effect only when the native module is correctly integrated. Users with Japanese disc images should review the default `region` configuration.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `Manifest not found` | Run `init-tree` for the correct disc first. |
| File not found during sync | Make sure the source image still exists at the path recorded in `manifest_disc1.json` or `manifest_disc2.json`. |
| No disc overrides reported | Confirm that your edited file names and paths match the indexed disc, and that the replacements differ from the original contents. |
| Python not recognized | Install Python 3 and ensure `python` is on your PATH. |
| Native changes do not appear in game | A generated cache alone does not prove the C module is built or connected to the host game's read hooks. |
| CHD or virtual-disc issues | Try a known-good raw `.bin` source for debugging; the Python CHD reader is experimental and virtual-disc generation skips CHD. |

## Limitations and status

- **Experimental, not independently tested in-game.** Do not assume that every supported asset category, disc format or upstream revision works.
- The Python disc reader includes a CHD v5 implementation, but compressed CHD variants may require additional work.
- A patched virtual disc is a separate, potentially large output file; it is not a replacement for native integration.
- The initial manifest and generated cache are **disc-specific**. Build the appropriate data for each disc and region.
- Git-tracked placeholder directories are not actual game assets.
- Upstream APIs may change. This project targets the v0.12-alpha-era layout and needs validation against the exact version you build.

## Credits and legal

This is a community project, **not an official Square Enix release** and not part of the upstream Parasite Eve PC recompilation. See [khasinski/parasite-eve-pc](https://github.com/khasinski/parasite-eve-pc) for the host project and [khasinski/parasite-eve-decomp](https://github.com/khasinski/parasite-eve-decomp) for related reverse-engineering work.

**Parasite Eve and its original assets belong to their respective rights holders.** This repository is intended for modifications using game data you already own and does not distribute the original game.
