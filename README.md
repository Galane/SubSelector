# SubSelector
Rapid visual subtitle OCR in HTML5
# SubSelector

**Rapid visual subtitle OCR in HTML5**

![SubSelector Interface Screenshot](SubSelector.jpg)

## What Is SubSelector?

SubSelector is a visual Optical Character Recognition (OCR) tool designed for **DVD (`.sup` / `.sub`)** and **Blu-ray PGS (`.sup`)** bitmap subtitles, scanning entire files, grouping character shapes into visual bins, and opening an interactive web browser grid for batch review and editing [SubSelector.jpg].

---

## Supported Source Subtitle Formats

SubSelector reads raw bitmap streams and saved session files directly without requiring external `.idx` or `.ifo` color files [SubSelector.jpg]:
1. **Raw DVD SubPicture Streams (`.sup`)** (90 kHz timestamped tracks from tools like IFOEdit or PGCdemux) [SubSelector.jpg]
2. **DVD VobSub Streams (`.sub`)** (MPEG-2 Program Stream SubPicture packets) [SubSelector.jpg]
3. **Blu-ray Presentation Graphic Stream (`.sup`)** (High-definition Blu-ray PGS streams) [SubSelector.jpg]
4. **Saved SubSelector Sessions (`.ocr_session.json`)** (Resume files from previous sessions) [SubSelector.jpg]

> **Note:** SubSelector works on image/bitmap subtitle files only; text-based formats like `.srt` or `.vtt` are unsupported [SubSelector.jpg].

---

## System Requirements

SubSelector runs across Windows, Linux, macOS, and legacy environments requiring [SubSelector.jpg]:
1. **Python 3.6+** (with optional `tkinter` for graphical file pickers) [SubSelector.jpg]
2. **Required Libraries:** `numpy` and `Pillow` (`PIL`) [SubSelector.jpg]
3. **HTML5-Capable Web Browser** (Chrome 57+, Edge 79+, Firefox 98+, or Safari 15.4+) [SubSelector.jpg]
4. **Hardware:** Adequate CPU speed for ~20,000–35,000 glyphs and 250–500 MB of free RAM [SubSelector.jpg]

---

## Part 1: Installation Guide

Install Python 3 along with `numpy` and `Pillow` across platforms [SubSelector.jpg]:
* **Windows:** Install Python from [python.org](https://python.org) (checking `Add python.exe to PATH`), then run `python -m pip install numpy pillow` in Command Prompt before launching `SubSelector.py` [SubSelector.jpg].
* **Linux:** Install via package manager (e.g., `sudo apt install python3 python3-tk python3-numpy python3-pil` on Ubuntu/Debian) and run `python3 SubSelector.py` [SubSelector.jpg].
* **macOS:** Install the universal2 Python installer from [python.org](https://python.orgdownloads/macos/), install libraries via `python3 -m pip install numpy pillow`, and execute `python3 SubSelector.py` [SubSelector.jpg].
* **PowerPC Mac OS X 10.5.8:** Compile Python 3.6, NumPy, and Pillow from source via MacPorts (`sudo port install python36 py36-tkinter py36-numpy py36-pillow`) [SubSelector.jpg].

---

## Part 2: How to Use the SubSelector Interface

Launching `SubSelector.py` processes subtitle images with a live terminal progress bar and opens a local browser interface (keep the terminal window open during use) [SubSelector.jpg].

### Screen Layout & Workflow
* **Top Toolbar:** Includes tools to reassign selected tiles (`Move To [Press Key]`), assign multi-character text (`Assign Text / Multi-Char`), select/clear tiles, ignore noise (`Ignore / Delete`), load files (`Open File`), save progress (`Save Session`), and export `.srt` files (`Export SRT`) [SubSelector.jpg].
* **Left Sidebar:** Organizes glyphs into `Unsorted / Blobs`, `Special Cases`, `Ambiguous Lookalikes`, and standard `Character Bins` [SubSelector.jpg].
* **Sub-Bar Options:** Toggle **Context Mode** (viewing surrounding word context with amber highlights) and **Apply Moves to Entire Identical Cluster** (propagating edits across matching glyphs) [SubSelector.jpg].
* **Step-by-Step Process:**
  1. **Unsorted / Blobs:** Resolve touching/bleeding letters (`rn`, `fl`) or noise [SubSelector.jpg].
  2. **Ambiguous Lookalikes:** Inspect lookalike pairs (`I` vs `l` vs `1`; `O` vs `o` vs `0`; `S` vs `s`; `m` vs `rn`) using Context Mode [SubSelector.jpg].
  3. **Character Bins & Export:** Spot-check remaining letter bins, save your session to `.ocr_session.json`, and export the final `.srt` file [SubSelector.jpg].

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| **Click Tile** | Toggle selection on/off (or open text dialog in `Unsorted / Blobs`) [SubSelector.jpg] |
| **Move To + `[Any Key]`** | Move all selected tiles to that character's bin [SubSelector.jpg] |
| **`Enter` (with selection)** | Open the Assign Text / Multi-Char dialog [SubSelector.jpg] |
| **`Enter` (inside dialog)** | Save typed text to Special Cases and close dialog [SubSelector.jpg] |
| **`Escape`** | Cancel Move To mode, close dialog, or clear selection [SubSelector.jpg] |

---

## Non-English Latin Languages

Supports accented and diacritic characters out of the box (`é`, `à`, `ü`, `ñ`, `ç`, `ø`, `ß`, `ł`, etc.); see `NON_ENGLISH_LATIN_GUIDE.txt` for configuration details [SubSelector.jpg].

## License

Licensed under the [GNU General Public License v3.0](LICENSE) [SubSelector.jpg].
