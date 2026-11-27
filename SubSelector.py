#!/usr/bin/env python3
"""
DVD (.sup / .sub) & Blu-ray PGS (.sup) Bin-Based Visual OCR Reviewer
Usage: python SubSelector.py path/to/subtitles.sup
"""

import base64
import io
import json
import os
import struct
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


# =====================================================================
# 1A. BLU-RAY PGS (.SUP) PARSER
# =====================================================================

class PGSParser:
    SEG_PDS = 0x14
    SEG_ODS = 0x15
    SEG_PCS = 0x16
    SEG_END = 0x80

    def parse_file(self, filepath):
        with open(filepath, "rb") as f:
            data = f.read()

        pos = 0
        length = len(data)
        cues = []
        palette = {}
        obj_buffers = {}
        obj_dims = {}
        pcs_info = None

        while pos + 13 <= length:
            if data[pos:pos + 2] != b"PG":
                pos += 1
                continue

            pts = struct.unpack(">I", data[pos + 2:pos + 6])[0]
            seg_type = data[pos + 10]
            seg_size = struct.unpack(">H", data[pos + 11:pos + 13])[0]
            seg_data = data[pos + 13:pos + 13 + seg_size]
            pos += 13 + seg_size

            if seg_type == self.SEG_PCS and len(seg_data) >= 11:
                comp_state = seg_data[7]
                num_comps = seg_data[10]
                comp_objs = []
                c_pos = 11
                for _ in range(num_comps):
                    if c_pos + 8 <= len(seg_data):
                        oid, wid, cropped, x, y = struct.unpack(">HBBHH", seg_data[c_pos:c_pos + 8])
                        comp_objs.append((oid, x, y))
                        c_pos += 8
                        if cropped & 0x80:
                            c_pos += 8
                pcs_info = {"pts_ms": int(pts / 90.0), "objects": comp_objs}
                if comp_state in (0x80, 0x40):
                    palette.clear()
                    obj_buffers.clear()
                    obj_dims.clear()

            elif seg_type == self.SEG_PDS and len(seg_data) >= 2:
                p_pos = 2
                while p_pos + 5 <= len(seg_data):
                    entry_id, y_val, cr, cb, alpha = struct.unpack("BBBBB", seg_data[p_pos:p_pos + 5])
                    r = max(0, min(255, int(y_val + 1.402 * (cr - 128))))
                    g = max(0, min(255, int(y_val - 0.34414 * (cb - 128) - 0.71414 * (cr - 128))))
                    b = max(0, min(255, int(y_val + 1.772 * (cb - 128))))
                    palette[entry_id] = (r, g, b, alpha)
                    p_pos += 5

            elif seg_type == self.SEG_ODS and len(seg_data) >= 4:
                oid = struct.unpack(">H", seg_data[0:2])[0]
                is_first = bool(seg_data[3] & 0x80)
                if is_first and len(seg_data) >= 11:
                    w, h = struct.unpack(">HH", seg_data[7:11])
                    obj_dims[oid] = (w, h)
                    obj_buffers[oid] = bytearray(seg_data[11:])
                elif oid in obj_buffers:
                    obj_buffers[oid].extend(seg_data[4:])

            elif seg_type == self.SEG_END and pcs_info is not None:
                if cues and cues[-1]["end_ms"] is None:
                    cues[-1]["end_ms"] = pcs_info["pts_ms"]
                if pcs_info["objects"]:
                    rendered = self._compose_cue(pcs_info["objects"], obj_dims, obj_buffers, palette)
                    if rendered is not None:
                        cues.append({
                            "index": len(cues) + 1,
                            "start_ms": pcs_info["pts_ms"],
                            "end_ms": None,
                            "image": rendered,
                        })
                pcs_info = None

        if cues and cues[-1]["end_ms"] is None:
            cues[-1]["end_ms"] = cues[-1]["start_ms"] + 3000
        return cues

    def _decode_rle(self, rle_bytes, width, height):
        indices = bytearray()
        i = 0
        n = len(rle_bytes)
        while i < n:
            b = rle_bytes[i]
            i += 1
            if b != 0x00:
                indices.append(b)
            else:
                if i >= n:
                    break
                flag = rle_bytes[i]
                i += 1
                if flag == 0x00:
                    rem = len(indices) % width
                    if rem != 0:
                        indices.extend(b"\x00" * (width - rem))
                elif (flag & 0xC0) == 0x00:
                    indices.extend(b"\x00" * (flag & 0x3F))
                elif (flag & 0xC0) == 0x40:
                    if i >= n:
                        break
                    run_len = ((flag & 0x3F) << 8) | rle_bytes[i]
                    i += 1
                    indices.extend(b"\x00" * run_len)
                elif (flag & 0xC0) == 0x80:
                    if i >= n:
                        break
                    run_len = flag & 0x3F
                    color = rle_bytes[i]
                    i += 1
                    indices.extend(bytes([color]) * run_len)
                elif (flag & 0xC0) == 0xC0:
                    if i + 1 >= n:
                        break
                    run_len = ((flag & 0x3F) << 8) | rle_bytes[i]
                    color = rle_bytes[i + 1]
                    i += 2
                    indices.extend(bytes([color]) * run_len)

        total = width * height
        if len(indices) < total:
            indices.extend(b"\x00" * (total - len(indices)))
        return np.frombuffer(bytes(indices[:total]), dtype=np.uint8).reshape((height, width))

    def _compose_cue(self, comp_objs, obj_dims, obj_buffers, palette):
        valid = []
        for oid, ox, oy in comp_objs:
            if oid in obj_dims and oid in obj_buffers:
                w, h = obj_dims[oid]
                if w > 0 and h > 0:
                    idx_map = self._decode_rle(obj_buffers[oid], w, h)
                    valid.append((ox, oy, w, h, idx_map))
        if not valid:
            return None

        min_x = min(v[0] for v in valid)
        min_y = min(v[1] for v in valid)
        max_x = max(v[0] + v[2] for v in valid)
        max_y = max(v[1] + v[3] for v in valid)

        canvas = np.zeros((max_y - min_y, max_x - min_x, 4), dtype=np.uint8)
        lut = np.zeros((256, 4), dtype=np.uint8)
        for pid, rgba in palette.items():
            lut[pid] = rgba

        for ox, oy, w, h, idx_map in valid:
            canvas[oy - min_y:oy - min_y + h, ox - min_x:ox - min_x + w] = lut[idx_map]
        return Image.fromarray(canvas, "RGBA")


# =====================================================================
# 1B. DVD RAW .SUP ("SP" PACKETS) & VOBSUB .SUB PARSER
# =====================================================================

