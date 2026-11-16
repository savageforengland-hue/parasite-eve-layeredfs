/*
 * pe_layeredfs.c — Layered Filesystem (LayeredFS) Implementation for Parasite Eve PC (v0.12-alpha+)
 * Target: khasinski/parasite-eve-pc v0.11 & v0.12-alpha+ (PE_MOD_API_VERSION = 1)
 *
 * Layered Resolution Order (highest priority first):
 *   Layer 3 (Config):   `$PE_CONFIG_HOME/layeredfs/romfs/` (if PE_CONFIG_HOME env is set in 0.12)
 *   Layer 2 (Portable): `<root>/userdata/layeredfs/romfs/` (when `portable.txt` or `userdata/` is present)
 *   Layer 1 (Profile):  `<root>/mods/layeredfs/profiles/<active>/romfs/`
 *   Layer 1 (Default):  `<root>/mods/layeredfs/romfs/`
 *   Layer 0 (Fallback): Original unmodified Parasite Eve CUE/BIN or CHD disc image.
 */

#include "pe_layeredfs.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#if defined(_WIN32)
#include <windows.h>
#include <direct.h>
#define PE_PATH_SEP '\\'
#else
#include <unistd.h>
#define PE_PATH_SEP '/'
#endif

#define PE_LFS_BUF_PATH (PE_LFS_MAX_PATH * 4)

/* ==========================================================================
 * Internal State
 * ========================================================================== */

typedef struct PeLfsRuntimeOverride {
    uint32_t        disc_num;
    PeLfsDiscRegion region_id;
    uint32_t        start_lba;
    uint32_t        sector_count;
    uint32_t        pkg_id;
    uint32_t        flags;
    uint8_t        *payload;
    size_t          payload_size;
    char            virtual_path[128];
} PeLfsRuntimeOverride;

static struct {
    bool                  initialized;
    bool                  enabled;
    bool                  log_reads;
    bool                  portable_mode;
    PeLfsDiscRegion       disc_region;
    char                  root_dir[PE_LFS_MAX_PATH];
    char                  userdata_dir[PE_LFS_MAX_PATH * 2];
    char                  config_home_dir[PE_LFS_MAX_PATH * 2];
    char                  romfs_dir[PE_LFS_MAX_PATH * 2];
    char                  active_profile[128];
    PeLfsRuntimeOverride  overrides[PE_LFS_MAX_OVERRIDES];
    uint32_t              override_count;
    uint64_t              intercepted_sector_reads;
    uint64_t              fallback_sector_reads;
    uint8_t              *last_asset_buf;
    size_t                last_asset_cap;
    FILE                 *log_fp;
} s_lfs;

static const char *const kAssetTypeFolders[PE_LFS_ASSET_TYPE_COUNT] = {
    "type_00_root",
    "type_01_scripts",
    "type_02_models",
    "type_03_animations",
    "type_04_sound_akao",
    "type_05_collision",
    "type_06_backgrounds",
    "type_07_camera_light",
    "type_08_effects",
    "type_09_textures",
    "type_10_room_overlay",
    "type_11_battle_data",
    "type_12_other"
};

/* ==========================================================================
 * File & Path Utilities
 * ========================================================================== */

static bool lfs_file_exists(const char *path, size_t *out_size) {
    if (!path || !path[0]) return false;
    struct stat st;
    if (stat(path, &st) != 0) return false;
#if defined(S_ISREG)
    if (!S_ISREG(st.st_mode)) return false;
#endif
    if (out_size) *out_size = (size_t)st.st_size;
    return true;
}

static bool lfs_dir_exists(const char *path) {
    if (!path || !path[0]) return false;
    struct stat st;
    if (stat(path, &st) != 0) return false;
#if defined(S_ISDIR)
    return S_ISDIR(st.st_mode);
#else
    return true;
#endif
}

static uint8_t *lfs_read_entire_file(const char *path, size_t *out_size) {
    FILE *fp = fopen(path, "rb");
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return NULL;
    }
    long sz = ftell(fp);
    if (sz < 0) {
        fclose(fp);
        return NULL;
    }
    rewind(fp);
    uint8_t *buf = (uint8_t *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(fp);
        return NULL;
    }
    size_t n = fread(buf, 1, (size_t)sz, fp);
    fclose(fp);
    buf[n] = 0;
    if (out_size) *out_size = n;
    return buf;
}

