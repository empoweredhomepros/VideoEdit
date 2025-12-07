# VideoEdit - Multi-Clip Video Editor

Automatically merge and edit multiple video clips with intelligent silence removal.

Perfect for combining short recordings (like 8-second clips) into one polished video with all silence trimmed out.

## Quick Start

```bash
# 1. Install dependencies
pip install torch

# 2. Make sure you have FFmpeg installed
brew install ffmpeg  # macOS
# or: sudo apt install ffmpeg  # Linux

# 3. Run the editor
python3 execution/multi_clip_editor.py --input-dir ./my_clips --output final.mp4
```

## Features

✅ **Auto-merge multiple clips** in filename order
✅ **Smart silence detection** using neural voice activity detection (Silero VAD)
✅ **Removes silence** from beginning, end, and during talking (0.5s+ pauses)
✅ **Command-line interface** - simple and fast
✅ **Configurable thresholds** - aggressive, balanced, or gentle editing

## Usage Examples

### Process all clips in a folder
```bash
python3 execution/multi_clip_editor.py \
    --input-dir ./recordings \
    --output final_edited.mp4
```

### Process specific files in order
```bash
python3 execution/multi_clip_editor.py \
    --input clip1.mp4 clip2.mp4 clip3.mp4 \
    --output final.mp4
```

### Adjust silence threshold
```bash
# More aggressive (removes 0.3s+ pauses)
python3 execution/multi_clip_editor.py \
    --input-dir ./clips \
    --output final.mp4 \
    --min-silence 0.3

# More gentle (removes 0.8s+ pauses)
python3 execution/multi_clip_editor.py \
    --input-dir ./clips \
    --output final.mp4 \
    --min-silence 0.8
```

## How It Works

1. **Sorts clips** by filename alphabetically
2. **Merges all clips** into one continuous video
3. **Detects speech** using neural VAD (much better than volume-based)
4. **Removes silence** at beginning, end, and during pauses
5. **Outputs edited video** with all cuts seamlessly joined

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-silence` | 0.5s | Remove pauses longer than this |
| `--min-speech` | 0.25s | Keep speech segments longer than this |
| `--padding` | 100ms | Breathing room around speech |
| `--merge-gap` | 0.3s | Merge close segments |

## File Naming Tips

For automatic sorting, use numbered filenames:

✅ **Good:**
- `001_intro.mp4`, `002_main.mp4`, `003_outro.mp4`
- `clip_01.mp4`, `clip_02.mp4`, `clip_10.mp4`

❌ **Bad:**
- `clip_1.mp4`, `clip_10.mp4`, `clip_2.mp4` (sorts incorrectly as 1, 10, 2)

## Documentation

- **Multi-Clip Editor:** `directives/multi_clip_editor.md` - Full documentation
- **Jump Cut VAD:** `directives/jump_cut_vad.md` - Single video editing with audio enhancement
- **Simple Editor:** `directives/smart_video_edit.md` - FFmpeg-based editing with YouTube upload

## System Requirements

- Python 3.8+
- FFmpeg (for video processing)
- PyTorch (for VAD model)

**Installation:**
```bash
# macOS
brew install ffmpeg
pip install torch

# Linux (Ubuntu/Debian)
sudo apt install ffmpeg
pip install torch

# Windows
# Download FFmpeg from https://ffmpeg.org/download.html
# Install PyTorch: pip install torch
```

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
   Found 10 speech segments
📎 After merging close segments: 8 segments
🔲 After adding 100ms padding: 8 segments

✂️  Extracting 8 speech segments...
✅ Edited video saved to final.mp4

📊 Results:
   Original: 40.00s (0.7 min)
   Edited: 34.50s (0.6 min)
   Removed: 5.50s (13.8%)

✅ Done!
```

## Troubleshooting

**No speech detected?**
- Lower `--min-speech` to 0.1
- Check videos have audio tracks

**Cuts too aggressive?**
- Increase `--min-silence` to 0.8
- Increase `--padding` to 150-200

**Clips in wrong order?**
- Rename with leading zeros: `clip_01.mp4` instead of `clip_1.mp4`
- Or use `--input file1.mp4 file2.mp4` to specify exact order

## Other Tools in This Project

This repository contains several video editing tools:

- **`multi_clip_editor.py`** - Merge and edit multiple clips (you are here)
- **`jump_cut_vad.py`** - Advanced single-video editor with audio enhancement and color grading
- **`simple_video_edit.py`** - FFmpeg-based editing with YouTube upload integration
- **Video effects** - 3D transitions and effects using Remotion

See the `directives/` folder for full documentation of each tool.

## License

MIT