class DVDSupParser:
    """Parses IFOEdit/ProjectX DVD .sup ('SP' + PTS + SPU) and VobSub .sub streams."""

    def parse_file(self, filepath):
        with open(filepath, "rb") as f:
            data = f.read()

        if data[:2] == b"SP":
            packets = self._extract_raw_sp_packets(data)
        else:
            packets = self._extract_ps_packets(data)

        cues = []
        for pts_ms, spu in packets:
            decoded = self._decode_spu(spu, pts_ms)
            if decoded is not None:
                decoded["index"] = len(cues) + 1
                if cues and cues[-1]["end_ms"] is None:
                    cues[-1]["end_ms"] = decoded["start_ms"]
                cues.append(decoded)

        if cues and cues[-1]["end_ms"] is None:
            cues[-1]["end_ms"] = cues[-1]["start_ms"] + 3000
        return cues

    def _extract_raw_sp_packets(self, data):
        packets = []
        pos = 0
        n = len(data)
        while pos + 14 <= n:
            if data[pos:pos + 2] != b"SP":
                pos += 1
                continue
            pts_le64 = struct.unpack("<Q", data[pos + 2:pos + 10])[0]
            pts_le32 = struct.unpack("<I", data[pos + 2:pos + 6])[0]
            pts_val = pts_le64 if pts_le64 < (1 << 40) else pts_le32
            pts_ms = int(pts_val / 90.0)

            spu_start = pos + 10
            spu_size = struct.unpack(">H", data[spu_start:spu_start + 2])[0]
            if spu_size < 4 or spu_start + spu_size > n:
                pos += 2
                continue
            packets.append((pts_ms, data[spu_start:spu_start + spu_size]))
            pos = spu_start + spu_size
        return packets

    def _extract_ps_packets(self, data):
        packets = []
        pos = 0
        n = len(data)
        cur_pts_ms = 0
        spu_buf = bytearray()
        expected_len = 0

        while pos + 6 <= n:
            if data[pos:pos + 3] != b"\x00\x00\x01":
                pos += 1
                continue
            stream_id = data[pos + 3]
            if stream_id == 0xBA:
                pos += 14
                continue
            if pos + 6 > n:
                break
            pkt_len = struct.unpack(">H", data[pos + 4:pos + 6])[0]
            pkt_end = min(n, pos + 6 + pkt_len)
            if stream_id == 0xBD and pos + 9 < pkt_end:
                flags = data[pos + 7]
                hdr_len = data[pos + 8]
                payload_start = pos + 9 + hdr_len
                if (flags & 0x80) and pos + 14 <= pkt_end:
                    p = data[pos + 9:pos + 14]
                    pts = (((p[0] >> 1) & 0x07) << 30) | (p[1] << 22) | (((p[2] >> 1) & 0x7F) << 15) | (p[3] << 7) | ((p[4] >> 1) & 0x7F)
                    cur_pts_ms = int(pts / 90.0)
                if payload_start < pkt_end:
                    sub_id = data[payload_start]
                    if 0x20 <= sub_id <= 0x3F:
                        chunk = data[payload_start + 1:pkt_end]
                        if not spu_buf and len(chunk) >= 2:
                            expected_len = struct.unpack(">H", chunk[0:2])[0]
                        spu_buf.extend(chunk)
                        if expected_len > 0 and len(spu_buf) >= expected_len:
                            packets.append((cur_pts_ms, bytes(spu_buf[:expected_len])))
                            spu_buf.clear()
                            expected_len = 0
            pos = pkt_end
        return packets

    def _classify_dvd_indices(self, idx_map, alphas):
        """Topologically identifies background, outline, and inner text fill indices."""
        h, w = idx_map.shape
        lut = np.zeros((4, 4), dtype=np.uint8)

        border = np.concatenate([idx_map[0, :], idx_map[-1, :], idx_map[:, 0], idx_map[:, -1]])
        border_counts = np.bincount(border, minlength=4)
        bg_idx = int(np.argmax(border_counts))

        candidates = [i for i in range(4) if i != bg_idx and alphas[i] > 0 and np.any(idx_map == i)]
        if not candidates:
            candidates = [i for i in range(4) if i != bg_idx and np.any(idx_map == i)]

        if not candidates:
            return lut

        if len(candidates) == 1:
            lut[candidates[0]] = (255, 255, 255, 255)
            return lut

        # Measure how strongly each candidate touches the transparent background
        bg_mask = (idx_map == bg_idx)
        bg_adj = np.zeros_like(bg_mask)
        bg_adj[1:, :] |= bg_mask[:-1, :]
        bg_adj[:-1, :] |= bg_mask[1:, :]
        bg_adj[:, 1:] |= bg_mask[:, :-1]
        bg_adj[:, :-1] |= bg_mask[:, 1:]

        touch_ratios = {}
        for c in candidates:
            c_mask = (idx_map == c)
            total_c = max(1, int(np.sum(c_mask)))
            touching = int(np.sum(c_mask & bg_adj))
            touch_ratios[c] = touching / float(total_c)

        # Text fill sits enclosed inside the outline, so it has the LOWEST background-touch ratio
        fill_idx = min(candidates, key=lambda c: touch_ratios[c])
        lut[fill_idx] = (255, 255, 255, 255)
        for c in candidates:
            if c != fill_idx:
                lut[c] = (24, 24, 24, 255)
        return lut

    def _decode_spu(self, spu, pts_ms):
        if len(spu) < 6:
            return None
        spu_size, dcsqt_off = struct.unpack(">HH", spu[0:4])
        if dcsqt_off >= len(spu):
            return None

        x1 = y1 = x2 = y2 = 0
        top_off = bot_off = 0
        colors = [0, 1, 2, 3]
        alphas = [0, 15, 15, 15]
        duration_ms = None

        seq_off = dcsqt_off
        visited = set()
        while seq_off + 4 <= len(spu) and seq_off not in visited:
            visited.add(seq_off)
            delay, next_off = struct.unpack(">HH", spu[seq_off:seq_off + 4])
            cmd_pos = seq_off + 4
            while cmd_pos < len(spu):
                cmd = spu[cmd_pos]
                cmd_pos += 1
                if cmd in (0x00, 0x01):
                    continue
                elif cmd == 0x02:
                    duration_ms = int((delay * 1024) / 90.0)
                elif cmd == 0x03 and cmd_pos + 2 <= len(spu):
                    b0, b1 = spu[cmd_pos:cmd_pos + 2]
                    cmd_pos += 2
                    colors = [(b1 & 0x0F), (b1 >> 4) & 0x0F, (b0 & 0x0F), (b0 >> 4) & 0x0F]
                elif cmd == 0x04 and cmd_pos + 2 <= len(spu):
                    b0, b1 = spu[cmd_pos:cmd_pos + 2]
                    cmd_pos += 2
                    alphas = [(b1 & 0x0F), (b1 >> 4) & 0x0F, (b0 & 0x0F), (b0 >> 4) & 0x0F]
                elif cmd == 0x05 and cmd_pos + 6 <= len(spu):
                    b = spu[cmd_pos:cmd_pos + 6]
                    cmd_pos += 6
                    x1 = (b[0] << 4) | (b[1] >> 4)
                    x2 = ((b[1] & 0x0F) << 8) | b[2]
                    y1 = (b[3] << 4) | (b[4] >> 4)
                    y2 = ((b[4] & 0x0F) << 8) | b[5]
                elif cmd == 0x06 and cmd_pos + 4 <= len(spu):
                    top_off, bot_off = struct.unpack(">HH", spu[cmd_pos:cmd_pos + 4])
                    cmd_pos += 4
                elif cmd == 0xFF:
                    break
                else:
                    break
            if next_off == seq_off or next_off >= len(spu):
                break
            seq_off = next_off

        width = x2 - x1 + 1
        height = y2 - y1 + 1
        if width <= 0 or height <= 0 or top_off <= 0 or bot_off <= 0:
            return None

        idx_map = np.zeros((height, width), dtype=np.uint8)
        self._decode_field(spu, top_off, bot_off if bot_off > top_off else dcsqt_off, idx_map, 0, width, height)
        self._decode_field(spu, bot_off, dcsqt_off, idx_map, 1, width, height)

        lut = self._classify_dvd_indices(idx_map, alphas)
        rgba = lut[idx_map]
        end_ms = (pts_ms + duration_ms) if duration_ms else None
        return {
            "start_ms": pts_ms,
            "end_ms": end_ms,
            "image": Image.fromarray(rgba, "RGBA"),
        }

    def _decode_field(self, spu, start_off, end_off, idx_map, start_row, width, height):
        nibble_pos = start_off * 2
        max_nibble = min(len(spu), end_off) * 2

        def get_nibble():
            nonlocal nibble_pos
            if nibble_pos >= max_nibble:
                return 0
            byte_val = spu[nibble_pos >> 1]
            nib = (byte_val >> 4) & 0x0F if (nibble_pos & 1) == 0 else (byte_val & 0x0F)
            nibble_pos += 1
            return nib

        for row in range(start_row, height, 2):
            col = 0
            while col < width and nibble_pos < max_nibble:
                n0 = get_nibble()
                if n0 >= 0x4:
                    run_len = n0 >> 2
                    color = n0 & 0x3
                elif n0 >= 0x1:
                    n1 = get_nibble()
                    val = (n0 << 4) | n1
                    run_len = val >> 2
                    color = val & 0x3
                else:
                    n1 = get_nibble()
                    if n1 >= 0x4:
                        n2 = get_nibble()
                        val = (n1 << 4) | n2
                        run_len = val >> 2
                        color = val & 0x3
                    else:
                        n2 = get_nibble()
                        n3 = get_nibble()
                        val = (n1 << 8) | (n2 << 4) | n3
                        run_len = val >> 2
                        color = val & 0x3
                        if run_len == 0:
                            run_len = width - col

                end_col = min(width, col + run_len)
                if color > 0:
                    idx_map[row, col:end_col] = color
                col = end_col

            if nibble_pos & 1:
                nibble_pos += 1