static void lfs_normalize_vpath(const char *in, char *out, size_t out_sz) {
    if (!in || !out || out_sz == 0) return;
    while (*in == '/' || *in == '\\') in++;
    size_t j = 0;
    for (size_t i = 0; in[i] && j + 1 < out_sz; i++) {
        char c = in[i];
        if (c == '\\') c = '/';
        if (c == '.' && in[i + 1] == '.') continue;
        out[j++] = c;
    }
    out[j] = '\0';
}

static void lfs_log(const char *fmt, ...) {
    if (!s_lfs.log_fp) return;
    va_list args;
    va_start(args, fmt);
    vfprintf(s_lfs.log_fp, fmt, args);
    fprintf(s_lfs.log_fp, "\n");
    fflush(s_lfs.log_fp);
    va_end(args);
}

/* ==========================================================================
 * CD-ROM Mode 2 Form 1 Sector Wrapping (2048 -> 2352 bytes)
 * ========================================================================== */

static uint8_t lfs_to_bcd(uint32_t val) {
    return (uint8_t)(((val / 10u) << 4) | (val % 10u));
}

static uint32_t lfs_compute_edc(const uint8_t *data, size_t len) {
    static uint32_t edc_lut[256];
    static bool lut_init = false;
    if (!lut_init) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t crc = i;
            for (int b = 0; b < 8; b++) {
                crc = (crc >> 1) ^ ((crc & 1) ? 0xD8018001u : 0u);
            }
            edc_lut[i] = crc;
        }
        lut_init = true;
    }
    uint32_t edc = 0;
    for (size_t i = 0; i < len; i++) {
        edc = (edc >> 8) ^ edc_lut[(edc ^ data[i]) & 0xFFu];
    }
    return edc;
}

static void lfs_wrap_mode2_form1_sector(
    uint32_t lba,
    const uint8_t *user_data_2048,
    uint8_t *raw_sector_2352
) {
    if (!user_data_2048 || !raw_sector_2352) return;

    raw_sector_2352[0] = 0x00;
    memset(raw_sector_2352 + 1, 0xFF, 10);
    raw_sector_2352[11] = 0x00;

    uint32_t total_frames = lba + 150u;
    uint32_t ff = total_frames % 75u;
    uint32_t ss = (total_frames / 75u) % 60u;
    uint32_t mm = total_frames / (75u * 60u);

    raw_sector_2352[12] = lfs_to_bcd(mm);
    raw_sector_2352[13] = lfs_to_bcd(ss);
    raw_sector_2352[14] = lfs_to_bcd(ff);
    raw_sector_2352[15] = 0x02;

    raw_sector_2352[16] = 0x00;
    raw_sector_2352[17] = 0x00;
    raw_sector_2352[18] = 0x08;
    raw_sector_2352[19] = 0x00;
    raw_sector_2352[20] = 0x00;
    raw_sector_2352[21] = 0x00;
    raw_sector_2352[22] = 0x08;
    raw_sector_2352[23] = 0x00;

    memcpy(raw_sector_2352 + 24, user_data_2048, PE_LFS_SECTOR_USER_SIZE);

    uint32_t edc = lfs_compute_edc(raw_sector_2352 + 16, 8 + PE_LFS_SECTOR_USER_SIZE);
    raw_sector_2352[2072] = (uint8_t)(edc & 0xFFu);
    raw_sector_2352[2073] = (uint8_t)((edc >> 8) & 0xFFu);
    raw_sector_2352[2074] = (uint8_t)((edc >> 16) & 0xFFu);
    raw_sector_2352[2075] = (uint8_t)((edc >> 24) & 0xFFu);

    memset(raw_sector_2352 + 2076, 0, 276);
}

/* ==========================================================================
 * Layered Path Resolution & Asset Reading (v0.12-alpha Multi-Root Aware)
 * ========================================================================== */

