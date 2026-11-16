/*
 * pe_layeredfs.h — Layered Filesystem (LayeredFS) for Parasite Eve PC Port (v0.12-alpha / main)
 * Target: khasinski/parasite-eve-pc v0.11 & v0.12-alpha+ (PE_MOD_API_VERSION = 1 & PE_ENHANCEMENTS_VERSION = 0.10.0)
 *
 * Supports all v0.12-alpha / main features:
 *   1. CUE/BIN (2352-byte Mode 2), ISO (2048-byte), and CHD v5 (.chd) disc images.
 *   2. North American (SLUS-006.62 / SLUS-006.68) and Japanese (SLPS-012.30 / SLPS-012.31) releases.
 *   3. Portable mode (`portable.txt` -> `userdata/`), `PE_CONFIG_HOME`, and `recomplauncher.json`.
 *   4. Native bridges for v0.12-alpha asset subsystems:
 *      - Disc / PE.IMG 12-category sub-asset splicing (`DISC1/`, `DISC2/`)
 *      - Wardrobe & Character Packs (`SKINS/` -> `pe_skins/`, `PACKS/` -> `packs/`)
 *      - Dialogue Fonts (`FONTS/<name>.png` -> `mods/fonts/` via `PE_HOOK_TIM_UPLOAD`)
 *      - Phone Calls (`CALLS/<name>.txt` -> `pe_calls/` for `pe_phone`)
 *      - Language Packs (`LANG/<name>.pelang` -> `lang/` for `pe_lang`)
 *      - HD Background Layers (`HD_BACKGROUNDS/` -> `userdata/backgrounds/`)
 */

#ifndef PE_LAYEREDFS_H
#define PE_LAYEREDFS_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PE_LFS_VERSION             "1.2.0"
#define PE_LFS_TARGET_RECOMP_VER   "0.12-alpha"
#define PE_LFS_SERVICE_NAME        "layeredfs"
#define PE_LFS_SERVICE_VERSION     1

#define PE_LFS_SECTOR_USER_SIZE    2048
#define PE_LFS_SECTOR_RAW_SIZE     2352
#define PE_LFS_SECTOR_SYNC_HDR     24

#define PE_LFS_MAX_OVERRIDES       4096
#define PE_LFS_MAX_PATH            512
#define PE_LFS_MAX_PROFILES        8

/* Disc region identifiers supported by parasite-eve-pc 0.12-alpha */
typedef enum PeLfsDiscRegion {
    PE_LFS_REGION_UNKNOWN = 0,
    PE_LFS_REGION_USA     = 1, /* SLUS_006.62 (Disc 1), SLUS_006.68 (Disc 2) */
    PE_LFS_REGION_JPN     = 2  /* SLPS_012.30 (Disc 1), SLPS_012.31 (Disc 2) */
} PeLfsDiscRegion;

/* Asset categories inside each PE.IMG package (ZenHAX / decomp conventions) */
typedef enum PeLfsAssetType {
    PE_LFS_ASSET_MEMORY_DAT    = 0,  /* Root memory.dat / header metadata */
    PE_LFS_ASSET_SCRIPTS       = 1,  /* Type 1: FieldFx / event scripts (.fxs) */
    PE_LFS_ASSET_MODELS        = 2,  /* Type 2: 3D character/enemy geometry */
    PE_LFS_ASSET_ANIMATIONS    = 3,  /* Type 3: Skeletal animation rows */
    PE_LFS_ASSET_SOUND_AKAO    = 4,  /* Type 4: AKAO audio sequences / instr */
    PE_LFS_ASSET_COLLISION     = 5,  /* Type 5: Walkmesh / collision data */
    PE_LFS_ASSET_BACKGROUNDS   = 6,  /* Type 6: 2D background tile layers */
    PE_LFS_ASSET_CAMERA_LIGHT  = 7,  /* Type 7: Camera & room lighting setup */
    PE_LFS_ASSET_EFFECTS       = 8,  /* Type 8: Particle / spell VFX sprites */
    PE_LFS_ASSET_TEXTURES_PAL  = 9,  /* Type 9: 4bpp/8bpp TIM textures & CLUTs */
    PE_LFS_ASSET_ROOM_OVERLAY  = 10, /* Type 10: Room executable overlay (0x8018EFE8) */
    PE_LFS_ASSET_BATTLE_DATA   = 11, /* Type 11: Encounter & monster tables */
    PE_LFS_ASSET_OTHER         = 12, /* Type 12: Misc package blobs */
    PE_LFS_ASSET_TYPE_COUNT    = 13
} PeLfsAssetType;