# =====================================================================
# 2. BUILT-IN TEMPLATE CLASSIFIER + SEGMENTATION + BIN ENGINE
# =====================================================================

def rgba_to_foreground_mask(pil_img):
    arr = np.array(pil_img, dtype=np.float32)
    alpha = arr[:, :, 3]
    lum = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]) * (alpha / 255.0)
    if lum.max() == 0:
        return np.zeros(lum.shape, dtype=bool)
    thresh = max(80.0, lum.max() * 0.55)
    return lum >= thresh


def connected_components(mask):
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    boxes = []
    ys, xs = np.where(mask)
    for start_y, start_x in zip(ys, xs):
        if visited[start_y, start_x]:
            continue
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)
        area = 0

        while stack:
            cy, cx = stack.pop()
            area += 1
            if cx < min_x:
                min_x = cx
            if cx > max_x:
                max_x = cx
            if cy < min_y:
                min_y = cy
            if cy > max_y:
                max_y = cy

            for ny in range(max(0, cy - 1), min(h, cy + 2)):
                for nx in range(max(0, cx - 1), min(w, cx + 2)):
                    if mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))

        if area >= 4:
            boxes.append((min_x, min_y, max_x + 1, max_y + 1))
    return boxes


def merge_vertical_parts(boxes):
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: b[0])
    merged = []
    used = [False] * len(boxes)

    for i, b1 in enumerate(boxes):
        if used[i]:
            continue
        x1, y1, x2, y2 = b1
        w1 = x2 - x1
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j, b2 in enumerate(boxes):
                if used[j]:
                    continue
                ox1, oy1, ox2, oy2 = b2
                w2 = ox2 - ox1
                overlap = min(x2, ox2) - max(x1, ox1)
                min_w = max(1, min(w1, w2))
                if overlap / min_w >= 0.45 and abs((oy1 + oy2) / 2 - (y1 + y2) / 2) < 48:
                    x1 = min(x1, ox1)
                    y1 = min(y1, oy1)
                    x2 = max(x2, ox2)
                    y2 = max(y2, oy2)
                    w1 = x2 - x1
                    used[j] = True
                    changed = True
        merged.append((x1, y1, x2, y2))
    return sorted(merged, key=lambda b: b[0])


def split_into_lines(mask):
    row_counts = mask.sum(axis=1)
    lines = []
    in_line = False
    start_y = 0
    for y, cnt in enumerate(row_counts):
        if cnt > 0 and not in_line:
            in_line = True
            start_y = y
        elif cnt == 0 and in_line:
            if y - start_y >= 5:
                lines.append((start_y, y))
            in_line = False
    if in_line and len(row_counts) - start_y >= 5:
        lines.append((start_y, len(row_counts)))
    return lines


