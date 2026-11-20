# Verified upstream Central Park checkpoint

Source inspected: https://github.com/khasinski/parasite-eve-pc/blob/main/mods/pe_warp/pe_warp.c

Upstream `pe_warp` defines:

```c
{"Day 2: Central Park (M374)", 0xA8067248u, 0xE4u},
```

- Room checkpoint: M374
- Scene dispatch transfer token: `0xA8067248`
- Story variable bank index: 74
- Story value: `0xE4`
- Warp is queued for a safe free-field frame using `Script_EncodeBarcode`.
- Requires a loaded game in a field room. It does not warp from the title screen.

## How to reach Central Park without a Central Park save

1. Use a native build compiled with `-DPE_MODS=ON` and `pe_warp` in `PE_MOD_LIST`.
2. Enable **All mods** and **Warp** in the F1 mod manager, then restart.
3. Load **any working field save**, open **F1 > Warp**, select **Day 2: Central Park (M374)**, and activate Warp.
4. Capture a screenshot with metadata to identify the actual background resource.

**Do not assume the downloadable prebuilt release contains or enables Warp.** It is an optional native mod and must be present in the build.

## Known unknowns

- The user's supplied snowy path screenshot has **not** been proven to be room M374. The checkpoint may lead to a different Central Park view.
- Background ID, layer names, resolution and mapping remain unverified.
- No in-game screenshot or runtime test has been performed.
- Do not hard-code M374 as the replacement asset filename.

Next: identify the actual room/background key using screenshot metadata or source-level asset mappings; only then apply a test replacement.
