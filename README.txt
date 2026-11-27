================================================================================
SubSelector.py - Visual Bin-Based Subtitle OCR Reviewer
================================================================================

WHAT IS SUBSELECTOR?
--------------------
SubSelector is a visual Optical Character Recognition (OCR) tool designed for
DVD (.sup / .sub) and Blu-ray PGS (.sup) bitmap subtitles.

Traditional subtitle OCR programs stop and ask you to type characters one line
at a time, or silently misread similar-looking letters (such as confusing "h"
with "b", "I" with "l", or "m" with "rn"). SubSelector scans the entire subtitle
file first, groups matching character shapes into visual bins, and opens an
interactive grid in your web browser so you can review and fix hundreds of
characters at once.

SUPPORTED SOURCE SUBTITLE FORMATS
---------------------------------
SubSelector reads the following bitmap subtitle and session file types directly
(no companion .idx or .ifo color files are required):

  1. Raw DVD SubPicture Streams (.sup)
       - Demuxed DVD subtitle tracks with embedded "SP" headers and 90 kHz
         timestamps (created by tools such as IFOEdit, ProjectX, PGCdemux,
         or DVD Decrypter).
  2. DVD VobSub Streams (.sub)
       - MPEG-2 Program Stream SubPicture packets (.sub), with or without a
         matching .idx file.
  3. Blu-ray Presentation Graphic Stream (.sup)
       - High-definition Blu-ray PGS subtitle streams ("PG" packet headers).
  4. Saved SubSelector Sessions (.ocr_session.json)
       - Resume files saved from a previous SubSelector session.

Note: SubSelector works on image/bitmap subtitle files only. Text-based
subtitles (such as .srt, .ass, .ssa, or .vtt) do not contain images to OCR.

SYSTEM REQUIREMENTS
-------------------
SubSelector will run on virtually any computer (Windows, Linux, macOS, or
older/alternative platforms) that meets these four basic requirements:

  1. Python 3
       - Python 3.6 or newer.
       - Optional: "tkinter" (included with standard Windows/macOS installers;
         available as python3-tk on Linux) if you want the pop-up file picker
         when launching without a filename. (You can also pass a filename on
         the command line or use the "Open File" button in the browser.)

  2. Required Python Libraries
       - numpy and Pillow (PIL) installed via pip, your Linux package manager,
         or compiled from source.

  3. HTML5-Capable Web Browser
       - Any modern browser supporting HTML5 (<dialog>), CSS Grid, and ES2017
         JavaScript (Chrome 57+, Edge 79+, Firefox 98+, Safari 15.4+, or
         equivalent).

  4. Hardware (CPU & Memory)
       - Enough CPU speed to segment and match ~20,000-35,000 character glyphs
         in a reasonable time (a few seconds on modern PCs; longer on older or
         low-power processors).
       - At least 250-500 MB of free RAM to hold decoded subtitle bitmaps and
         glyph thumbnails in memory during a session.

================================================================================
PART 1: INSTALLATION GUIDE (BEGINNER-FRIENDLY)
================================================================================

SubSelector runs on Python 3 and uses two free add-on libraries:
  1. numpy   (fast image math and shape matching)
  2. Pillow  (reading and rendering subtitle character images)

Choose your operating system below and follow the steps in order.


--------------------------------------------------------------------------------
1. WINDOWS (Windows 10 / Windows 11)
--------------------------------------------------------------------------------
Windows does not come with Python pre-installed.

Step 1: Download Python
  - Open your web browser and go to: https://www.python.org/downloads/
  - Click the yellow "Download Python" button to save the installer.

Step 2: Install Python
  - Double-click the downloaded installer file.
  - IMPORTANT: At the very bottom of the first installer window, check the box
    that says:  [X] Add python.exe to PATH
  - Click "Install Now" and wait for it to finish, then close the installer.

Step 3: Open Command Prompt
  - Hold down the Windows key on your keyboard and press R (Win + R).
  - Type:  cmd
  - Press Enter. A black Command Prompt window will open.

Step 4: Install the Required Libraries
  - In the Command Prompt window, type the following command exactly and press
    Enter:

        python -m pip install numpy pillow

  - Wait until it finishes downloading and says "Successfully installed".
    (Note: If Windows says "Defaulting to user installation because normal
    site-packages is not writeable", that is completely normal and works fine.)

Step 5: Run SubSelector
  - You can run SubSelector in any of three ways:
      a) Double-click SubSelector.py in File Explorer. A file-picker window
         will open so you can choose your subtitle file.
      b) In Command Prompt, type:
             python "C:\path\to\SubSelector.py" "C:\path\to\movie.sup"
         (Tip: Type python followed by a space, drag SubSelector.py into the
         Command Prompt window, type a space, drag your .sup file in, and press
         Enter.)