static bool lfs_resolve_path(const char *virtual_path, char *out_host_path, size_t out_sz) {
    if (!s_lfs.initialized || !s_lfs.enabled || !virtual_path || !out_host_path) {
        return false;
    }

    char norm[PE_LFS_MAX_PATH];
    lfs_normalize_vpath(virtual_path, norm, sizeof(norm));
    if (!norm[0]) return false;

    char candidate[PE_LFS_BUF_PATH];

    /* Layer 3: PE_CONFIG_HOME override (highest precedence in 0.12-alpha) */
    if (s_lfs.config_home_dir[0]) {
        snprintf(candidate, sizeof(candidate), "%s/layeredfs/romfs/%s", s_lfs.config_home_dir, norm);
        if (lfs_file_exists(candidate, NULL)) {
            snprintf(out_host_path, out_sz, "%s", candidate);
            if (s_lfs.log_reads) lfs_log("[LayeredFS] HIT (PE_CONFIG_HOME) %s -> %s", norm, candidate);
            return true;
        }
    }

    /* Layer 2: 0.12-alpha Portable `userdata/` folder (`portable.txt` or `--portable`) */
    if (s_lfs.portable_mode && s_lfs.userdata_dir[0]) {
        snprintf(candidate, sizeof(candidate), "%s/layeredfs/romfs/%s", s_lfs.userdata_dir, norm);
        if (lfs_file_exists(candidate, NULL)) {
            snprintf(out_host_path, out_sz, "%s", candidate);
            if (s_lfs.log_reads) lfs_log("[LayeredFS] HIT (userdata) %s -> %s", norm, candidate);
            return true;
        }
    }

    /* Layer 1b: Active profile romfs */
    if (s_lfs.active_profile[0] && strcmp(s_lfs.active_profile, "default") != 0) {
        snprintf(candidate, sizeof(candidate), "%s/mods/layeredfs/profiles/%s/romfs/%s",
                 s_lfs.root_dir, s_lfs.active_profile, norm);
        if (lfs_file_exists(candidate, NULL)) {
            snprintf(out_host_path, out_sz, "%s", candidate);
            if (s_lfs.log_reads) lfs_log("[LayeredFS] HIT (profile:%s) %s -> %s", s_lfs.active_profile, norm, candidate);
            return true;
        }
    }

    /* Layer 1a: Default `mods/layeredfs/romfs/` */
    snprintf(candidate, sizeof(candidate), "%s/%s", s_lfs.romfs_dir, norm);
    if (lfs_file_exists(candidate, NULL)) {
        snprintf(out_host_path, out_sz, "%s", candidate);
        if (s_lfs.log_reads) lfs_log("[LayeredFS] HIT (romfs) %s -> %s", norm, candidate);
        return true;
    }

    if (s_lfs.log_reads) {
        lfs_log("[LayeredFS] FALLBACK (original disc) %s", norm);
    }
    return false;
}

static const uint8_t *lfs_read_asset(
    const char *virtual_path,
    size_t *out_size,
    const uint8_t *(*fallback_disc_read)(const char *vpath, size_t *sz, void *ud),
    void *user_data
) {
    if (out_size) *out_size = 0;

    char host_path[PE_LFS_BUF_PATH];
    if (lfs_resolve_path(virtual_path, host_path, sizeof(host_path))) {
        size_t sz = 0;
        uint8_t *data = lfs_read_entire_file(host_path, &sz);
        if (data) {
            free(s_lfs.last_asset_buf);
            s_lfs.last_asset_buf = data;
            s_lfs.last_asset_cap = sz;
            if (out_size) *out_size = sz;
            return s_lfs.last_asset_buf;
        }
    }

    /* Not in mod folder -> fall back to original game disc */
    if (fallback_disc_read) {
        return fallback_disc_read(virtual_path, out_size, user_data);
    }
    return NULL;
}

/* ==========================================================================
 * PE.IMG Sub-Asset Package Splicer
 * ========================================================================== */