/* Binary header for prebuilt sector override cache (override_cache.bin) */
#define PE_LFS_CACHE_MAGIC 0x53464C50u /* "PLFS" */
#define PE_LFS_CACHE_VER   2u          /* v2 adds region_id for 0.12-alpha USA/JPN check */

#pragma pack(push, 1)
typedef struct PeLfsCacheHeader {
    uint32_t magic;          /* PE_LFS_CACHE_MAGIC ("PLFS") */
    uint32_t version;        /* PE_LFS_CACHE_VER (2) */
    uint32_t disc_number;    /* 1 or 2 */
    uint32_t region_id;      /* PeLfsDiscRegion (1=USA, 2=JPN) */
    uint32_t entry_count;    /* Number of LBA range overrides */
    uint32_t reserved;       /* Alignment padding */
    uint64_t total_blob_sz;  /* Total byte size of replacement payload pool */
} PeLfsCacheHeader;

typedef struct PeLfsCacheEntry {
    uint32_t start_lba;      /* Starting 2048-byte sector LBA on disc */
    uint32_t sector_count;   /* Number of 2048-byte sectors covered */
    uint32_t pkg_id;         /* PE.IMG package index (0xFFFFFFFF if ISO file) */
    uint32_t flags;          /* Bit 0: sub-asset merged; Bit 1: full file */
    uint64_t data_offset;    /* Offset inside override_cache.bin payload pool */
    uint64_t byte_length;    /* Exact byte length of replacement data */
    char     virtual_path[128]; /* Relative path in romfs/ for logging */
} PeLfsCacheEntry;
#pragma pack(pop)

/* Public service API published via pe_service_publish("layeredfs", 1, ...) */
typedef struct PeLayeredFsApi {
    /* Resolve a virtual disc path (e.g., "DISC1/PE_IMG/pkg_0012/type_02_models/asset_0000.bin").
     * Checks PE_CONFIG_HOME, 0.12 portable `userdata/`, active profile, and `mods/layeredfs/romfs/`.
     * Returns true and writes the full host path if an override exists,
     * or returns false if the caller should use the original disc asset. */
    bool (*resolve_path)(const char *virtual_path, char *out_host_path, size_t out_sz);

    /* Read a file from the LayeredFS mod folder if overridden; otherwise invokes
     * `fallback_disc_read` (if provided) to read from the original disc. */
    const uint8_t *(*read_asset)(
        const char *virtual_path,
        size_t *out_size,
        const uint8_t *(*fallback_disc_read)(const char *vpath, size_t *sz, void *ud),
        void *user_data
    );

    /* Intercept a sector read at (disc_num, start_lba, sector_count).
     * `sector_buf` must already contain the original disc's 2048-byte user sectors
     * (the fallback layer). Any sector overlapped by a mod file in `romfs/` is
     * overwritten in-place. Returns the number of modded sectors applied. */
    uint32_t (*apply_sector_overrides)(
        uint32_t disc_num,
        uint32_t start_lba,
        uint32_t sector_count,
        uint8_t *sector_buf_2048
    );

    /* Convert a 2048-byte user sector into a 2352-byte Mode 2 Form 1 raw CD sector
     * preserving or synthesizing the 24-byte sync/header/subheader and 280-byte trailer. */
    void (*wrap_mode2_form1_sector)(
        uint32_t lba,
        const uint8_t *user_data_2048,
        uint8_t *raw_sector_2352
    );

    /* Hot-reload `romfs/` and `override_cache.bin` at runtime. */
    uint32_t (*reload_overrides)(void);

    /* Query statistics & 0.12 portable state */
    uint32_t (*get_override_count)(void);
    uint64_t (*get_intercepted_reads)(void);
    bool     (*is_portable_mode)(void);
    PeLfsDiscRegion (*get_disc_region)(void);
} PeLayeredFsApi;

/* Standalone C entry points for testing and direct host integration */
bool     pe_lfs_init(const char *root_dir);
void     pe_lfs_shutdown(void);
uint32_t pe_lfs_reload(void);
const PeLayeredFsApi *pe_lfs_get_api(void);

/* Reconstructs a PE.IMG package in memory by taking the original package bytes
 * from the base disc and splicing in any replacement sub-assets found in
 * `<romfs>/DISC<N>/PE_IMG/pkg_<XXXX>/type_<YY>_<category>/asset_<ZZZZ>.bin`.
 * If no sub-assets are modded, returns false and uses the original package untouched. */
bool pe_lfs_patch_package_in_memory(
    const uint8_t *orig_pkg_data,
    size_t orig_pkg_size,
    const char *pkg_romfs_dir,
    uint8_t **out_patched_data,
    size_t *out_patched_size,
    uint32_t *out_replaced_assets
);

#ifdef __cplusplus
}
#endif

#endif /* PE_LAYEREDFS_H */