--------------------------------------------------------------------------------
2. LINUX (Ubuntu, Debian, Linux Mint, Fedora, Arch)
--------------------------------------------------------------------------------
Most Linux distributions include Python 3, but you may need to install pip,
tkinter (for the file-picker window), numpy, and Pillow. Using your system's
package manager is the easiest method.

Ubuntu / Debian / Linux Mint:
  1. Open Terminal.
  2. Run this command and enter your password when prompted:

         sudo apt update && sudo apt install -y python3 python3-tk python3-numpy python3-pil

  3. Run SubSelector:

         python3 SubSelector.py

Fedora:
  1. Open Terminal and run:

         sudo dnf install -y python3 python3-tkinter python3-numpy python3-pillow

  2. Run SubSelector:

         python3 SubSelector.py

Arch Linux:
  1. Open Terminal and run:

         sudo pacman -S python tk python-numpy python-pillow

  2. Run SubSelector:

         python3 SubSelector.py


--------------------------------------------------------------------------------
3. MACINTOSH (Apple Silicon M1/M2/M3/M4 & Intel Macs)
--------------------------------------------------------------------------------
Modern macOS does not include Python 3 pre-installed. Using the official
installer from python.org is recommended because it includes the window toolkit
(tkinter) needed for the file-picker dialog.

Step 1: Download and Install Python
  - Go to: https://www.python.org/downloads/macos/
  - Download the "macOS universal2 installer" (.pkg file), which works on both
    Apple Silicon and Intel Macs.
  - Double-click the downloaded .pkg file and follow the on-screen prompts.

Step 2: Open Terminal
  - Press Command + Spacebar on your keyboard to open Spotlight Search.
  - Type:  Terminal
  - Press Enter.

Step 3: Install the Required Libraries
  - In Terminal, type the following command and press Enter:

        python3 -m pip install numpy pillow

Step 4: Run SubSelector
  - In Terminal, type:  python3   (with a space after it)
  - Drag SubSelector.py from Finder into the Terminal window, then press Enter.


--------------------------------------------------------------------------------
4. MAC OS X (PowerPC G4 / G5 - OS X 10.5.8 Leopard)
--------------------------------------------------------------------------------
PowerPC Macs include only outdated Python 2.x and cannot use modern prebuilt
pip downloads, so Python 3 and the libraries must be compiled using MacPorts.

Step 1: Install Xcode 3.1.4
  - Install Xcode 3.1.4 Developer Tools for Mac OS X 10.5.8 so the C/C++
    compilers are available.

Step 2: Install MacPorts
  - Download and install the MacPorts package for OS X 10.5 Leopard from:
    https://www.macports.org/install.php

Step 3: Compile Python 3.6, NumPy, and Pillow
  - Open Terminal and run:

        sudo port install python36 py36-tkinter py36-numpy py36-pillow

  - Note: Compiling numpy from source on a G4 or G5 Mac can take 30 to 60+
    minutes.

Step 4: Run SubSelector
  - Run:

        python3.6 SubSelector.py movie.sup


================================================================================
PART 2: HOW TO USE THE SUBSELECTOR INTERFACE
================================================================================

When you launch SubSelector.py and select a subtitle file (.sup or .sub), it
processes the images in your terminal window (showing a live progress bar) and
automatically opens the reviewer interface in your default web browser.

Keep the terminal/Command Prompt window open while you work; closing it stops
the local server.


1. SCREEN LAYOUT
----------------
  - Top Toolbar:
      * Move To [Press Key]          Reassign selected tiles to a character.
      * Assign Text / Multi-Char     Type 1 or more letters for selected tiles.
      * Select All / Clear Selection Select or deselect all tiles in view.
      * Ignore / Delete              Remove stray speckles or noise from output.
      * Open File                    Load a .sup, .sub, or saved .json session.
      * Save Session                 Save your work to resume later.
      * Export SRT                   Generate and download the finished .srt.

  - Left Sidebar (Bins):
      * Review Queues: "Unsorted / Blobs" and "Special Cases".
      * Ambiguous Lookalikes: Characters that easily confuse OCR or human eyes.
      * Character Bins: Every standard letter, number, and punctuation mark.

  - Sub-Bar Options:
      * Context Mode (Show Neighboring Letters): Displays each character inside
        a wider strip of its surrounding word, with an amber highlight above and
        below the target character.
      * Apply Moves to Entire Identical Cluster: When checked, moving one tile
        also moves every pixel-identical copy of that glyph across the entire
        movie.


2. STEP-BY-STEP WORKFLOW
------------------------