bool pe_lfs_patch_package_in_memory(
    const uint8_t *orig_pkg_data,
    size_t orig_pkg_size,
    const char *pkg_romfs_dir,
    uint8_t **out_patched_data,
    size_t *out_patched_size,
    uint32_t *out_replaced_assets
) {
    if (out_patched_data) *out_patched_data = NULL;
    if (out_patched_size) *out_patched_size = 0;
    if (out_replaced_assets) *out_replaced_assets = 0;

    if (!orig_pkg_data || orig_pkg_size < 16 || !pkg_romfs_dir) {
        return false;
    }

    uint32_t magic_or_count = 0;
    memcpy(&magic_or_count, orig_pkg_data, 4);

    bool has_pepk_magic = (magic_or_count == 0x4B504550u); /* "PEPK" */
    size_t table_off = has_pepk_magic ? 8 : 4;
    uint32_t entry_count = 0;
    if (has_pepk_magic) {
        memcpy(&entry_count, orig_pkg_data + 4, 4);
    } else {
        entry_count = magic_or_count;
    }

    if (entry_count == 0 || entry_count > 1024 || table_off + (size_t)entry_count * 16 > orig_pkg_size) {
        return false;
    }

    typedef struct {
        uint32_t asset_type;
        uint32_t sub_index;
        uint32_t offset;
        uint32_t size;
    } PkgAssetDesc;

    PkgAssetDesc *descs = (PkgAssetDesc *)malloc(sizeof(PkgAssetDesc) * entry_count);
    uint8_t **chunks = (uint8_t **)calloc(entry_count, sizeof(uint8_t *));
    bool *chunk_owned = (bool *)calloc(entry_count, sizeof(bool));
    if (!descs || !chunks || !chunk_owned) {
        free(descs);
        free(chunks);
        free(chunk_owned);
        return false;
    }

    uint32_t replaced_count = 0;
    for (uint32_t i = 0; i < entry_count; i++) {
        memcpy(&descs[i], orig_pkg_data + table_off + i * 16, 16);
        if ((size_t)descs[i].offset + descs[i].size > orig_pkg_size) {
            for (uint32_t k = 0; k < i; k++) if (chunk_owned[k]) free(chunks[k]);
            free(descs);
            free(chunks);
            free(chunk_owned);
            return false;
        }

        uint32_t atype = descs[i].asset_type;
        const char *folder = (atype < PE_LFS_ASSET_TYPE_COUNT)
            ? kAssetTypeFolders[atype]
            : kAssetTypeFolders[PE_LFS_ASSET_OTHER];

        char candidate[PE_LFS_BUF_PATH];
        if (atype == PE_LFS_ASSET_MEMORY_DAT && descs[i].sub_index == 0) {
            snprintf(candidate, sizeof(candidate), "%s/memory.dat", pkg_romfs_dir);
        } else {
            snprintf(candidate, sizeof(candidate), "%s/%s/asset_%04u.bin",
                     pkg_romfs_dir, folder, descs[i].sub_index);
        }

        size_t mod_sz = 0;
        uint8_t *mod_bytes = lfs_read_entire_file(candidate, &mod_sz);
        if (mod_bytes) {
            chunks[i] = mod_bytes;
            chunk_owned[i] = true;
            descs[i].size = (uint32_t)mod_sz;
            replaced_count++;
        } else {
            chunks[i] = (uint8_t *)(orig_pkg_data + descs[i].offset);
            chunk_owned[i] = false;
        }
    }

    if (replaced_count == 0) {
        free(descs);
        free(chunks);
        free(chunk_owned);
        return false;
    }

    size_t cur_off = (table_off + (size_t)entry_count * 16 + 15u) & ~15u;
    for (uint32_t i = 0; i < entry_count; i++) {
        descs[i].offset = (uint32_t)cur_off;
        cur_off = (cur_off + descs[i].size + 15u) & ~15u;
    }
    size_t total_sz = (cur_off + PE_LFS_SECTOR_USER_SIZE - 1u) & ~(PE_LFS_SECTOR_USER_SIZE - 1u);
    if (total_sz < orig_pkg_size) {
        total_sz = orig_pkg_size;
    }

    uint8_t *out_buf = (uint8_t *)calloc(1, total_sz);
    if (!out_buf) {
        for (uint32_t i = 0; i < entry_count; i++) if (chunk_owned[i]) free(chunks[i]);
        free(descs);
        free(chunks);
        free(chunk_owned);
        return false;
    }

    memcpy(out_buf, orig_pkg_data, table_off);
    for (uint32_t i = 0; i < entry_count; i++) {
        memcpy(out_buf + table_off + i * 16, &descs[i], 16);
        memcpy(out_buf + descs[i].offset, chunks[i], descs[i].size);
        if (chunk_owned[i]) free(chunks[i]);
    }

    free(descs);
    free(chunks);
    free(chunk_owned);

    *out_patched_data = out_buf;
    *out_patched_size = total_sz;
    if (out_replaced_assets) *out_replaced_assets = replaced_count;
    return true;
}

/* ==========================================================================
 * Sector-Level Override Cache & Live Interception
 * ========================================================================== */

static void lfs_clear_overrides(void) {
    for (uint32_t i = 0; i < s_lfs.override_count; i++) {
        free(s_lfs.overrides[i].payload);
        s_lfs.overrides[i].payload = NULL;
    }
    s_lfs.override_count = 0;
}

