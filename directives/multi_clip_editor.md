# Multi-Clip Video Editor

Automatically merge multiple video clips and remove silence using neural voice activity detection (Silero VAD).

Perfect for combining short clips (like 8-second recordings) into one polished, edited video with all silence removed.

## Execution Script

`execution/multi_clip_editor.py`

---

## Quick Start

```bash
# Process all videos in a directory (auto-sorted by filename)
python3 execution/multi_clip_editor.py --input-dir ./my_clips --output final.mp4

# Process specific files in order
python3 execution/multi_clip_editor.py \
    --input clip1.mp4 clip2.mp4 clip3.mp4 \
    --output final.mp4

# Adjust silence threshold (more aggressive cuts)
python3 execution/multi_clip_editor.py \
    --input-dir ./clips \
    --output final.mp4 \
    --min-silence 0.3

# Keep the merged (unedited) file too
python3 execution/multi_clip_editor.py \
    --input-dir ./clips \
    --output final.mp4 \
    --keep-merged
```

---

## How It Works

1. **Auto-sorts clips** by filename (alphabetically)
2. **Merges all clips** into one continuous video
3. **Extracts audio** for VAD processing
4. **Runs Silero VAD** to detect speech vs silence
5. **Removes silence** from beginning, end, and during talking
6. **Concatenates speech segments** with padding
7. **Outputs final edited video**

---

## CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--input-dir` | - | Directory with video clips (mutually exclusive with `--input`) |
| `--input` | - | List of specific video files (mutually exclusive with `--input-dir`) |
| `--output` | required | Output video file path |
| `--min-silence` | 0.5 | Minimum silence gap to cut (seconds) |
| `--min-speech` | 0.25 | Minimum speech duration to keep (seconds) |
| `--padding` | 100 | Padding around speech in milliseconds |
| `--merge-gap` | 0.3 | Merge segments closer than this (seconds) |
| `--keep-merged` | false | Keep the merged (unedited) video file |

---

## Workflow Example

### Scenario: 10 Short Clips

You have 10 video clips named:
- `clip_001.mp4`
- `clip_002.mp4`
- ...
- `clip_010.mp4`

Each clip is 8 seconds, some have silence at the beginning/end, and some have pauses during talking.

**Command:**
```bash
python3 execution/multi_clip_editor.py \
    --input-dir ./my_recordings \
    --output final_edited.mp4
```

**What happens:**
1. ✅ Clips are sorted by filename automatically (001, 002, ..., 010)
2. ✅ All clips merged into one 80-second video
3. ✅ Silence detected and removed (beginning, end, and 0.5s+ pauses)
4. ✅ Final video might be 60 seconds (20 seconds of silence removed)

---

## Silence Threshold Guide

| `--min-silence` | Behavior | Best For |
|-----------------|----------|----------|
| 0.3 | Aggressive - removes brief pauses | Fast-paced content, tight editing |
| 0.5 | **Balanced** (default) - removes noticeable pauses | General use, natural feel |
| 0.8 | Gentle - only removes long pauses | Conversational, preserves natural rhythm |

---

## File Naming for Auto-Sort

The script sorts files **alphabetically** by filename. For best results:

✅ **Good naming:**
- `001_intro.mp4`, `002_main.mp4`, `003_outro.mp4`
- `clip_01.mp4`, `clip_02.mp4`, `clip_03.mp4`
- `part1.mp4`, `part2.mp4`, `part3.mp4`

❌ **Bad naming (wrong order):**
- `clip_1.mp4`, `clip_10.mp4`, `clip_2.mp4` → sorts as 1, 10, 2
- Use `clip_01.mp4`, `clip_02.mp4`, `clip_10.mp4` instead

---

## Dependencies

### System Requirements

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

### Python Dependencies

```bash
# Install PyTorch (for Silero VAD)
pip install torch

# Alternative: Use requirements file if available
pip install -r requirements.txt
```

The Silero VAD model is downloaded automatically from torch.hub on first run (~2MB).

---

## Example Output