STEP A: Sort Out "Unsorted / Blobs" First
  Why characters land here:
  In DVD subtitles, adjacent letters often touch or bleed together (such as
  "rn", "fl", "fi", "tt", "lo", or italicized pairs), or a character may be too
  degraded for automatic matching.

  How to sort them:
  1. Click "Unsorted / Blobs" at the top of the left sidebar.
  2. Notice that "Apply Moves to Entire Identical Cluster" is checked
     automatically in this bin.
  3. Click any single tile in the grid. A pop-up dialog opens showing the
     isolated shape at the top and the surrounding word context below it.
  4. Type the exact letter or multi-character pair (for example: rn, fl, tt)
     and press Enter.
  5. SubSelector saves that text to "Special Cases" and automatically moves
     every identical copy of that blob across the entire subtitle file at once.
  6. If a tile is just random video noise or a stray speck, click it to select
     it (or select multiple tiles) and click "Ignore / Delete".

  Tip: If you select multiple tiles first in Unsorted / Blobs, pressing Enter
  on your keyboard opens the same text dialog for all selected tiles.


STEP B: Review "Ambiguous Lookalikes"
  Even good OCR engines confuse characters with similar shapes. SubSelector
  groups the trickiest English lookalikes near the top of the sidebar and turns
  on Context Mode automatically so you can see neighboring letters:

  - Uppercase I ("I") vs. Lowercase l ("l") vs. Digit 1 ("1"):
      In sans-serif subtitle fonts, capital I and lowercase l are often
      identical vertical bars. SubSelector uses word position, capitalization,
      and common English prefixes to pre-sort most of them, leaving edge cases
      for you to inspect in Context Mode.
      * Scan the grid using the surrounding word context.
      * Click any misplaced tiles (no need to hold Ctrl or Shift; clicking
        toggles selection on and off).
      * Click "Move To [Press Key]" and press the correct key on your keyboard
        (for example, press l to send misplaced bars to Lowercase l).
      * Uppercase O ("O") vs. Lowercase o ("o") vs. Digit 0 ("0"):
        SubSelector separates these using character height relative to the line
        and neighboring letters/numbers. Check each bin for tall capital O's
        that slipped into Lowercase o (or vice versa), click the outliers, click
        "Move To [Press Key]", and press O, o, or 0.
      * Uppercase S ("S") vs. Lowercase s ("s"):
        Check for capital S's at the start of sentences or all-caps words that
        landed in Lowercase s, or short lowercase s's in Uppercase S.
      * Lowercase m / rn ("m"):
        Sometimes "r" and "n" touch so tightly that the OCR reads "rn" as a single
        "m" (turning "burn" into "bum" or "modern" into "modem").
	* Scan the "m" bin in Context Mode.
	* If you spot a merged "rn" sitting in the "m" bin, click it, press Enter
          (or click "Assign Text / Multi-Char"), type rn, and press Enter. It
          will move to Special Cases and output "rn" in the final SRT.

Important Note on Cluster Moves in Character Bins:
When you open any bin other than "Unsorted / Blobs", "Apply Moves to Entire
Identical Cluster" is unchecked by default. This prevents a single outlier
fix from accidentally dragging other valid letters along with it. If you want
to move all identical copies at once while inside a character bin, simply
check that box first.

STEP C: Quick Scan of Remaining Character Bins
      * Non-AI binary OCR frequently confuses "h" and "b", or "H" and "M".
      * Click through the remaining Character Bins in the sidebar (especially h, b,
        H, M, c, e, a, n, r).
      * Because every tile in a bin is supposed to be the exact same letter, any
        straggler stands out immediately.
      * Click any stragglers, click "Move To [Press Key]", and press the right key.
STEP D: Saving Sessions and Exporting Your SRT
      * Save Session: Click "Save Session" at any time to save a
        ".ocr_session.json" file directly into the same folder as SubSelector.py.
        This file contains all extracted glyph images, clusters, and your sorting
        progress. To resume later, launch SubSelector and click "Open File" (or
        select the .json file at startup).
      * Export SRT: When you are finished sorting, click "Export SRT" to save the
        completed ".srt" subtitle file (with original timestamps and spacing)
        directly into the same folder as SubSelector.py

================================================================================
KEYBOARD SHORTCUTS SUMMARY

Click Tile              Toggle selection on/off (or open dialog in Unsorted)
Move To + [Any Key]     Move all selected tiles to that character's bin
Enter (with selection)  Open the Assign Text / Multi-Char dialog
Enter (inside dialog)   Save typed text to Special Cases and close dialog
Escape                  Cancel Move To mode, close dialog, or clear selection