static bool lfs_load_cache_file(const char *cache_path) {
    size_t file_sz = 0;
    uint8_t *raw = lfs_read_entire_file(cache_path, &file_sz);
    if (!raw) return false;

    if (file_sz < sizeof(PeLfsCacheHeader)) {
        free(raw);
        return false;
    }

    PeLfsCacheHeader hdr;
    memcpy(&hdr, raw, sizeof(hdr));
    if (hdr.magic != PE_LFS_CACHE_MAGIC || (hdr.version != PE_LFS_CACHE_VER && hdr.version != 1u)) {
        free(raw);
        return false;
    }

    if (hdr.region_id != PE_LFS_REGION_UNKNOWN) {
        s_lfs.disc_region = (PeLfsDiscRegion)hdr.region_id;
    }

    size_t table_end = sizeof(PeLfsCacheHeader) + (size_t)hdr.entry_count * sizeof(PeLfsCacheEntry);
    if (table_end > file_sz) {
        free(raw);
        return false;
    }

    for (uint32_t i = 0; i < hdr.entry_count && s_lfs.override_count < PE_LFS_MAX_OVERRIDES; i++) {
        PeLfsCacheEntry ent;
        memcpy(&ent, raw + sizeof(PeLfsCacheHeader) + i * sizeof(PeLfsCacheEntry), sizeof(ent));

        size_t blob_pos = table_end + (size_t)ent.data_offset;
        size_t alloc_sz = (size_t)ent.sector_count * PE_LFS_SECTOR_USER_SIZE;
        if (blob_pos + (size_t)ent.byte_length > file_sz || alloc_sz == 0) {
            continue;
        }

        uint8_t *payload = (uint8_t *)calloc(1, alloc_sz);
        if (!payload) continue;
        size_t copy_len = (size_t)ent.byte_length < alloc_sz ? (size_t)ent.byte_length : alloc_sz;
        memcpy(payload, raw + blob_pos, copy_len);

        PeLfsRuntimeOverride *rt = &s_lfs.overrides[s_lfs.override_count++];
        rt->disc_num = hdr.disc_number;
        rt->region_id = (PeLfsDiscRegion)hdr.region_id;
        rt->start_lba = ent.start_lba;
        rt->sector_count = ent.sector_count;
        rt->pkg_id = ent.pkg_id;
        rt->flags = ent.flags;
        rt->payload = payload;
        rt->payload_size = alloc_sz;
        snprintf(rt->virtual_path, sizeof(rt->virtual_path), "%s", ent.virtual_path);
    }

    free(raw);
    return true;
}

static uint32_t lfs_apply_sector_overrides(
    uint32_t disc_num,
    uint32_t start_lba,
    uint32_t sector_count,
    uint8_t *sector_buf_2048
) {
    if (!s_lfs.initialized || !s_lfs.enabled || !sector_buf_2048 || sector_count == 0) {
        return 0;
    }

    uint32_t req_end = start_lba + sector_count;
    uint32_t patched_sectors = 0;

    for (uint32_t i = 0; i < s_lfs.override_count; i++) {
        const PeLfsRuntimeOverride *ov = &s_lfs.overrides[i];
        if (ov->disc_num != 0 && ov->disc_num != disc_num) continue;

        uint32_t ov_start = ov->start_lba;
        uint32_t ov_end = ov->start_lba + ov->sector_count;

        uint32_t overlap_start = (start_lba > ov_start) ? start_lba : ov_start;
        uint32_t overlap_end   = (req_end < ov_end) ? req_end : ov_end;

        if (overlap_start < overlap_end) {
            uint32_t count = overlap_end - overlap_start;
            size_t dst_off = (size_t)(overlap_start - start_lba) * PE_LFS_SECTOR_USER_SIZE;
            size_t src_off = (size_t)(overlap_start - ov_start) * PE_LFS_SECTOR_USER_SIZE;
            memcpy(sector_buf_2048 + dst_off, ov->payload + src_off, (size_t)count * PE_LFS_SECTOR_USER_SIZE);
            patched_sectors += count;
            if (s_lfs.log_reads) {
                lfs_log("[LayeredFS] Sector override Disc %u LBA %u..%u (%u sectors) <- %s",
                        disc_num, overlap_start, overlap_end - 1, count, ov->virtual_path);
            }
        }
    }

    if (patched_sectors > 0) {
        s_lfs.intercepted_sector_reads += patched_sectors;
    } else {
        s_lfs.fallback_sector_reads += sector_count;
    }

    return patched_sectors;
}