```
🎬 Multi-Clip Video Editor
   Processing 5 clips
   Output: final.mp4

📦 Merging 5 video clips...
   1. clip_001.mp4
   2. clip_002.mp4
   3. clip_003.mp4
   4. clip_004.mp4
   5. clip_005.mp4
✅ Clips merged successfully
📏 Merged video duration: 40.00s (0.7 min)

🎵 Extracting audio...
🎯 Detecting speech (min_silence=0.5s)...
   Found 12 speech segments
     1. 0.00s - 6.32s (6.32s)
     2. 7.15s - 13.44s (6.29s)
     3. 14.28s - 20.12s (5.84s)
     4. 21.05s - 26.88s (5.83s)
     5. 27.92s - 33.45s (5.53s)
     ... and 7 more
📎 After merging close segments: 10 segments
🔲 After adding 100ms padding: 10 segments

✂️  Extracting 10 speech segments...
✅ Edited video saved to final.mp4

📊 Results:
   Original: 40.00s (0.7 min)
   Edited: 34.50s (0.6 min)
   Removed: 5.50s (13.8%)

✅ Done!
```

---

## Advanced Usage

### Keep Merged File for Review

Sometimes you want to see the merged (unedited) video before silence removal:

```bash
python3 execution/multi_clip_editor.py \
    --input-dir ./clips \
    --output final_edited.mp4 \
    --keep-merged
```

This creates:
- `final_edited.mp4` - Edited version (silence removed)
- `final_edited_merged.mp4` - Merged version (all clips, no editing)

### Process Specific Files in Custom Order

If filenames don't sort correctly, specify the exact order:

```bash
python3 execution/multi_clip_editor.py \
    --input intro.mp4 middle_part.mp4 conclusion.mp4 \
    --output final.mp4
```

### Very Aggressive Editing

For maximum compression (remove all pauses):

```bash
python3 execution/multi_clip_editor.py \
    --input-dir ./clips \
    --output final.mp4 \
    --min-silence 0.2 \
    --padding 50
```

---

## Troubleshooting

### "No video files found"

- Check that your directory contains video files with extensions: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v`
- Use `--input` to specify files manually if needed

### "No speech detected"

- Try lowering `--min-speech` to 0.1
- Check that your videos have audio tracks
- Verify audio isn't corrupted: `ffplay your_video.mp4`

### Cuts feel too aggressive

- Increase `--min-silence` to 0.8 or 1.0
- Increase `--padding` to 150-200ms

### Clips in wrong order

- Rename files with leading zeros: `clip_01.mp4`, `clip_02.mp4`, etc.
- Or use `--input file1.mp4 file2.mp4 file3.mp4` to specify exact order

### FFmpeg errors

- Update FFmpeg: `brew upgrade ffmpeg` or download latest from ffmpeg.org
- Check video files aren't corrupted
- Try processing with `--keep-merged` and check if merging works

---

## Performance

**Processing time depends on:**
- Number and length of clips
- Hardware (CPU/GPU)
- Video resolution

**Typical benchmark (5 clips, 8 seconds each, 1080p):**
- Merging: ~2-5 seconds
- VAD processing: ~5-10 seconds
- Segment extraction: ~10-15 seconds
- **Total: ~20-30 seconds**

For longer videos (30+ minutes), expect 1-2 minutes of processing time.

---

## Comparison to Other Scripts

| Feature | multi_clip_editor.py | jump_cut_vad.py | simple_video_edit.py |
|---------|---------------------|-----------------|---------------------|
| Multi-clip support | ✅ Yes (auto-merge) | ❌ No | ❌ No |
| Silence detection | Neural VAD | Neural VAD | FFmpeg volume-based |
| Auto-sort by filename | ✅ Yes | N/A | N/A |
| Audio enhancement | ❌ No | ✅ Yes | ✅ Basic |
| Color grading (LUT) | ❌ No | ✅ Yes | ❌ No |
| YouTube upload | ❌ No | ❌ No | ✅ Yes |

**Use `multi_clip_editor.py` for:** Merging and editing multiple clips
**Use `jump_cut_vad.py` for:** Single video with audio enhancement
**Use `simple_video_edit.py` for:** End-to-end YouTube workflow

---

## License

Part of the VideoEdit project.
