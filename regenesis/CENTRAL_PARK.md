# Central Park infection prototype

Target: first Central Park scene whose real background override filename can be verified against a user-owned installation.

## Current status

- Offline room infection-state engine: implemented.
- Background staging CLI: implemented, not yet executed against real game assets.
- Actual Central Park room identifier: **not yet identified**.
- Actual native background override filename / layer mapping: **not yet verified**.
- In-game hooks and live background switching: **not yet implemented**.

## Artist workflow

1. Export or capture the original room image from your own game installation for alignment reference. Do not commit it.
2. Produce three original PNG/WebP variants with matching camera geometry: exposed, infested, overrun.
3. Verify the filename expected by the installed upstream background system.
4. Preview without modifying the game's override folder:

```sh
python regenesis/stage_background.py --source path/to/your_infected.png --target-name CONFIRMED_NAME.png --stage infested
```

5. Only after confirming the correct native filename, stage it for LayeredFS:

```sh
python regenesis/stage_background.py --source path/to/your_infected.png --target-name CONFIRMED_NAME.png --stage infested --apply
python tools/pe_layeredfs_tool.py sync --root . --disc 1
```

The second command depends on a valid Disc 1 manifest. Staging does not guarantee the upstream runtime loads the image. Never apply multiple infection stages to the same target filename simultaneously; stage switching requires a later native hook.

## Safety

The tool refuses overwrites and rejects path traversal. No original game assets are bundled. Preserve backups and validate with the exact recompilation version before sharing a playable release.