static uint32_t lfs_get_override_count(void) {
    return s_lfs.override_count;
}

static uint64_t lfs_get_intercepted_reads(void) {
    return s_lfs.intercepted_sector_reads;
}

static bool lfs_is_portable_mode(void) {
    return s_lfs.portable_mode;
}

static PeLfsDiscRegion lfs_get_disc_region(void) {
    return s_lfs.disc_region;
}

/* ==========================================================================
 * Public API & Lifecycle
 * ========================================================================== */

static const PeLayeredFsApi kLayeredFsApi = {
    .resolve_path            = lfs_resolve_path,
    .read_asset              = lfs_read_asset,
    .apply_sector_overrides  = lfs_apply_sector_overrides,
    .wrap_mode2_form1_sector = lfs_wrap_mode2_form1_sector,
    .reload_overrides        = pe_lfs_reload,
    .get_override_count      = lfs_get_override_count,
    .get_intercepted_reads   = lfs_get_intercepted_reads,
    .is_portable_mode        = lfs_is_portable_mode,
    .get_disc_region         = lfs_get_disc_region
};

const PeLayeredFsApi *pe_lfs_get_api(void) {
    return &kLayeredFsApi;
}

uint32_t pe_lfs_reload(void) {
    if (!s_lfs.initialized) return 0;
    lfs_clear_overrides();

    char cache1[PE_LFS_BUF_PATH];
    char cache2[PE_LFS_BUF_PATH];
    char cache_merged[PE_LFS_BUF_PATH];

    snprintf(cache_merged, sizeof(cache_merged), "%s/mods/layeredfs/override_cache.bin", s_lfs.root_dir);
    snprintf(cache1, sizeof(cache1), "%s/mods/layeredfs/override_cache_disc1.bin", s_lfs.root_dir);
    snprintf(cache2, sizeof(cache2), "%s/mods/layeredfs/override_cache_disc2.bin", s_lfs.root_dir);

    lfs_load_cache_file(cache_merged);
    lfs_load_cache_file(cache1);
    lfs_load_cache_file(cache2);

    if (s_lfs.portable_mode && s_lfs.userdata_dir[0]) {
        char ucache[PE_LFS_BUF_PATH];
        snprintf(ucache, sizeof(ucache), "%s/layeredfs/override_cache.bin", s_lfs.userdata_dir);
        lfs_load_cache_file(ucache);
    }

    if (s_lfs.log_reads) {
        lfs_log("[LayeredFS] Reloaded %u active sector override ranges (portable=%d, region=%d)",
                s_lfs.override_count, (int)s_lfs.portable_mode, (int)s_lfs.disc_region);
    }
    return s_lfs.override_count;
}

