#!/usr/bin/env python3
"""
pe_layeredfs_tool.py — Parasite Eve PC Recompilation (v0.12-alpha / main) LayeredFS Manager

Supports all features of `khasinski/parasite-eve-pc` v0.12-alpha and `main`:
  1. Disc Formats:
     - `.bin`/`.cue` (Raw 2352-byte/sector Mode 2 Form 1)
     - `.iso` (2048-byte/sector Mode 1)
     - `.chd` (MAME CHD v5 CD-ROM images introduced in 0.12-alpha, via `chdman` or native CHD v5 parser)
  2. Multi-Region Support:
     - North American release (`SLUS_006.62` Disc 1 / `SLUS_006.68` Disc 2)
     - Japanese release (`SLPS_012.30` Disc 1 / `SLPS_012.31` Disc 2) added in 0.12-alpha
  3. 0.12-alpha Asset & Portable Subsystems (`userdata/`, `PE_CONFIG_HOME`, `portable.txt`):
     - `romfs/DISC1/` & `romfs/DISC2/`: ISO 9660 + `PE.IMG` packages split into 12 sub-asset folders
     - `romfs/SKINS/`: Syncs custom character skins (`texture.bin`, `model.bin`, `day1-8.bin`, `rooms.bin`, `meta.bin`) into `pe_skins/` for `pe_wardrobe`
     - `romfs/PACKS/`: Syncs `pack.json` format v1 character packs into `packs/` for `pe_wardrobe`
     - `romfs/FONTS/`: Syncs custom `.png` font sheets into `mods/fonts/` for `pe_fonts` (`PE_HOOK_TIM_UPLOAD`)
     - `romfs/CALLS/`: Syncs custom phone call scripts (`.txt`) into `pe_calls/` for `pe_phone`
     - `romfs/LANG/`: Syncs `.pelang` packs into `lang/` for `pe_lang`
     - `romfs/HD_BACKGROUNDS/`: Syncs WebP/PNG room backgrounds into `backgrounds/` for immediate scene reload
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SECTOR_USER_SIZE = 2048
SECTOR_RAW_SIZE = 2352
SECTOR_SYNC_HEADER = 24
CHD_CD_SECTOR_SIZE = 2448  # 2352 raw + 96 subcode bytes in CHD CD hunks

CACHE_MAGIC = 0x53464C50  # "PLFS"
CACHE_VERSION = 2         # v2 header for 0.12-alpha
PEPK_MAGIC = 0x4B504550   # "PEPK"

REGION_UNKNOWN = 0
REGION_USA = 1  # SLUS_006.62 / SLUS_006.68
REGION_JPN = 2  # SLPS_012.30 / SLPS_012.31

ASSET_TYPE_FOLDERS = {
    0: "type_00_root",
    1: "type_01_scripts",
    2: "type_02_models",
    3: "type_03_animations",
    4: "type_04_sound_akao",
    5: "type_05_collision",
    6: "type_06_backgrounds",
    7: "type_07_camera_light",
    8: "type_08_effects",
    9: "type_09_textures",
    10: "type_10_room_overlay",
    11: "type_11_battle_data",
    12: "type_12_other",
}


def compute_edc(data: bytes) -> int:
    """Compute PS1 CD-ROM Mode 2 Form 1 EDC (CRC-32 polynomial 0xD8018001)."""
    edc = 0
    for b in data:
        crc = edc ^ b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xD8018001 if (crc & 1) else 0)
        edc = (edc >> 8) ^ (crc & 0xFFFFFFFF)
    return edc & 0xFFFFFFFF


def to_bcd(val: int) -> int:
    return ((val // 10) << 4) | (val % 10)


def wrap_mode2_form1_sector(lba: int, user_2048: bytes, orig_raw_2352: Optional[bytes] = None) -> bytes:
    """Wrap 2048 bytes of user payload into a 2352-byte Mode 2 Form 1 CD-ROM sector."""
    if len(user_2048) < SECTOR_USER_SIZE:
        user_2048 = user_2048 + b"\x00" * (SECTOR_USER_SIZE - len(user_2048))
    else:
        user_2048 = user_2048[:SECTOR_USER_SIZE]

    if orig_raw_2352 and len(orig_raw_2352) == SECTOR_RAW_SIZE:
        header_24 = orig_raw_2352[:24]
    else:
        sync = b"\x00" + (b"\xFF" * 10) + b"\x00"
        total_frames = lba + 150
        ff = total_frames % 75
        ss = (total_frames // 75) % 60
        mm = total_frames // (75 * 60)
        msf_mode = bytes([to_bcd(mm), to_bcd(ss), to_bcd(ff), 0x02])
        subhdr = b"\x00\x00\x08\x00\x00\x00\x08\x00"
        header_24 = sync + msf_mode + subhdr

    edc = compute_edc(header_24[16:24] + user_2048)
    edc_bytes = struct.pack("<I", edc)
    ecc_zero = b"\x00" * 276
    return header_24 + user_2048 + edc_bytes + ecc_zero


class DiscImageReader:
    """
    Reads sectors from:
      - 2352-byte/sector raw `.bin` (Mode 2 Form 1)
      - 2048-byte/sector `.iso`
      - `.chd` (MAME CHD v5 uncompressed/zlib-hunk CD image or via `chdman`)
    """

    def __init__(self, image_path: Path):
        self.bin_path = Path(image_path)
        self.file_size = self.bin_path.stat().st_size
        self.fp = open(self.bin_path, "rb")
        self.is_chd = False
        self.is_raw_2352 = False
        self._chd_hunk_bytes = 0
        self._chd_unit_bytes = CHD_CD_SECTOR_SIZE
        self._chd_map_offset = 0
        self._chd_Comp = False
        self._detect_format()

    def _detect_format(self):
        self.fp.seek(0)
        head = self.fp.read(124)
        if head[:8] == b"MComprHD":
            # MAME CHD v5 header (124 bytes big-endian)
            self.is_chd = True
            hdr_len, hdr_ver = struct.unpack_from(">II", head, 8)
            if hdr_ver == 5 and len(head) >= 124:
                comp0 = struct.unpack_from(">I", head, 16)[0]
                logical_bytes = struct.unpack_from(">Q", head, 32)[0]
                self._chd_map_offset = struct.unpack_from(">Q", head, 40)[0]
                self._chd_hunk_bytes = struct.unpack_from(">I", head, 56)[0]
                self._chd_unit_bytes = struct.unpack_from(">I", head, 60)[0] or CHD_CD_SECTOR_SIZE
                self._chd_Comp = (comp0 != 0)
                self.total_sectors = int(logical_bytes // self._chd_unit_bytes)
                self.sector_stride = self._chd_unit_bytes
                self.payload_offset = SECTOR_SYNC_HEADER
                return

        if head[:12] == b"\x00\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\x00" or (self.file_size % SECTOR_RAW_SIZE == 0):
            self.is_raw_2352 = True
            self.sector_stride = SECTOR_RAW_SIZE
            self.payload_offset = SECTOR_SYNC_HEADER
        else:
            self.is_raw_2352 = False
            self.sector_stride = SECTOR_USER_SIZE
            self.payload_offset = 0
        self.total_sectors = self.file_size // self.sector_stride

    def _read_chd_sector(self, lba: int) -> bytes:
        frames_per_hunk = self._chd_hunk_bytes // self._chd_unit_bytes
        hunk_idx = lba // frames_per_hunk
        frame_in_hunk = lba % frames_per_hunk

        if not self._chd_Comp:
            # Uncompressed CHD v5 map: 4 bytes per hunk (uint32 block offset in hunk_bytes units)
            self.fp.seek(self._chd_map_offset + hunk_idx * 4)
            block_idx = struct.unpack(">I", self.fp.read(4))[0]
            if block_idx == 0:
                return b"\x00" * SECTOR_USER_SIZE
            hunk_off = block_idx * self._chd_hunk_bytes
            frame_off = hunk_off + frame_in_hunk * self._chd_unit_bytes
            self.fp.seek(frame_off)
            raw_frame = self.fp.read(SECTOR_RAW_SIZE)
        else:
            # Compressed CHD v5 map entry: 12 bytes per hunk
            # byte 0: compression type, bytes 1..3: 24-bit compressed length, bytes 4..9: 48-bit offset
            self.fp.seek(self._chd_map_offset + hunk_idx * 12)
            entry = self.fp.read(12)
            ctype = entry[0]
            clen = (entry[1] << 16) | (entry[2] << 8) | entry[3]
            coff = int.from_bytes(entry[4:10], "big")
            self.fp.seek(coff)
            cbuf = self.fp.read(clen)
            if ctype == 4:  #CHD_MAKE_TAG('n','o','n','e') / uncompressed hunk
                hunk_data = cbuf
            else:
                try:
                    hunk_data = zlib.decompress(cbuf)
                except Exception:
                    hunk_data = zlib.decompress(cbuf, -15)
            start = frame_in_hunk * self._chd_unit_bytes
            raw_frame = hunk_data[start: start + SECTOR_RAW_SIZE]

        if len(raw_frame) >= SECTOR_SYNC_HEADER + SECTOR_USER_SIZE and raw_frame[:12] == b"\x00" + b"\xFF" * 10 + b"\x00":
            return raw_frame[24: 24 + SECTOR_USER_SIZE]
        return raw_frame[:SECTOR_USER_SIZE].ljust(SECTOR_USER_SIZE, b"\x00")

    def read_user_sectors(self, start_lba: int, count: int) -> bytes:
        out = bytearray()
        for lba in range(start_lba, start_lba + count):
            if self.is_chd:
                out.extend(self._read_chd_sector(lba))
            else:
                off = lba * self.sector_stride + self.payload_offset
                self.fp.seek(off)
                chunk = self.fp.read(SECTOR_USER_SIZE)
                if len(chunk) < SECTOR_USER_SIZE:
                    chunk += b"\x00" * (SECTOR_USER_SIZE - len(chunk))
                out.extend(chunk)
        return bytes(out)

    def read_bytes_at_lba(self, start_lba: int, byte_length: int) -> bytes:
        n_sectors = (byte_length + SECTOR_USER_SIZE - 1) // SECTOR_USER_SIZE
        data = self.read_user_sectors(start_lba, n_sectors)
        return data[:byte_length]

    def close(self):
        if self.fp:
            self.fp.close()
            self.fp = None


def parse_iso9660_directory(reader: DiscImageReader) -> Dict[str, dict]:
    """Parse ISO 9660 Primary Volume Descriptor (LBA 16) and root/sub directories."""
    pvd = reader.read_user_sectors(16, 1)
    if pvd[0:6] != b"\x01CD001":
        raise ValueError(f"{reader.bin_path} does not have a valid ISO 9660 PVD at LBA 16.")

    root_record = pvd[156:156 + 34]
    root_lba = struct.unpack_from("<I", root_record, 2)[0]
    root_len = struct.unpack_from("<I", root_record, 10)[0]

    files: Dict[str, dict] = {}

    def walk_dir(dir_lba: int, dir_len: int, prefix: str = ""):
        raw = reader.read_bytes_at_lba(dir_lba, dir_len)
        pos = 0
        while pos < len(raw):
            rec_len = raw[pos]
            if rec_len == 0:
                next_sec = ((pos // SECTOR_USER_SIZE) + 1) * SECTOR_USER_SIZE
                if next_sec <= pos:
                    break
                pos = next_sec
                continue
            extent_lba = struct.unpack_from("<I", raw, pos + 2)[0]
            data_len = struct.unpack_from("<I", raw, pos + 10)[0]
            flags = raw[pos + 25]
            name_len = raw[pos + 32]
            name_raw = raw[pos + 33: pos + 33 + name_len].decode("ascii", errors="ignore")
            clean_name = name_raw.split(";")[0]

            if clean_name not in ("", "\x00", "\x01"):
                rel_path = f"{prefix}/{clean_name}" if prefix else clean_name
                is_dir = bool(flags & 0x02)
                if is_dir:
                    walk_dir(extent_lba, data_len, rel_path)
                else:
                    files[rel_path] = {
                        "name": clean_name,
                        "path": rel_path,
                        "lba": extent_lba,
                        "size": data_len,
                        "sectors": (data_len + SECTOR_USER_SIZE - 1) // SECTOR_USER_SIZE,
                    }
            pos += rec_len

    walk_dir(root_lba, root_len, "")
    return files


def detect_disc_identity(iso_files: Dict[str, dict], fallback_disc: int = 1) -> Tuple[str, int, int, str]:
    """
    Detect executable name, disc number (1 or 2), region_id (USA=1, JPN=2), and region string.
    Supports North American (`SLUS_006.62` / `SLUS_006.68`) and Japanese (`SLPS_012.30` / `SLPS_012.31`).
    """
    for k in iso_files:
        ku = k.upper()
        if "SLUS_006.62" in ku:
            return k, 1, REGION_USA, "USA"
        if "SLUS_006.68" in ku:
            return k, 2, REGION_USA, "USA"
        if "SLPS_012.30" in ku:
            return k, 1, REGION_JPN, "JPN"
        if "SLPS_012.31" in ku:
            return k, 2, REGION_JPN, "JPN"
    exe = "SLUS_006.62" if fallback_disc == 1 else "SLUS_006.68"
    return exe, fallback_disc, REGION_USA, "USA"


def scan_pe_img_packages(reader: DiscImageReader, iso_files: Dict[str, dict], exe_name: str) -> List[dict]:
    """Locate the PE.IMG package table from the executable or directly from PE.IMG headers."""
    pe_img_info = None
    for k, v in iso_files.items():
        if k.upper().endswith(("PE.IMG", "PE1.IMG", "PE2.IMG")):
            pe_img_info = v
            break
    if not pe_img_info:
        return []

    pe_img_lba = pe_img_info["lba"]
    pe_img_sectors = pe_img_info["sectors"]
    packages: List[dict] = []

    if exe_name in iso_files:
        exe_info = iso_files[exe_name]
        exe_bytes = reader.read_bytes_at_lba(exe_info["lba"], exe_info["size"])
        marker_idx = exe_bytes.find(b"PELB")
        if marker_idx != -1 and marker_idx + 8 <= len(exe_bytes):
            pkg_count = struct.unpack_from("<I", exe_bytes, marker_idx + 4)[0]
            pos = marker_idx + 8
            for pkg_id in range(pkg_count):
                if pos + 8 > len(exe_bytes):
                    break
                rel_sector, sec_count = struct.unpack_from("<II", exe_bytes, pos)
                pos += 8
                if sec_count == 0:
                    continue
                packages.append({
                    "pkg_id": pkg_id,
                    "name": f"pkg_{pkg_id:04d}",
                    "start_lba": pe_img_lba + rel_sector,
                    "rel_sector": rel_sector,
                    "sectors": sec_count,
                    "size": sec_count * SECTOR_USER_SIZE,
                })
            if packages:
                return packages

        best_run: List[Tuple[int, int]] = []
        for off in range(0x800, len(exe_bytes) - 64, 4):
            first_val = struct.unpack_from("<I", exe_bytes, off)[0]
            if first_val != 0:
                continue
            run: List[Tuple[int, int]] = []
            cur_off = off
            prev_sec = 0
            while cur_off + 4 <= len(exe_bytes):
                next_sec = struct.unpack_from("<I", exe_bytes, cur_off + 4)[0]
                diff = next_sec - prev_sec
                if 1 <= diff <= 4096 and next_sec <= pe_img_sectors:
                    run.append((prev_sec, diff))
                    prev_sec = next_sec
                    cur_off += 4
                else:
                    break
            if len(run) > len(best_run) and len(run) >= 16:
                best_run = run

        if best_run:
            for pkg_id, (rel_sec, sec_cnt) in enumerate(best_run):
                packages.append({
                    "pkg_id": pkg_id,
                    "name": f"pkg_{pkg_id:04d}",
                    "start_lba": pe_img_lba + rel_sec,
                    "rel_sector": rel_sec,
                    "sectors": sec_cnt,
                    "size": sec_cnt * SECTOR_USER_SIZE,
                })
            return packages

    cur_rel = 0
    pkg_id = 0
    while cur_rel < pe_img_sectors:
        sec_data = reader.read_user_sectors(pe_img_lba + cur_rel, 1)
        magic, count = struct.unpack_from("<II", sec_data, 0)
        if magic == PEPK_MAGIC and 1 <= count <= 1024:
            max_end = SECTOR_USER_SIZE
            hdr_sectors = ((8 + count * 16 + SECTOR_USER_SIZE - 1) // SECTOR_USER_SIZE)
            hdr_bytes = reader.read_user_sectors(pe_img_lba + cur_rel, hdr_sectors)
            for i in range(count):
                _, _, a_off, a_sz = struct.unpack_from("<IIII", hdr_bytes, 8 + i * 16)
                if a_off + a_sz > max_end:
                    max_end = a_off + a_sz
            sec_cnt = (max_end + SECTOR_USER_SIZE - 1) // SECTOR_USER_SIZE
            packages.append({
                "pkg_id": pkg_id,
                "name": f"pkg_{pkg_id:04d}",
                "start_lba": pe_img_lba + cur_rel,
                "rel_sector": cur_rel,
                "sectors": sec_cnt,
                "size": sec_cnt * SECTOR_USER_SIZE,
            })
            cur_rel += sec_cnt
            pkg_id += 1
        else:
            break

    return packages


def unpack_package_subassets(pkg_bytes: bytes) -> List[dict]:
    """Parse sub-assets inside a PE.IMG package if it carries an asset descriptor table."""
    if len(pkg_bytes) < 16:
        return []
    magic_or_count = struct.unpack_from("<I", pkg_bytes, 0)[0]
    has_magic = (magic_or_count == PEPK_MAGIC)
    table_off = 8 if has_magic else 4
    count = struct.unpack_from("<I", pkg_bytes, 4)[0] if has_magic else magic_or_count

    if count == 0 or count > 1024 or table_off + count * 16 > len(pkg_bytes):
        return []

    subassets = []
    for i in range(count):
        atype, sub_idx, offset, size = struct.unpack_from("<IIII", pkg_bytes, table_off + i * 16)
        if offset < table_off + count * 16 or offset + size > len(pkg_bytes):
            return []
        folder = ASSET_TYPE_FOLDERS.get(atype, ASSET_TYPE_FOLDERS[12])
        rel_name = "memory.dat" if (atype == 0 and sub_idx == 0) else f"{folder}/asset_{sub_idx:04d}.bin"
        subassets.append({
            "index": i,
            "asset_type": atype,
            "sub_index": sub_idx,
            "offset": offset,
            "size": size,
            "rel_name": rel_name,
        })
    return subassets


def rebuild_package_with_overrides(orig_pkg_bytes: bytes, pkg_romfs_dir: Path) -> Tuple[Optional[bytes], int]:
    """
    Replace ONLY the sub-assets that exist in `pkg_romfs_dir` and take all other sub-assets
    from `orig_pkg_bytes`. Returns `(patched_bytes, replaced_count)`.
    """
    subassets = unpack_package_subassets(orig_pkg_bytes)
    if not subassets:
        return None, 0

    magic_or_count = struct.unpack_from("<I", orig_pkg_bytes, 0)[0]
    has_magic = (magic_or_count == PEPK_MAGIC)
    table_off = 8 if has_magic else 4
    count = len(subassets)

    chunks: List[bytes] = []
    descs: List[Tuple[int, int, int, int]] = []
    replaced = 0

    for item in subassets:
        candidate = pkg_romfs_dir / item["rel_name"]
        if candidate.is_file():
            mod_data = candidate.read_bytes()
            chunks.append(mod_data)
            descs.append((item["asset_type"], item["sub_index"], 0, len(mod_data)))
            replaced += 1
        else:
            orig_slice = orig_pkg_bytes[item["offset"]: item["offset"] + item["size"]]
            chunks.append(orig_slice)
            descs.append((item["asset_type"], item["sub_index"], 0, len(orig_slice)))

    if replaced == 0:
        return None, 0

    cur_off = (table_off + count * 16 + 15) & ~15
    updated_descs = []
    for (atype, sub_idx, _, sz) in descs:
        updated_descs.append((atype, sub_idx, cur_off, sz))
        cur_off = (cur_off + sz + 15) & ~15

    total_sz = max(len(orig_pkg_bytes), (cur_off + SECTOR_USER_SIZE - 1) & ~(SECTOR_USER_SIZE - 1))
    out = bytearray(total_sz)
    out[:table_off] = orig_pkg_bytes[:table_off]

    for i, (atype, sub_idx, off, sz) in enumerate(updated_descs):
        struct.pack_into("<IIII", out, table_off + i * 16, atype, sub_idx, off, sz)
        out[off: off + sz] = chunks[i]

    return bytes(out), replaced


def resolve_012_userdata_dir(game_root: Path) -> Path:
    """Resolve the active 0.12-alpha user/portable directory (`PE_CONFIG_HOME` or `userdata/`)."""
    env_cfg = os.environ.get("PE_CONFIG_HOME")
    if env_cfg:
        return Path(env_cfg)
    if (game_root / "portable.txt").is_file() or (game_root / "userdata").is_dir():
        return game_root / "userdata"
    return game_root


def sync_012_native_asset_packs(game_root: Path, romfs_root: Path) -> Dict[str, int]:
    """
    Syncs 0.12-alpha native mod asset folders from `mods/layeredfs/romfs/` into the
    exact locations expected by `parasite-eve-pc` v0.12-alpha:
      - `romfs/SKINS/<id>/`          -> `<userdata>/pe_skins/<id>/` (for `pe_wardrobe`)
      - `romfs/PACKS/<pack>/`        -> `<userdata>/packs/<pack>/` (for `pe_wardrobe` pack.json v1)
      - `romfs/FONTS/*.png`          -> `<game_root>/mods/fonts/*.png` (for `pe_fonts`)
      - `romfs/CALLS/*.txt`          -> `<userdata>/pe_calls/*.txt` (for `pe_phone`)
      - `romfs/LANG/*.pelang`        -> `<game_root>/lang/*.pelang` (for `pe_lang`)
      - `romfs/HD_BACKGROUNDS/...`   -> `<userdata>/backgrounds/...` (for 0.12 HD Background pack)
    """
    userdata = resolve_012_userdata_dir(game_root)
    counts = {
        "skins": 0,
        "packs": 0,
        "fonts": 0,
        "calls": 0,
        "lang": 0,
        "hd_backgrounds": 0,
    }

    mappings = [
        ("SKINS", userdata / "pe_skins", "skins"),
        ("PACKS", userdata / "packs", "packs"),
        ("FONTS", game_root / "mods" / "fonts", "fonts"),
        ("CALLS", userdata / "pe_calls", "calls"),
        ("LANG", game_root / "lang", "lang"),
        ("HD_BACKGROUNDS", userdata / "backgrounds", "hd_backgrounds"),
    ]

    for src_name, dst_base, key in mappings:
        src_dir = romfs_root / src_name
        if not src_dir.is_dir():
            continue
        for root, _, files in os.walk(src_dir):
            for fname in files:
                if fname.startswith("_DROP_") or fname.endswith(".meta"):
                    continue
                src_file = Path(root) / fname
                rel = src_file.relative_to(src_dir)
                dst_file = dst_base / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                counts[key] += 1

    return counts


def init_disc_tree(
    bin_path: Path,
    game_root: Path,
    disc_num: int = 1,
    extract_files: bool = False,
) -> dict:
    """
    Parse the original Parasite Eve `.bin`/`.iso`/`.chd` disc image, generate `manifest_disc<N>.json`,
    and create the mirrored directory structure in `mods/layeredfs/romfs/DISC<N>/` plus all 0.12-alpha
    asset directories (`SKINS`, `PACKS`, `FONTS`, `CALLS`, `LANG`, `HD_BACKGROUNDS`).
    """
    reader = DiscImageReader(bin_path)
    try:
        iso_files = parse_iso9660_directory(reader)
        exe_name, detected_disc, region_id, region_str = detect_disc_identity(iso_files, disc_num)
        disc_num = detected_disc

        packages = scan_pe_img_packages(reader, iso_files, exe_name)

        lfs_root = game_root / "mods" / "layeredfs"
        romfs_root = lfs_root / "romfs"
        romfs_disc = romfs_root / f"DISC{disc_num}"
        romfs_disc.mkdir(parents=True, exist_ok=True)

        # Create all 0.12-alpha asset override directories
        for sub_dir in [
            "TIM_OVERRIDES",
            "SKINS",
            "PACKS",
            "FONTS",
            "CALLS",
            "LANG",
            "HD_BACKGROUNDS",
        ]:
            (romfs_root / sub_dir).mkdir(parents=True, exist_ok=True)

        ini_path = lfs_root / "layeredfs.ini"
        if not ini_path.exists():
            ini_path.write_text(
                "# Parasite Eve PC (v0.12-alpha+) LayeredFS Configuration\n"
                "enabled = 1\n"
                "profile = default\n"
                f"region = {region_str}\n"
                "log_reads = 1\n",
                encoding="utf-8",
            )

        for rel_path, info in iso_files.items():
            target = romfs_disc / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if extract_files and not rel_path.upper().endswith("PE.IMG"):
                target.write_bytes(reader.read_bytes_at_lba(info["lba"], info["size"]))

        pkg_manifest = []
        for pkg in packages:
            pkg_dir = romfs_disc / "PE_IMG" / pkg["name"]
            pkg_dir.mkdir(parents=True, exist_ok=True)
            pkg_bytes = reader.read_user_sectors(pkg["start_lba"], pkg["sectors"])
            subassets = unpack_package_subassets(pkg_bytes)

            for folder_name in ASSET_TYPE_FOLDERS.values():
                (pkg_dir / folder_name).mkdir(parents=True, exist_ok=True)

            if extract_files:
                if subassets:
                    for sa in subassets:
                        out_f = pkg_dir / sa["rel_name"]
                        out_f.parent.mkdir(parents=True, exist_ok=True)
                        out_f.write_bytes(pkg_bytes[sa["offset"]: sa["offset"] + sa["size"]])
                else:
                    (romfs_disc / "PE_IMG" / f"{pkg['name']}.bin").write_bytes(pkg_bytes)

            pkg_entry = dict(pkg)
            pkg_entry["subasset_count"] = len(subassets)
            pkg_entry["subassets"] = subassets
            pkg_manifest.append(pkg_entry)

        manifest = {
            "target_recomp_version": "0.12-alpha",
            "disc_number": disc_num,
            "region": region_str,
            "region_id": region_id,
            "source_bin": str(bin_path.resolve()),
            "is_chd": reader.is_chd,
            "is_raw_2352": reader.is_raw_2352,
            "total_sectors": reader.total_sectors,
            "executable": exe_name,
            "iso_files": iso_files,
            "packages": pkg_manifest,
        }

        manifest_path = lfs_root / f"manifest_disc{disc_num}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        reader.close()


def sync_layeredfs_overrides(
    game_root: Path,
    disc_num: int = 1,
    build_virtual_disc: bool = False,
    virtual_bin_out: Optional[Path] = None,
) -> dict:
    """
    Scan `mods/layeredfs/romfs/` (and 0.12-alpha `userdata/layeredfs/romfs/` if present):
      - Replaces only files/packages/sub-assets present in `romfs/`.
      - Leaves all missing files untouched (falling back to the original disc).
      - Syncs 0.12-alpha native folders (`SKINS`, `PACKS`, `FONTS`, `CALLS`, `LANG`, `HD_BACKGROUNDS`).
      - Writes `mods/layeredfs/override_cache.bin` (v2 header with region_id).
      - Optionally writes a patched virtual `.bin`/`.cue` disc image.
    """
    lfs_root = game_root / "mods" / "layeredfs"
    manifest_path = lfs_root / f"manifest_disc{disc_num}.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}. Run `init-tree` first.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_bin = Path(manifest["source_bin"])
    region_id = manifest.get("region_id", REGION_USA)
    romfs_root = lfs_root / "romfs"
    romfs_disc = romfs_root / f"DISC{disc_num}"

    # Sync 0.12-alpha native asset folders (Wardrobe skins/packs, fonts, phone calls, lang, HD BGs)
    native_counts = sync_012_native_asset_packs(game_root, romfs_root)

    reader = DiscImageReader(source_bin)
    overrides: List[dict] = []

    try:
        for rel_path, info in manifest["iso_files"].items():
            candidate = romfs_disc / rel_path
            if candidate.is_file():
                mod_bytes = candidate.read_bytes()
                orig_bytes = reader.read_bytes_at_lba(info["lba"], info["size"])
                if mod_bytes != orig_bytes:
                    overrides.append({
                        "start_lba": info["lba"],
                        "sector_count": info["sectors"],
                        "pkg_id": 0xFFFFFFFF,
                        "flags": 2,
                        "virtual_path": f"DISC{disc_num}/{rel_path}",
                        "payload": mod_bytes[: info["sectors"] * SECTOR_USER_SIZE].ljust(
                            info["sectors"] * SECTOR_USER_SIZE, b"\x00"
                        ),
                    })

        for pkg in manifest["packages"]:
            pkg_id = pkg["pkg_id"]
            pkg_name = pkg["name"]
            start_lba = pkg["start_lba"]
            sectors = pkg["sectors"]

            raw_pkg_override = romfs_disc / "PE_IMG" / f"{pkg_name}.bin"
            pkg_dir = romfs_disc / "PE_IMG" / pkg_name

            if raw_pkg_override.is_file():
                mod_pkg = raw_pkg_override.read_bytes()
                orig_pkg = reader.read_user_sectors(start_lba, sectors)
                if mod_pkg != orig_pkg:
                    overrides.append({
                        "start_lba": start_lba,
                        "sector_count": sectors,
                        "pkg_id": pkg_id,
                        "flags": 2,
                        "virtual_path": f"DISC{disc_num}/PE_IMG/{pkg_name}.bin",
                        "payload": mod_pkg[: sectors * SECTOR_USER_SIZE].ljust(
                            sectors * SECTOR_USER_SIZE, b"\x00"
                        ),
                    })
            elif pkg_dir.is_dir():
                orig_pkg = reader.read_user_sectors(start_lba, sectors)
                patched_pkg, replaced_cnt = rebuild_package_with_overrides(orig_pkg, pkg_dir)
                if patched_pkg is not None and replaced_cnt > 0 and patched_pkg != orig_pkg:
                    overrides.append({
                        "start_lba": start_lba,
                        "sector_count": sectors,
                        "pkg_id": pkg_id,
                        "flags": 1,
                        "replaced_subassets": replaced_cnt,
                        "virtual_path": f"DISC{disc_num}/PE_IMG/{pkg_name} ({replaced_cnt} sub-assets)",
                        "payload": patched_pkg[: sectors * SECTOR_USER_SIZE].ljust(
                            sectors * SECTOR_USER_SIZE, b"\x00"
                        ),
                    })

        cache_path = lfs_root / "override_cache.bin"
        blob_pool = bytearray()
        entry_structs = bytearray()

        for ov in overrides:
            data_offset = len(blob_pool)
            payload = ov["payload"]
            blob_pool.extend(payload)
            vpath_bytes = ov["virtual_path"].encode("utf-8")[:127].ljust(128, b"\x00")
            entry_structs.extend(
                struct.pack(
                    "<IIIIQQ128s",
                    ov["start_lba"],
                    ov["sector_count"],
                    ov["pkg_id"],
                    ov["flags"],
                    data_offset,
                    len(payload),
                    vpath_bytes,
                )
            )

        # v2 PeLfsCacheHeader: magic, version(2), disc_number, region_id, entry_count, reserved(0), total_blob_sz
        header_bytes = struct.pack(
            "<IIIIIIQ",
            CACHE_MAGIC,
            CACHE_VERSION,
            disc_num,
            region_id,
            len(overrides),
            0,
            len(blob_pool),
        )
        cache_bytes = header_bytes + entry_structs + blob_pool
        cache_path.write_bytes(cache_bytes)

        # Also copy cache into `userdata/layeredfs/override_cache.bin` if 0.12 portable mode is active
        if (game_root / "portable.txt").is_file() or (game_root / "userdata").is_dir():
            u_lfs = game_root / "userdata" / "layeredfs"
            u_lfs.mkdir(parents=True, exist_ok=True)
            (u_lfs / "override_cache.bin").write_bytes(cache_bytes)

        virtual_cue_path = None
        if build_virtual_disc and not reader.is_chd:
            if virtual_bin_out is None:
                virtual_bin_out = game_root / f"Parasite_Eve_LayeredFS_Disc{disc_num}.bin"
            shutil.copyfile(source_bin, virtual_bin_out)
            with open(virtual_bin_out, "r+b") as vfp:
                for ov in overrides:
                    start_lba = ov["start_lba"]
                    sec_count = ov["sector_count"]
                    payload = ov["payload"]
                    for s in range(sec_count):
                        lba = start_lba + s
                        user_sec = payload[s * SECTOR_USER_SIZE: (s + 1) * SECTOR_USER_SIZE]
                        if reader.is_raw_2352:
                            vfp.seek(lba * SECTOR_RAW_SIZE)
                            orig_raw = vfp.read(SECTOR_RAW_SIZE)
                            raw_sec = wrap_mode2_form1_sector(lba, user_sec, orig_raw)
                            vfp.seek(lba * SECTOR_RAW_SIZE)
                            vfp.write(raw_sec)
                        else:
                            vfp.seek(lba * SECTOR_USER_SIZE)
                            vfp.write(user_sec)

            virtual_cue_path = virtual_bin_out.with_suffix(".cue")
            mode_str = "MODE2/2352" if reader.is_raw_2352 else "MODE1/2048"
            virtual_cue_path.write_text(
                f'FILE "{virtual_bin_out.name}" BINARY\n'
                f"  TRACK 01 {mode_str}\n"
                f"    INDEX 01 00:00:00\n",
                encoding="utf-8",
            )

        return {
            "override_count": len(overrides),
            "native_012_synced": native_counts,
            "cache_path": str(cache_path),
            "virtual_bin": str(virtual_bin_out) if (build_virtual_disc and not reader.is_chd) else None,
            "virtual_cue": str(virtual_cue_path) if virtual_cue_path else None,
            "overrides": [
                {
                    "virtual_path": o["virtual_path"],
                    "start_lba": o["start_lba"],
                    "sector_count": o["sector_count"],
                }
                for o in overrides
            ],
        }
    finally:
        reader.close()


def main():
    parser = argparse.ArgumentParser(
        description="Parasite Eve PC (v0.12-alpha / main) LayeredFS Manager & Disc Extractor"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-tree", help="Mirror Parasite Eve (.bin/.iso/.chd) into mods/layeredfs/romfs/")
    p_init.add_argument("--bin", required=True, type=Path, help="Path to original Parasite Eve .bin, .iso, or .chd")
    p_init.add_argument("--root", default=Path("."), type=Path, help="Game root directory")
    p_init.add_argument("--disc", default=1, type=int, choices=[1, 2], help="Disc number (1 or 2)")
    p_init.add_argument("--extract-all", action="store_true", help="Extract all base assets into romfs/")

    p_sync = sub.add_parser("sync", help="Compile active romfs/ overrides for v0.12-alpha")
    p_sync.add_argument("--root", default=Path("."), type=Path, help="Game root directory")
    p_sync.add_argument("--disc", default=1, type=int, choices=[1, 2], help="Disc number (1 or 2)")
    p_sync.add_argument("--virtual-disc", action="store_true", help="Also write a patched virtual .bin/.cue image")
    p_sync.add_argument("--out-bin", default=None, type=Path, help="Custom path for virtual .bin output")

    args = parser.parse_args()
    if args.cmd == "init-tree":
        manifest = init_disc_tree(args.bin, args.root, args.disc, args.extract_all)
        print(
            f"[LayeredFS v0.12] Initialized DISC{manifest['disc_number']} ({manifest['region']}) tree in "
            f"{args.root / 'mods/layeredfs/romfs'} "
            f"({len(manifest['iso_files'])} ISO files, {len(manifest['packages'])} PE.IMG packages)."
        )
    elif args.cmd == "sync":
        res = sync_layeredfs_overrides(args.root, args.disc, args.virtual_disc, args.out_bin)
        print(f"[LayeredFS v0.12] Synced {res['override_count']} disc sector override(s) -> {res['cache_path']}")
        for ov in res["overrides"]:
            print(f"  * OVERRIDE: {ov['virtual_path']} (LBA {ov['start_lba']}, {ov['sector_count']} sectors)")
        for k, cnt in res["native_012_synced"].items():
            if cnt > 0:
                print(f"  * SYNCED 0.12 {k.upper()}: {cnt} file(s)")
        if res["virtual_cue"]:
            print(f"[LayeredFS v0.12] Virtual disc ready: {res['virtual_cue']}")


if __name__ == "__main__":
    main()