def img_to_base64(pil_img):
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_builtin_templates():
    """Renders standard Windows/Linux sans-serif & serif fonts as 24x24 normalized masks
    so characters get pre-sorted into bins even without Tesseract installed."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?'-:;\"()"
    font_candidates = [
        "arial.ttf", "arialbd.ttf", "ariali.ttf",
        "calibri.ttf", "calibrib.ttf",
        "verdana.ttf", "verdanab.ttf",
        "tahoma.ttf", "tahomabd.ttf",
        "segoeui.ttf", "segoeuib.ttf",
        "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Regular.ttf"
    ]
    fonts = []
    win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    for fname in font_candidates:
        for path in (fname, os.path.join(win_fonts, fname), f"/usr/share/fonts/truetype/dejavu/{fname}"):
            if os.path.isfile(path):
                try:
                    fonts.append(ImageFont.truetype(path, 36))
                    break
                except Exception:
                    pass
    if not fonts:
        fonts.append(ImageFont.load_default())

    templates = []  # (char, 24x24 float32, aspect_ratio)
    for fnt in fonts:
        for ch in chars:
            canvas = Image.new("L", (80, 80), 0)
            draw = ImageDraw.Draw(canvas)
            draw.text((16, 16), ch, fill=255, font=fnt)
            arr = np.array(canvas)
            ys, xs = np.where(arr > 127)
            if len(xs) == 0:
                continue
            crop = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            gh, gw = crop.shape
            aspect = gw / max(1.0, float(gh))
            norm_img = Image.fromarray(crop, "L").resize((24, 24), Image.Resampling.BILINEAR)
            sig = (np.array(norm_img, dtype=np.float32) > 127).astype(np.float32)
            templates.append((ch, sig, aspect))
    return templates



def print_progress(current, total, label="Processing cues"):
    spinner = "|/-\\"[current % 4]
    pct = int((current / max(1, total)) * 100)
    bar_len = 24
    filled = int(bar_len * current / max(1, total))
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\r  [{spinner}] {label}: [{bar}] {pct:3d}% ({current}/{total})")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()


class BinOCRSession:
    def __init__(self, sup_path, session_data=None):
        self.sup_path = sup_path
        self.cues = []
        self.glyphs = {}
        self.clusters = {}
        self.line_spaces = {}
        if session_data is not None:
            self._load_session_dict(session_data)
            return
        if sup_path.lower().endswith(".json"):
            with open(sup_path, "r", encoding="utf-8") as sf:
                self._load_session_dict(json.load(sf))
            return
        print("  [1/3] Building font templates...", end="\r", flush=True)
        self.templates = build_builtin_templates()
        self.tpl_chars = [t[0] for t in self.templates]
        self.tpl_mat = np.stack([t[1].ravel() for t in self.templates], axis=0)
        self.tpl_aspects = np.array([t[2] for t in self.templates], dtype=np.float32)
        print("  [1/3] Font templates ready.        ")
        self._build_from_file()

    def to_session_dict(self):
        return {
            "sup_path": self.sup_path,
            "cues": self.cues,
            "glyphs": self.glyphs,
            "clusters": self.clusters,
            "line_spaces": {f"{k[0]}:{k[1]}": v for k, v in self.line_spaces.items()},
        }

    def _load_session_dict(self, data):
        self.sup_path = data.get("sup_path", self.sup_path)
        self.cues = data["cues"]
        self.glyphs = data["glyphs"]
        self.clusters = data["clusters"]
        self.line_spaces = {
            (int(k.split(":")[0]), int(k.split(":")[1])): v
            for k, v in data.get("line_spaces", {}).items()
        }

    def _normalize_glyph(self, crop_mask):
        img = Image.fromarray((crop_mask * 255).astype(np.uint8), "L")
        img = img.resize((24, 24), Image.Resampling.BILINEAR)
        return (np.array(img, dtype=np.float32) > 127).astype(np.float32)

    def _refine_e_vs_o(self, crop_mask, guess):
        if guess not in ("e", "o", "0"):
            return guess
        h, w = crop_mask.shape
        if h < 6 or w < 5:
            return guess

        # 1. Center hole check: 'o' is hollow in the center; 'e' has a crossbar through the middle
        c_y1, c_y2 = int(h * 0.36), max(int(h * 0.36) + 1, int(h * 0.64))
        c_x1, c_x2 = int(w * 0.32), max(int(w * 0.32) + 1, int(w * 0.68))
        center_ink = float(crop_mask[c_y1:c_y2, c_x1:c_x2].mean())

        # 2. Right-edge lower opening: 'e' opens on the lower-right edge; 'o' has a continuous right wall
        r_edge_low = crop_mask[int(h * 0.52):max(int(h * 0.52) + 1, int(h * 0.80)), int(w * 0.65):]
        r_edge_up = crop_mask[int(h * 0.18):max(int(h * 0.18) + 1, int(h * 0.46)), int(w * 0.65):]
        low_r = float(r_edge_low.mean()) if r_edge_low.size > 0 else 1.0
        up_r = float(r_edge_up.mean()) if r_edge_up.size > 0 else 1.0

        # 3. Top-to-bottom flip asymmetry
        half_h = h // 2
        top_half = crop_mask[:half_h, :].astype(np.float32)
        bot_half = crop_mask[h - half_h:, :][::-1, :].astype(np.float32)
        v_asym = float(np.mean(np.abs(top_half - bot_half)))

        if center_ink >= 0.28 or (up_r - low_r) >= 0.16 or v_asym >= 0.15:
            return "e"
        return "0" if guess == "0" else "o"

    def _guess_single_char(self, crop_mask, sig, aspect):
        if HAS_TESSERACT:
            h, w = crop_mask.shape
            padded = np.zeros((h + 24, w + 24), dtype=np.uint8)
            padded[12:12 + h, 12:12 + w] = (1 - crop_mask.astype(np.uint8)) * 255
            pil_crop = Image.fromarray(padded, "L")
            data = pytesseract.image_to_data(
                pil_crop,
                config="--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?'-:;\"()",
                output_type=pytesseract.Output.DICT,
            )
            for txt, conf in zip(data["text"], data["conf"]):
                txt = txt.strip()
                if len(txt) == 1 and float(conf) >= 82.0:
                    return self._refine_e_vs_o(crop_mask, txt)

        valid_mask = np.abs(self.tpl_aspects - aspect) <= 0.22
        if not np.any(valid_mask):
            return None
        flat = sig.ravel()
        sub_mat = self.tpl_mat[valid_mask]
        dists = np.mean(np.abs(sub_mat - flat), axis=1)
        best_local = int(np.argmin(dists))
        best_dist = float(dists[best_local])
        if best_dist <= 0.24:
            valid_indices = np.where(valid_mask)[0]
            best_char = self.tpl_chars[int(valid_indices[best_local])]
            return self._refine_e_vs_o(crop_mask, best_char)
        return None

    def _build_from_file(self):
        with open(self.sup_path, "rb") as f:
            magic = f.read(4)

        if magic[:2] == b"PG":
            raw_cues = PGSParser().parse_file(self.sup_path)
        else:
            raw_cues = DVDSupParser().parse_file(self.sup_path)

        cluster_mat = None
        cluster_aspects = []
        cluster_parts = []
        cluster_cids = []
        cluster_guess = {}
        gid_counter = 0

        total_cues = len(raw_cues)
        for idx_c, cue in enumerate(raw_cues, 1):
            if idx_c == 1 or idx_c % 5 == 0 or idx_c == total_cues:
                print_progress(idx_c, total_cues, "Segmenting & matching glyphs")
            cue_idx = cue["index"]
            pil_img = cue["image"]
            mask = rgba_to_foreground_mask(pil_img)
            line_spans = split_into_lines(mask)

            self.cues.append({
                "index": cue_idx,
                "start_ms": cue["start_ms"],
                "end_ms": cue["end_ms"],
                "line_count": len(line_spans),
            })

            for line_idx, (ly1, ly2) in enumerate(line_spans):
                line_mask = mask[ly1:ly2, :]
                raw_boxes = connected_components(line_mask)
                boxes = merge_vertical_parts(raw_boxes)
                if not boxes:
                    continue
                line_cap_h = float(max(b[3] - b[1] for b in boxes))

                widths = [b[2] - b[0] for b in boxes]
                median_w = float(np.median(widths)) if widths else 12.0
                gaps = [boxes[i + 1][0] - boxes[i][2] for i in range(len(boxes) - 1)]
                space_thresh = max(median_w * 0.55, 6.0)
                space_xs = [
                    (boxes[i][2] + boxes[i + 1][0]) / 2.0
                    for i, g in enumerate(gaps)
                    if g > space_thresh
                ]
                self.line_spaces[(cue_idx, line_idx)] = space_xs

                for bx1, by1, bx2, by2 in boxes:
                    gid_counter += 1
                    gid = f"g{gid_counter}"
                    gw = bx2 - bx1
                    gh = by2 - by1
                    aspect = gw / max(1.0, float(gh))

                    g_mask = line_mask[by1:by2, bx1:bx2]
                    tight_img = Image.fromarray((g_mask * 255).astype(np.uint8), "L")

                    ctx_x1 = max(0, bx1 - 75)
                    ctx_x2 = min(mask.shape[1], bx2 + 75)
                    ctx_pad_y1 = max(0, ly1 - 4)
                    ctx_pad_y2 = min(mask.shape[0], ly2 + 4)
                    ctx_crop = pil_img.crop((ctx_x1, ctx_pad_y1, ctx_x2, ctx_pad_y2)).convert("RGBA")

                    ctx_arr = np.array(ctx_crop)
                    rel_x1 = bx1 - ctx_x1
                    rel_x2 = bx2 - ctx_x1
                    rel_y1 = (ly1 + by1) - ctx_pad_y1
                    rel_y2 = (ly1 + by2) - ctx_pad_y1
                    amber = np.array((245, 158, 11, 255), dtype=np.uint8)
                    ctx_arr[max(0, rel_y1 - 2):rel_y1, max(0, rel_x1 - 2):min(ctx_arr.shape[1], rel_x2 + 2)] = amber
                    ctx_arr[rel_y2:min(ctx_arr.shape[0], rel_y2 + 2), max(0, rel_x1 - 2):min(ctx_arr.shape[1], rel_x2 + 2)] = amber
                    ctx_img = Image.fromarray(ctx_arr, "RGBA")

                    sig = self._normalize_glyph(g_mask)
                    flat_sig = sig.ravel()
                    matched_cid = None
                    part_cnt = sum(1 for rb in raw_boxes if rb[0] >= bx1 and rb[2] <= bx2)

                    if cluster_mat is not None:
                        c_asp_arr = np.array(cluster_aspects, dtype=np.float32)
                        c_prt_arr = np.array(cluster_parts, dtype=np.int32)
                        cand_idx = np.where((c_prt_arr == part_cnt) & (np.abs(c_asp_arr - aspect) <= 0.14))[0]
                        if cand_idx.size > 0:
                            diffs = np.mean(np.abs(cluster_mat[cand_idx] - flat_sig), axis=1)
                            min_pos = int(np.argmin(diffs))
                            if float(diffs[min_pos]) <= 0.085:
                                matched_cid = cluster_cids[int(cand_idx[min_pos])]

                    is_new_cluster = False
                    if matched_cid is None:
                        is_new_cluster = True
                        matched_cid = f"c{len(cluster_cids) + 1}"
                        cluster_cids.append(matched_cid)
                        cluster_aspects.append(aspect)
                        cluster_parts.append(part_cnt)
                        if cluster_mat is None:
                            cluster_mat = flat_sig.reshape(1, -1)
                        else:
                            cluster_mat = np.vstack([cluster_mat, flat_sig])
                        self.clusters[matched_cid] = []

                    self.clusters[matched_cid].append(gid)

                    is_wide_blob = aspect > 1.38 and gw > median_w * 1.45
                    bin_name = "UNSORTED"
                    line_h = float(max(1, ly2 - ly1))
                    y_center_rel = ((by1 + by2) / 2.0) / line_h
                    is_apostrophe = (
                        (gh / line_cap_h) < 0.58
                        and y_center_rel < 0.48
                        and aspect < 0.85
                    )

                    if not is_wide_blob:
                        if is_apostrophe:
                            bin_name = "'"
                        elif not is_new_cluster and matched_cid in cluster_guess:
                            bin_name = cluster_guess[matched_cid]
                        else:
                            row_has_ink = g_mask.any(axis=1)
                            ink_runs = int(np.sum(row_has_ink[1:] & ~row_has_ink[:-1])) + (1 if row_has_ink[0] else 0)
                            if ink_runs >= 2 and aspect < 0.55 and gh >= 8:
                                bin_name = "i"
                            else:
                                guess = self._guess_single_char(g_mask, sig, aspect)
                                if guess:
                                    bin_name = guess
                            if is_new_cluster and bin_name != "UNSORTED":
                                cluster_guess[matched_cid] = bin_name

                    self.glyphs[gid] = {
                        "id": gid,
                        "cluster": matched_cid,
                        "cue": cue_idx,
                        "line": line_idx,
                        "x": bx1,
                        "w": gw, "h": gh, "cap_h": line_cap_h, "eo_pref": self._refine_e_vs_o(g_mask, "o"),
                        "bin": bin_name,
                        "text": "" if bin_name == "UNSORTED" else bin_name,
                        "tight_b64": img_to_base64(tight_img),
                        "ctx_b64": img_to_base64(ctx_img),
                    }

        print("  [3/3] Running cluster voting & context rules...", end="\r", flush=True)
        for cid, gids in self.clusters.items():
            votes = {}
            for gid in gids:
                b = self.glyphs[gid]["bin"]
                if b != "UNSORTED":
                    votes[b] = votes.get(b, 0) + 1
            if votes:
                winner = max(votes.items(), key=lambda kv: kv[1])[0]
                for gid in gids:
                    if self.glyphs[gid]["bin"] == "UNSORTED":
                        self.glyphs[gid]["bin"] = winner
                        self.glyphs[gid]["text"] = winner


        for gid, g in self.glyphs.items():
            b = g["bin"]
            if len(b) == 1 and b.lower() in "oscvwxz" and g.get("cap_h", 0) > 0:
                ratio = g["h"] / g["cap_h"]
                fixed = b.upper() if ratio >= 0.85 else b.lower()
                g["bin"] = fixed
                g["text"] = fixed


        # Height filter: short x-height glyphs cannot be full-height digit '0'
        for gid, g in self.glyphs.items():
            if g["bin"] == "0" and g.get("cap_h", 0) > 0:
                if (g["h"] / g["cap_h"]) < 0.84:
                    fixed_eo = g.get("eo_pref", "o")
                    g["bin"] = fixed_eo
                    g["text"] = fixed_eo

        # Rescue short top-aligned apostrophes from 'l', 'I', '1', or ','
        for gid, g in self.glyphs.items():
            if g["bin"] in ("l", "I", "1") and g.get("cap_h", 0) > 0:
                if (g["h"] / g["cap_h"]) < 0.58:
                    g["bin"] = "'"
                    g["text"] = "'"

        # Neighbor & word-level context pass (run twice so 'all' / 'Ill' cascade cleanly)
        by_line = {}
        for g in self.glyphs.values():
            by_line.setdefault((g["cue"], g["line"]), []).append(g)

        roman_chars = set("IVX")

        # Global cap-height and ascender-height across the whole subtitle stream
        global_caps = [
            g["h"] for g in self.glyphs.values()
            if len(g["text"]) == 1 and g["text"].isupper() and g["text"] not in ("I", "J", "Q")
        ]
        global_ascs = [
            g["h"] for g in self.glyphs.values()
            if len(g["text"]) == 1 and g["text"] in ("b", "d", "h", "k", "l")
        ]
        global_cap_ref = float(np.median(global_caps)) if global_caps else None
        global_asc_ref = float(np.median(global_ascs)) if global_ascs else None

        for _pass in range(2):
            for (c_idx, l_idx), items in by_line.items():
                items.sort(key=lambda x: x["x"])
                space_xs = sorted(self.line_spaces.get((c_idx, l_idx), []))

                # Compute robust cap height & ascender height on this line (with global fallback)
                alpha_heights = [g["h"] for g in items if g["text"].isalnum()]
                robust_cap_h = float(max(alpha_heights)) if alpha_heights else float(max(g["h"] for g in items))

                cap_heights = [
                    g["h"] for g in items
                    if len(g["text"]) == 1 and g["text"].isupper() and g["text"] not in ("I", "J", "Q")
                ]
                asc_heights = [
                    g["h"] for g in items
                    if len(g["text"]) == 1 and g["text"] in ("b", "d", "h", "k", "l")
                ]
                cap_ref = float(np.median(cap_heights)) if cap_heights else global_cap_ref
                asc_ref = float(np.median(asc_heights)) if asc_heights else global_asc_ref

                # Group items on this line into words separated by space_xs
                words = []
                cur_word = []
                for idx, g in enumerate(items):
                    if idx > 0:
                        px, cx = items[idx - 1]["x"], g["x"]
                        if any(px <= sx <= cx for sx in space_xs):
                            words.append(cur_word)
                            cur_word = []
                    cur_word.append(g)
                if cur_word:
                    words.append(cur_word)

                for word in words:
                    word_texts = [w["text"] for w in word if w["text"]]
                    alpha_texts = [t for t in word_texts if len(t) == 1 and t.isalpha()]
                    has_any_lower = any(t.islower() for t in alpha_texts)
                    other_alpha = [t for t in alpha_texts if t not in ("I", "l")]
                    is_all_caps = (len(other_alpha) >= 1 and all(t.isupper() for t in other_alpha))
                    is_roman = (len(alpha_texts) >= 2 and all(t in roman_chars for t in alpha_texts))

                    for w_idx, g in enumerate(word):
                        b = g["bin"]
                        if b not in ("I", "l", "0", "O", "o"):
                            continue

                        left_ch = word[w_idx - 1]["text"] if w_idx > 0 else ""
                        right_ch = word[w_idx + 1]["text"] if w_idx + 1 < len(word) else ""
                        neighbors = left_ch + right_ch

                        if b in ("I", "l"):
                            if len(word) == 1:
                                g["bin"] = "I"
                                g["text"] = "I"
                            elif is_all_caps or is_roman:
                                g["bin"] = "I"
                                g["text"] = "I"
                            elif w_idx > 0:
                                # Mid-word or end-of-word bar (including any 'll' pair) -> 'l'
                                g["bin"] = "l"
                                g["text"] = "l"
                            elif w_idx == 0 and any(ch.islower() for ch in right_ch):
                                # Build lowercase-normalized suffix of the current word
                                tail = "".join(w["text"] for w in word[1:] if w["text"]).lower()
                                l_tails = {
                                    "et", "ets", "etting", "ike", "ikes", "iked", "iking", "ikely",
                                    "ast", "asts", "asting", "eave", "eaves", "eaving", "eft",
                                    "ong", "onger", "ongest", "ine", "ines", "ined", "ining",
                                    "ook", "ooks", "ooked", "ooking", "ittle", "ife", "ives",
                                    "ove", "oves", "oved", "oving", "ost", "ight", "ights",
                                    "ead", "eads", "eading", "ed", "earn", "earns", "earned",
                                    "ess", "ive", "ived", "iving", "ord", "ords", "aw", "aws",
                                    "and", "ands", "anded", "anding", "ater", "ate", "ately",
                                    "isten", "istens", "istened", "ucky", "uck", "ying", "ie", "ies",
                                    "evel", "evels", "aser", "asers", "ightsaber", "ightsabers",
                                    "egislation", "egislative", "egislature", "egislati",
                                    "ocal", "ocate", "ocated", "ocation", "ock", "ocked", "ocking",
                                    "ose", "oses", "osing", "oud", "ouder", "oudly", "ow", "ower",
                                    "oyal", "oyalty", "eg", "egs", "egion", "essons", "esson",
                                    "etter", "etters", "iar", "iars", "iberty", "imit", "imits",
                                    "ink", "inks", "inked", "ist", "ists", "isted", "oad", "oads"
                                }
                                has_overshoot = (
                                    cap_ref is not None
                                    and asc_ref is not None
                                    and (asc_ref - cap_ref) >= 1.0
                                    and abs(g["h"] - asc_ref) < abs(g["h"] - cap_ref)
                                )
                                if tail in l_tails or has_overshoot:
                                    g["bin"] = "l"
                                    g["text"] = "l"
                                else:
                                    g["bin"] = "I"
                                    g["text"] = "I"

                        elif b in ("0", "O", "o"):
                            if any(ch.isdigit() for ch in neighbors):
                                g["bin"] = "0"
                                g["text"] = "0"
                            elif any(ch.isalpha() for ch in neighbors) or len(word) == 1:
                                ratio = (g["h"] / robust_cap_h) if robust_cap_h > 0 else 0.0
                                # Uppercase 'O' if ALL-CAPS word OR cap-height at start/single-char word ('Or', 'Other')
                                is_upper = is_all_caps or (ratio >= 0.80 and (w_idx == 0 or not has_any_lower))
                                fixed = "O" if is_upper else "o"
                                g["bin"] = fixed
                                g["text"] = fixed

        print("  [3/3] Cluster voting & context rules complete.   ")
    def get_state(self):
        return {
            "filename": os.path.basename(self.sup_path),
            "cue_count": len(self.cues),
            "has_tesseract": HAS_TESSERACT,
            "glyphs": list(self.glyphs.values()),
        }

    def move_glyphs(self, gids, target_bin, custom_text=None, apply_to_cluster=False):
        target_set = set(gids)
        if apply_to_cluster:
            cids = {self.glyphs[g]["cluster"] for g in gids if g in self.glyphs}
            for cid in cids:
                target_set.update(self.clusters.get(cid, []))

        for gid in target_set:
            if gid not in self.glyphs:
                continue
            if target_bin == "SPECIAL":
                self.glyphs[gid]["bin"] = "SPECIAL"
                self.glyphs[gid]["text"] = custom_text if custom_text is not None else ""
            elif target_bin == "DELETE":
                self.glyphs[gid]["bin"] = "DELETED"
                self.glyphs[gid]["text"] = ""
            elif target_bin == "UNSORTED":
                self.glyphs[gid]["bin"] = "UNSORTED"
                self.glyphs[gid]["text"] = ""
            else:
                self.glyphs[gid]["bin"] = target_bin
                self.glyphs[gid]["text"] = target_bin

    def export_srt(self, min_gap_ms=1):
        min_gap_ms = max(0, int(min_gap_ms))

        def fmt_ts(ms):
            ms = max(0, int(ms))
            hrs = ms // 3600000
            ms %= 3600000
            mins = ms // 60000
            ms %= 60000
            secs = ms // 1000
            millis = ms % 1000
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        by_cue_line = {}
        for g in self.glyphs.values():
            if g["bin"] == "DELETED":
                continue
            key = (g["cue"], g["line"])
            by_cue_line.setdefault(key, []).append(g)

        ordered_cues = sorted(self.cues, key=lambda c: (c["start_ms"], c["index"]))
        non_empty = []
        for cue in ordered_cues:
            c_idx = cue["index"]
            lines_out = []
            for l_idx in range(cue["line_count"]):
                items = sorted(by_cue_line.get((c_idx, l_idx), []), key=lambda x: x["x"])
                if not items:
                    continue
                space_xs = sorted(self.line_spaces.get((c_idx, l_idx), []))
                s_ptr = 0
                chars = []
                for idx, item in enumerate(items):
                    if idx > 0:
                        prev_x = items[idx - 1]["x"]
                        cur_x = item["x"]
                        while s_ptr < len(space_xs) and space_xs[s_ptr] < prev_x:
                            s_ptr += 1
                        if s_ptr < len(space_xs) and prev_x <= space_xs[s_ptr] <= cur_x:
                            chars.append(" ")
                            s_ptr += 1
                    token = item["text"] if item["text"] else "?"
                    chars.append(token)
                line_str = "".join(chars).strip()
                if line_str:
                    lines_out.append(line_str)

            if not lines_out:
                continue

            start = max(0, int(cue["start_ms"]))
            end = max(start + 1, int(cue["end_ms"]))
            non_empty.append([start, end, "\n".join(lines_out)])

        for i in range(len(non_empty) - 1):
            next_start = non_empty[i + 1]
            if non_empty[i] > next_start - min_gap_ms:
                non_empty[i] = max(non_empty[i] + 1, next_start - min_gap_ms)

        srt_blocks = []
        for out_idx, (start_ms, end_ms, text_block) in enumerate(non_empty, 1):
            srt_blocks.append(
                f"{out_idx}\n{fmt_ts(start_ms)} --> {fmt_ts(end_ms)}\n{text_block}\n"
            )
        return "\n".join(srt_blocks)


# =====================================================================
# 3. EMBEDDED HTML5 UI & LOCAL HTTP SERVER
# =====================================================================

HTML_UI = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Subtitle Bin OCR Reviewer</title>
<style>
  :root {
    --bg: #121417; --panel: #1b1f24; --border: #2d333b;
    --text: #e6edf3; --muted: #8b949e; --accent: #2f81f7;
    --selected: #f59e0b; --danger: #da3633;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; flex-direction: column; height: 100vh; overflow: hidden;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--border);
    gap: 12px; flex-wrap: wrap;
  }
  .toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  button {
    background: #262c34; color: var(--text); border: 1px solid var(--border);
    padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
  }
  button:hover { background: #323944; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.active-move { background: var(--selected); color: #000; border-color: var(--selected); font-weight: 700; }
  button.danger { border-color: var(--danger); color: #ff7b72; }
  .main { display: flex; flex: 1; overflow: hidden; }
  aside {
    width: 240px; background: var(--panel); border-right: 1px solid var(--border);
    overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 4px;
  }
  .bin-section-title {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); margin: 8px 4px 4px;
  }
  .bin-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 10px; border-radius: 6px; cursor: pointer; font-size: 14px;
  }
  .bin-item:hover { background: #262c34; }
  .bin-item.active { background: var(--accent); color: #fff; font-weight: 600; }
  .bin-badge { font-size: 12px; padding: 1px 7px; border-radius: 10px; background: rgba(255,255,255,0.12); }
  .workspace { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .subbar {
    padding: 8px 16px; background: #16191d; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 13px;
  }
  .grid {
    flex: 1; overflow-y: auto; padding: 16px;
    display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
    gap: 10px; align-content: start;
  }
  .grid.context-mode { grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
  .tile {
    background: #0d1117; border: 2px solid var(--border); border-radius: 8px;
    padding: 8px; display: flex; flex-direction: column; align-items: center;
    justify-content: space-between; cursor: pointer; user-select: none; min-height: 78px;
  }
  .tile:hover { border-color: #58a6ff; }
  .tile.selected { border-color: var(--selected); background: rgba(245, 158, 11, 0.14); }
  .tile img { max-width: 100%; max-height: 44px; image-rendering: pixelated; object-fit: contain; }
  .tile-meta { margin-top: 6px; font-size: 11px; color: var(--muted); display: flex; gap: 6px; }
  .special-tag { color: #d2a8ff; font-weight: 700; font-family: monospace; font-size: 12px; }
  dialog {
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px; width: 420px; max-width: 92vw;
  }
  dialog::backdrop { background: rgba(0, 0, 0, 0.72); }
  .dialog-preview {
    background: #0d1117; border: 1px solid var(--border); border-radius: 8px;
    padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 10px; margin: 12px 0;
  }
  .dialog-preview img { max-height: 64px; image-rendering: pixelated; }
  input[type="text"] {
    width: 100%; padding: 9px 12px; font-size: 16px; border-radius: 6px;
    border: 1px solid var(--border); background: #0d1117; color: var(--text);
  }
  .dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
  label.chk { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; }
</style>
</head>
<body>

<header>
  <div>
    <strong id="fileTitle">Subtitle Bin OCR</strong>
    <span id="statsText" style="color:var(--muted); font-size:13px; margin-left:8px;"></span>
  </div>
  <div class="toolbar">
    <button id="moveToBtn" onclick="armMoveMode()">Move To [Press Key]</button>
    <button onclick="openSpecialDialog()">Assign Text / Multi-Char (Enter)</button>
    <button onclick="selectAllVisible()">Select All</button>
    <button onclick="clearSelection()">Clear Selection</button>
    <button class="danger" onclick="deleteSelected()">Ignore / Delete</button>
    <input type="file" id="fileLoader" accept=".sup,.sub,.json" style="display:none" onchange="uploadSubtitleFile(this)">
    <button onclick="document.getElementById('fileLoader').click()">Open File</button>
    <button onclick="saveSession()">Save Session</button>
    <label style="display:flex; align-items:center; gap:4px; font-size:12px; color:var(--muted);" title="Minimum gap in milliseconds between consecutive cues">
      Gap (ms):
      <input type="number" id="minGapInput" value="1" min="0" max="5000" style="width:58px; padding:4px 6px; font-size:12px; border-radius:6px; border:1px solid var(--border); background:#0d1117; color:var(--text);">
    </label>
    <button class="primary" onclick="exportSRT()">Export SRT</button>
  </div>
</header>

<div class="main">
  <aside id="binSidebar"></aside>
  <div class="workspace">
    <div class="subbar">
      <div>
        <strong id="currentBinLabel">Bin: UNSORTED</strong>
        <span id="selectionCount" style="color:var(--selected); margin-left:10px;"></span>
      </div>
      <div class="toolbar">
        <label class="chk">
          <input type="checkbox" id="contextToggle" onchange="renderGrid()">
          Context Mode (Show Neighboring Letters)
        </label>
        <label class="chk">
          <input type="checkbox" id="clusterToggle" checked>
          Apply Moves to Entire Identical Cluster
        </label>
      </div>
    </div>
    <div id="glyphGrid" class="grid"></div>
  </div>
</div>

<dialog id="specialDialog">
  <h3 style="margin:0 0 6px;">Assign Multi-Character / Custom Text</h3>
  <div style="font-size:13px; color:var(--muted);">
    Type the letters for this glyph or merged pair (e.g. <code>rn</code>, <code>fl</code>, <code>tt</code>) and press <strong>Enter</strong>.
  </div>
  <div class="dialog-preview">
    <img id="dlgTightImg" alt="Glyph">
    <img id="dlgCtxImg" alt="Context">
  </div>
  <input type="text" id="specialInput" placeholder="Type characters and press Enter..." autocomplete="off">
  <div class="dialog-actions">
    <button onclick="closeSpecialDialog()">Cancel (Esc)</button>
    <button class="primary" onclick="submitSpecialDialog()">Save to Special Cases (Enter)</button>
  </div>
</dialog>

<script>
const AMBIGUOUS_BINS = new Set(["I", "l", "1", "O", "o", "0", "S", "s", "5", "Z", "2", "m"]);
const BIN_LABELS = {
  "I": 'Uppercase I ("I")', "l": 'Lowercase l ("l")', "1": 'Digit 1 ("1")',
  "O": 'Uppercase O ("O")', "o": 'Lowercase o ("o")', "0": 'Digit 0 ("0")',
  "S": 'Uppercase S ("S")', "s": 'Lowercase s ("s")', "m": 'Lowercase m / rn ("m")'
};
let allGlyphs = [];
let currentBin = "UNSORTED";
let selectedIds = new Set();
let moveModeArmed = false;
let dialogTargetIds = [];

async function loadState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  allGlyphs = data.glyphs;
  document.getElementById("fileTitle").textContent = data.filename;
  document.getElementById("statsText").textContent =
    `${data.cue_count} cues • ${allGlyphs.length} glyphs • Auto-presorted`;
  renderSidebar();
  selectBin(currentBin);
}

function getBinCounts() {
  const counts = { UNSORTED: 0, SPECIAL: 0 };
  for (const g of allGlyphs) {
    if (g.bin === "DELETED") continue;
    counts[g.bin] = (counts[g.bin] || 0) + 1;
  }
  return counts;
}

function renderSidebar() {
  const sidebar = document.getElementById("binSidebar");
  const counts = getBinCounts();
  sidebar.innerHTML = "";

  const addSection = (title) => {
    const el = document.createElement("div");
    el.className = "bin-section-title";
    el.textContent = title;
    sidebar.appendChild(el);
  };

  const addBinItem = (binKey, label) => {
    const item = document.createElement("div");
    item.className = "bin-item" + (currentBin === binKey ? " active" : "");
    item.onclick = () => selectBin(binKey);
    item.innerHTML = `<span>${label}</span><span class="bin-badge">${counts[binKey] || 0}</span>`;
    sidebar.appendChild(item);
  };

  addSection("Review Queues");
  addBinItem("UNSORTED", "Unsorted / Blobs");
  addBinItem("SPECIAL", "Special Cases");

  addSection("Ambiguous Lookalikes");
  ["I", "l", "1", "O", "o", "0", "S", "s", "m"].forEach(ch => {
    if (counts[ch] > 0 || ["I", "l", "O", "o", "0", "S", "s", "m"].includes(ch)) {
      addBinItem(ch, BIN_LABELS[ch] || `Char: "${ch}"`);
    }
  });

  addSection("Character Bins");
  const otherKeys = Object.keys(counts)
    .filter(k => !["UNSORTED", "SPECIAL", "DELETED", "I", "l", "1", "O", "o", "0", "S", "s", "m"].includes(k))
    .sort();
  otherKeys.forEach(ch => addBinItem(ch, `Char: "${ch}"`));
}

function selectBin(binKey) {
  currentBin = binKey;
  selectedIds.clear();
  disarmMoveMode();
  document.getElementById("contextToggle").checked =
    AMBIGUOUS_BINS.has(binKey) || binKey === "UNSORTED";
  document.getElementById("clusterToggle").checked = (binKey === "UNSORTED");
  document.getElementById("currentBinLabel").textContent = `Bin: ${BIN_LABELS[binKey] || binKey}`;
  renderSidebar();
  renderGrid();
}

function renderGrid() {
  const grid = document.getElementById("glyphGrid");
  const ctxMode = document.getElementById("contextToggle").checked;
  grid.className = "grid" + (ctxMode ? " context-mode" : "");
  grid.innerHTML = "";

  const items = allGlyphs.filter(g => g.bin === currentBin);
  document.getElementById("selectionCount").textContent =
    selectedIds.size > 0 ? `${selectedIds.size} selected` : "";

  for (const g of items) {
    const tile = document.createElement("div");
    tile.className = "tile" + (selectedIds.has(g.id) ? " selected" : "");
    tile.onclick = () => {
      if (currentBin === "UNSORTED" && selectedIds.size === 0) {
        openSpecialDialog([g.id]);
        return;
      }
      if (selectedIds.has(g.id)) {
        selectedIds.delete(g.id);
      } else {
        selectedIds.add(g.id);
      }
      renderGrid();
    };

    const img = document.createElement("img");
    img.src = ctxMode ? g.ctx_b64 : g.tight_b64;
    tile.appendChild(img);

    const meta = document.createElement("div");
    meta.className = "tile-meta";
    if (g.bin === "SPECIAL") {
      meta.innerHTML = `<span class="special-tag">"${escapeHtml(g.text)}"</span> • #${g.cue}`;
    } else {
      meta.textContent = `Cue #${g.cue}`;
    }
    tile.appendChild(meta);
    grid.appendChild(tile);
  }
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[m]));
}

function selectAllVisible() {
  allGlyphs.filter(g => g.bin === currentBin).forEach(g => selectedIds.add(g.id));
  renderGrid();
}

function clearSelection() {
  selectedIds.clear();
  disarmMoveMode();
  renderGrid();
}

function armMoveMode() {
  if (selectedIds.size === 0) {
    alert("Click one or more glyph tiles first to select them.");
    return;
  }
  moveModeArmed = true;
  const btn = document.getElementById("moveToBtn");
  btn.classList.add("active-move");
  btn.textContent = "Press target character key now...";
}

function disarmMoveMode() {
  moveModeArmed = false;
  const btn = document.getElementById("moveToBtn");
  btn.classList.remove("active-move");
  btn.textContent = "Move To [Press Key]";
}

async function performMove(targetBin, customText = null) {
  const gids = Array.from(selectedIds);
  if (gids.length === 0) return;
  const applyCluster = document.getElementById("clusterToggle").checked;

  await fetch("/api/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      gids,
      target_bin: targetBin,
      custom_text: customText,
      apply_to_cluster: applyCluster
    })
  });
  selectedIds.clear();
  disarmMoveMode();
  await loadState();
}

function deleteSelected() {
  if (selectedIds.size === 0) return;
  performMove("DELETE");
}

function openSpecialDialog(overrideIds = null) {
  const ids = overrideIds || Array.from(selectedIds);
  if (ids.length === 0) {
    alert("Click a glyph or select tiles first.");
    return;
  }
  dialogTargetIds = ids;
  const sample = allGlyphs.find(g => g.id === ids[0]);
  document.getElementById("dlgTightImg").src = sample.tight_b64;
  document.getElementById("dlgCtxImg").src = sample.ctx_b64;
  const inp = document.getElementById("specialInput");
  inp.value = sample.bin === "SPECIAL" ? sample.text : "";
  document.getElementById("specialDialog").showModal();
  inp.focus();
  inp.select();
}

function closeSpecialDialog() {
  document.getElementById("specialDialog").close();
}

async function submitSpecialDialog() {
  const val = document.getElementById("specialInput").value;
  if (!val) return;
  closeSpecialDialog();
  const applyCluster = document.getElementById("clusterToggle").checked;
  await fetch("/api/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      gids: dialogTargetIds,
      target_bin: val.length === 1 ? val : "SPECIAL",
      custom_text: val,
      apply_to_cluster: applyCluster
    })
  });
  selectedIds.clear();
  await loadState();
}

document.getElementById("specialInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    submitSpecialDialog();
  }
});

document.addEventListener("keydown", (e) => {
  if (document.getElementById("specialDialog").open) return;

  if (moveModeArmed) {
    if (e.key === "Escape") {
      disarmMoveMode();
      return;
    }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      performMove(e.key);
    }
    return;
  }

  if (e.key === "Enter" && selectedIds.size > 0) {
    e.preventDefault();
    openSpecialDialog();
  } else if (e.key === "Escape") {
    clearSelection();
  }
});

async function exportSRT() {
  const gapVal = Math.max(0, parseInt(document.getElementById("minGapInput").value, 10) || 0);
  const res = await fetch(`/api/export_srt?min_gap=${gapVal}`);
  if (res.ok) {
    const data = await res.json();
    alert("SRT exported to:\n" + data.saved_path);
  } else {
    alert("Failed to export SRT.");
  }
}

async function saveSession() {
  const res = await fetch("/api/save_session");
  if (res.ok) {
    const data = await res.json();
    alert("Session saved to:\n" + data.saved_path);
  } else {
    alert("Failed to save session.");
  }
}

async function uploadSubtitleFile(inputEl) {
  const file = inputEl.files[0];
  if (!file) return;
  document.getElementById("statsText").textContent = `Loading ${file.name}...`;
  const res = await fetch("/api/load_file", {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file
  });
  inputEl.value = "";
  if (res.ok) {
    currentBin = "UNSORTED";
    selectedIds.clear();
    await loadState();
  } else {
    alert("Failed to load file.");
  }
}

loadState();
</script>
</body>
</html>
"""