bool pe_lfs_init(const char *root_dir) {
    if (s_lfs.initialized) {
        pe_lfs_shutdown();
    }
    memset(&s_lfs, 0, sizeof(s_lfs));
    s_lfs.initialized = true;
    s_lfs.enabled = true;
    s_lfs.log_reads = false;
    s_lfs.disc_region = PE_LFS_REGION_USA;

    snprintf(s_lfs.root_dir, sizeof(s_lfs.root_dir), "%s", (root_dir && root_dir[0]) ? root_dir : ".");
    snprintf(s_lfs.romfs_dir, sizeof(s_lfs.romfs_dir), "%s/mods/layeredfs/romfs", s_lfs.root_dir);
    snprintf(s_lfs.userdata_dir, sizeof(s_lfs.userdata_dir), "%s/userdata", s_lfs.root_dir);
    snprintf(s_lfs.active_profile, sizeof(s_lfs.active_profile), "default");

    /* Check 0.12-alpha PE_CONFIG_HOME env var and portable.txt */
    const char *env_cfg = getenv("PE_CONFIG_HOME");
    if (env_cfg && env_cfg[0]) {
        snprintf(s_lfs.config_home_dir, sizeof(s_lfs.config_home_dir), "%s", env_cfg);
    }

    char portable_file[PE_LFS_BUF_PATH];
    snprintf(portable_file, sizeof(portable_file), "%s/portable.txt", s_lfs.root_dir);
    if (lfs_file_exists(portable_file, NULL) || lfs_dir_exists(s_lfs.userdata_dir)) {
        s_lfs.portable_mode = true;
    }

    /* Parse optional mods/layeredfs/layeredfs.ini */
    char ini_path[PE_LFS_BUF_PATH];
    snprintf(ini_path, sizeof(ini_path), "%s/mods/layeredfs/layeredfs.ini", s_lfs.root_dir);
    FILE *ini = fopen(ini_path, "r");
    if (ini) {
        char line[256];
        while (fgets(line, sizeof(line), ini)) {
            char key[64], val[120];
            if (sscanf(line, " %63[^= \t] = %119[^\r\n]", key, val) == 2) {
                if (strcmp(key, "enabled") == 0) {
                    s_lfs.enabled = (strcmp(val, "1") == 0 || strcmp(val, "true") == 0);
                } else if (strcmp(key, "log_reads") == 0) {
                    s_lfs.log_reads = (strcmp(val, "1") == 0 || strcmp(val, "true") == 0);
                } else if (strcmp(key, "profile") == 0) {
                    snprintf(s_lfs.active_profile, sizeof(s_lfs.active_profile), "%s", val);
                } else if (strcmp(key, "region") == 0) {
                    if (strcmp(val, "JPN") == 0 || strcmp(val, "SLPS") == 0) {
                        s_lfs.disc_region = PE_LFS_REGION_JPN;
                    } else {
                        s_lfs.disc_region = PE_LFS_REGION_USA;
                    }
                }
            }
        }
        fclose(ini);
    }

    if (s_lfs.log_reads) {
        char log_path[PE_LFS_BUF_PATH];
        snprintf(log_path, sizeof(log_path), "%s/pe_layeredfs.log", s_lfs.root_dir);
        s_lfs.log_fp = fopen(log_path, "a");
    }

    pe_lfs_reload();
    return true;
}

void pe_lfs_shutdown(void) {
    if (!s_lfs.initialized) return;
    lfs_clear_overrides();
    free(s_lfs.last_asset_buf);
    s_lfs.last_asset_buf = NULL;
    if (s_lfs.log_fp) {
        fclose(s_lfs.log_fp);
        s_lfs.log_fp = NULL;
    }
    s_lfs.initialized = false;
}

/* ==========================================================================
 * Native parasite-eve-pc v0.12-alpha Mod Host Integration (-DPE_MODS=ON)
 * ========================================================================== */
#if defined(PE_MODS) && defined(PE_LAYEREDFS_NATIVE_MOD)
#include "pe_hooks.h"
#include "../host/pe_mod_host.h"
#include "../host/pe_mod_menu.h"

#define MOD_ID "pe_layeredfs"

static bool s_ui_enabled = true;
static bool s_ui_log_reads = false;

static void on_reload_pressed(void) {
    uint32_t cnt = pe_lfs_reload();
    pe_toast("LayeredFS v0.12 reloaded (%u overrides)", cnt);
}

static void on_frame_drawn(void *ctx, void *user) {
    (void)ctx;
    (void)user;
    s_lfs.enabled = s_ui_enabled;
    s_lfs.log_reads = s_ui_log_reads;
}

static bool mod_init(void) {
    pe_lfs_init(".");
    pe_service_publish(PE_LFS_SERVICE_NAME, PE_LFS_SERVICE_VERSION, &kLayeredFsApi, MOD_ID);

    pe_menu_top_page("LayeredFS", "Disc & v0.12 asset override system (mods/layeredfs/romfs)", 45);
    pe_menu_begin("LayeredFS");
    pe_menu_toggle("Enable LayeredFS", "Override disc, skin, font, and call assets from romfs/", &s_ui_enabled, true);
    pe_menu_toggle("Log asset reads", "Write accessed virtual paths to pe_layeredfs.log", &s_ui_log_reads, false);
    pe_menu_action("Reload overrides now", "Rescan romfs/ and override_cache.bin in-place", on_reload_pressed, false);
    pe_menu_end();

    pe_hook_add(PE_HOOK_FRAME_DRAWN, on_frame_drawn, NULL, 0, MOD_ID);
    return true;
}

static void mod_shutdown(void) {
    pe_lfs_shutdown();
}

const PeMod pe_mod_pe_layeredfs = {
    MOD_ID,
    "LayeredFS Asset Overrides (0.12)",
    PE_LFS_VERSION,
    NULL,
    mod_init,
    mod_shutdown
};
#endif /* PE_MODS && PE_LAYEREDFS_NATIVE_MOD */
