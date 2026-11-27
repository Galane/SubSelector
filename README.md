# SubSelector
Rapid visual subtitle OCR in HTML5
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