SESSION = None


class OCRRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML_UI.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/state":
            self._send_json(SESSION.get_state())
        elif parsed.path == "/api/save_session":
            script_dir = os.path.dirname(os.path.abspath(__file__))
            out_name = os.path.splitext(os.path.basename(SESSION.sup_path))[0] + ".ocr_session.json"
            out_path = os.path.join(script_dir, out_name)
            with open(out_path, "w", encoding="utf-8") as sf:
                json.dump(SESSION.to_session_dict(), sf)
            self._send_json({"ok": True, "saved_path": out_path})
        elif parsed.path == "/api/export_srt":
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            try:
                min_gap = max(0, int(qs.get("min_gap", ["1"])[0]))
            except ValueError:
                min_gap = 1
            script_dir = os.path.dirname(os.path.abspath(__file__))
            out_name = os.path.splitext(os.path.basename(SESSION.sup_path))[0] + ".srt"
            out_path = os.path.join(script_dir, out_name)
            with open(out_path, "w", encoding="utf-8") as srt_f:
                srt_f.write(SESSION.export_srt(min_gap_ms=min_gap))
            self._send_json({"ok": True, "saved_path": out_path})
        else:
            self.send_error(404)

    def do_POST(self):
        global SESSION
        parsed = urlparse(self.path)
        if parsed.path == "/api/move":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            SESSION.move_glyphs(
                gids=data.get("gids", []),
                target_bin=data.get("target_bin", "UNSORTED"),
                custom_text=data.get("custom_text"),
                apply_to_cluster=data.get("apply_to_cluster", False),
            )
            self._send_json({"ok": True})
        elif parsed.path == "/api/load_file":
            from urllib.parse import unquote
            length = int(self.headers.get("Content-Length", 0))
            raw_bytes = self.rfile.read(length)
            fname = unquote(self.headers.get("X-Filename", "uploaded.sup"))
            print(f"\nLoading from browser: {fname} ...")
            if fname.lower().endswith(".json"):
                SESSION = BinOCRSession(fname, session_data=json.loads(raw_bytes.decode("utf-8")))
            else:
                tmp_path = os.path.join(tempfile.gettempdir(), fname)
                with open(tmp_path, "wb") as tf:
                    tf.write(raw_bytes)
                SESSION = BinOCRSession(tmp_path)
            print(f"Loaded {len(SESSION.cues)} cues and {len(SESSION.glyphs)} glyphs.")
            self._send_json({"ok": True})
        else:
            self.send_error(404)


def pick_sup_file():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(
        title="Select DVD (.sup / .sub) or Blu-ray PGS (.sup) Subtitle File",
        filetypes=[("Subtitles & OCR Sessions", "*.sup *.sub *.json"), ("All Files", "*.*")],
    )


def main():
    global SESSION
    try:
        sup_path = sys.argv[1] if len(sys.argv) >= 2 else pick_sup_file()
        if not sup_path or not os.path.isfile(sup_path):
            print("No valid subtitle file selected.")
            input("Press Enter to exit...")
            sys.exit(1)

        print(f"Parsing subtitle stream and clustering glyphs from: {sup_path} ...")
        SESSION = BinOCRSession(sup_path)
        print(f"Loaded {len(SESSION.cues)} cues and {len(SESSION.glyphs)} glyphs.")

        server = ThreadingHTTPServer(("127.0.0.1", 0), OCRRequestHandler)
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/"
        print(f"Opening reviewer at {url} (Press Ctrl+C or close window to quit)")
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    except Exception:
        import traceback
        traceback.print_exc()
        input("\nError occurred. Press Enter to exit...")


if __name__ == "__main__":
    main()
