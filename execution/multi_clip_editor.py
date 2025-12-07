#!/usr/bin/env python3
"""
Multi-Clip Video Editor with Silence Detection

Merges multiple video clips in filename order, then removes silence using
neural voice activity detection (Silero VAD).

Perfect for editing multiple short clips into one polished video.

Usage:
    # Process all videos in a directory
    python3 execution/multi_clip_editor.py --input-dir ./clips --output final.mp4

    # Process specific files (in order provided)
    python3 execution/multi_clip_editor.py --input clip1.mp4 clip2.mp4 clip3.mp4 --output final.mp4

    # Custom silence threshold (0.5s is balanced)
    python3 execution/multi_clip_editor.py --input-dir ./clips --output final.mp4 --min-silence 0.5

Features:
- Auto-sorts clips by filename
- Merges all clips before processing
- Removes silence from beginning/end of scenes
- Removes half-second (or custom) silences during talking
- Neural VAD for accurate speech detection
"""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple


# Default parameters
MIN_SILENCE_DURATION = 0.5  # Balanced: removes noticeable pauses
MIN_SPEECH_DURATION = 0.25  # Keep speech segments longer than 0.25s
PADDING_MS = 100  # Padding around speech segments
MERGE_GAP = 0.3  # Merge segments closer than 0.3s


def get_video_files_from_directory(directory: str) -> List[str]:
    """Get all video files from a directory, sorted by filename."""
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    video_files = []

    for file in Path(directory).iterdir():
        if file.is_file() and file.suffix.lower() in video_extensions:
            video_files.append(str(file))

    # Sort alphabetically by filename
    return sorted(video_files)


def concatenate_videos(input_files: List[str], output_path: str) -> None:
    """Concatenate multiple video files using FFmpeg concat demuxer."""
    print(f"📦 Merging {len(input_files)} video clips...")

    for i, file in enumerate(input_files, 1):
        print(f"   {i}. {Path(file).name}")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        concat_file = f.name
        for video in input_files:
            # Escape single quotes in filenames and write absolute path
            abs_path = os.path.abspath(video)
            # FFmpeg concat demuxer needs proper escaping
            escaped_path = abs_path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")

    try:
        # Use concat demuxer for fast, lossless concatenation
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",  # Stream copy - no re-encoding
            "-loglevel", "error",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"⚠️  Stream copy failed, re-encoding...")
            # Fallback: re-encode if stream copy fails (different codecs/settings)
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-loglevel", "error",
                output_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)

        print(f"✅ Clips merged successfully")

    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


def extract_audio(input_path: str, output_path: str, sample_rate: int = 16000) -> None:
    """Extract audio from video as WAV for VAD processing."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-ar", str(sample_rate), "-ac", "1",
        "-acodec", "pcm_s16le",
        "-loglevel", "error", output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def get_speech_timestamps_silero(
    audio_path: str,
    min_speech_duration: float = 0.25,
    min_silence_duration: float = 0.5
) -> List[Tuple[float, float]]:
    """
    Use Silero VAD to detect speech segments.
    Returns list of (start, end) tuples in seconds.
    """
    import torch

    # Load Silero VAD model
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        trust_repo=True
    )

    (get_speech_timestamps, _, read_audio, _, _) = utils

    # Read audio
    SAMPLE_RATE = 16000
    wav = read_audio(audio_path, sampling_rate=SAMPLE_RATE)

    # Get speech timestamps
    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=SAMPLE_RATE,
        threshold=0.5,
        min_speech_duration_ms=int(min_speech_duration * 1000),
        min_silence_duration_ms=int(min_silence_duration * 1000),
        speech_pad_ms=100,
    )

    # Convert from samples to seconds
    segments = []
    for ts in speech_timestamps:
        start_sec = ts['start'] / SAMPLE_RATE
        end_sec = ts['end'] / SAMPLE_RATE
        segments.append((start_sec, end_sec))

    return segments


def merge_close_segments(
    segments: List[Tuple[float, float]],
    max_gap: float
) -> List[Tuple[float, float]]:
    """Merge segments that are very close together."""
    if not segments:
        return []

    merged = [segments[0]]
    for start, end in segments[1:]:
        prev_start, prev_end = merged[-1]

        if start - prev_end <= max_gap:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    return merged


def add_padding(
    segments: List[Tuple[float, float]],
    padding_s: float,
    duration: float
) -> List[Tuple[float, float]]:
    """Add padding around segments and merge any overlaps."""
    if not segments:
        return []

    padded = []
    for start, end in segments:
        new_start = max(0, start - padding_s)
        new_end = min(duration, end + padding_s)
        padded.append((new_start, new_end))

    # Merge overlapping segments
    merged = [padded[0]]
    for start, end in padded[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def concatenate_segments(
    input_path: str,
    segments: List[Tuple[float, float]],
    output_path: str
) -> None:
    """Extract and concatenate video segments."""
    print(f"✂️  Extracting {len(segments)} speech segments...")

    with tempfile.TemporaryDirectory() as tmpdir:
        segment_files = []

        for i, (start, end) in enumerate(segments):
            seg_path = os.path.join(tmpdir, f"seg_{i:04d}.mp4")
            duration = end - start

            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ss", str(start),
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-loglevel", "error",
                seg_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            segment_files.append(seg_path)

        # Create concat file
        concat_path = os.path.join(tmpdir, "concat.txt")
        with open(concat_path, "w") as f:
            for seg_path in segment_files:
                f.write(f"file '{seg_path}'\n")

        # Concatenate
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-c", "copy",
            "-loglevel", "error",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    print(f"✅ Edited video saved to {output_path}")


def get_duration(input_path: str) -> float:
    """Get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(
        description="Multi-clip video editor with silence detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all videos in a directory
  python3 execution/multi_clip_editor.py --input-dir ./clips --output final.mp4

  # Process specific files
  python3 execution/multi_clip_editor.py --input clip1.mp4 clip2.mp4 --output final.mp4

  # Adjust silence threshold
  python3 execution/multi_clip_editor.py --input-dir ./clips --output final.mp4 --min-silence 0.3
        """
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-dir",
        help="Directory containing video clips (will be sorted by filename)"
    )
    input_group.add_argument(
        "--input",
        nargs="+",
        help="List of video files to process (in order provided)"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output video file path"
    )

    parser.add_argument(
        "--min-silence",
        type=float,
        default=MIN_SILENCE_DURATION,
        help=f"Minimum silence duration to cut in seconds (default: {MIN_SILENCE_DURATION})"
    )

    parser.add_argument(
        "--min-speech",
        type=float,
        default=MIN_SPEECH_DURATION,
        help=f"Minimum speech duration to keep in seconds (default: {MIN_SPEECH_DURATION})"
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=PADDING_MS,
        help=f"Padding around speech in milliseconds (default: {PADDING_MS})"
    )

    parser.add_argument(
        "--merge-gap",
        type=float,
        default=MERGE_GAP,
        help=f"Merge segments closer than this in seconds (default: {MERGE_GAP})"
    )

    parser.add_argument(
        "--keep-merged",
        action="store_true",
        help="Keep the merged (unedited) video file"
    )

    args = parser.parse_args()

    # Get input files
    if args.input_dir:
        if not os.path.isdir(args.input_dir):
            print(f"❌ Error: Directory not found: {args.input_dir}")
            return 1
        input_files = get_video_files_from_directory(args.input_dir)
        if not input_files:
            print(f"❌ Error: No video files found in {args.input_dir}")
            return 1
    else:
        input_files = args.input
        # Validate all files exist
        for file in input_files:
            if not os.path.exists(file):
                print(f"❌ Error: File not found: {file}")
                return 1

    print(f"🎬 Multi-Clip Video Editor")
    print(f"   Processing {len(input_files)} clips")
    print(f"   Output: {args.output}")
    print()

    # Step 1: Merge all clips
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        merged_path = tmp.name

    try:
        concatenate_videos(input_files, merged_path)

        # Get merged video duration
        duration = get_duration(merged_path)
        print(f"📏 Merged video duration: {duration:.2f}s ({duration/60:.1f} min)")
        print()

        # Step 2: Extract audio for VAD
        print(f"🎵 Extracting audio...")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name

        try:
            extract_audio(merged_path, audio_path)

            # Step 3: Run Silero VAD
            print(f"🎯 Detecting speech (min_silence={args.min_silence}s)...")
            speech_segments = get_speech_timestamps_silero(
                audio_path,
                min_speech_duration=args.min_speech,
                min_silence_duration=args.min_silence
            )
            print(f"   Found {len(speech_segments)} speech segments")

            # Show first few segments
            for i, (start, end) in enumerate(speech_segments[:5]):
                print(f"     {i+1}. {start:.2f}s - {end:.2f}s ({end-start:.2f}s)")
            if len(speech_segments) > 5:
                print(f"     ... and {len(speech_segments) - 5} more")

        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

        if not speech_segments:
            print("⚠️  No speech detected!")
            return 1

        # Step 4: Merge close segments
        speech_segments = merge_close_segments(speech_segments, args.merge_gap)
        print(f"📎 After merging close segments: {len(speech_segments)} segments")

        # Step 5: Add padding
        padding_s = args.padding / 1000
        speech_segments = add_padding(speech_segments, padding_s, duration)
        print(f"🔲 After adding {args.padding}ms padding: {len(speech_segments)} segments")
        print()

        # Step 6: Concatenate speech segments
        concatenate_segments(merged_path, speech_segments, args.output)

        # Stats
        new_duration = get_duration(args.output)
        removed = duration - new_duration
        print()
        print(f"📊 Results:")
        print(f"   Original: {duration:.2f}s ({duration/60:.1f} min)")
        print(f"   Edited: {new_duration:.2f}s ({new_duration/60:.1f} min)")
        print(f"   Removed: {removed:.2f}s ({100*removed/duration:.1f}%)")

        # Save merged file if requested
        if args.keep_merged:
            merged_output = str(Path(args.output).with_suffix('')) + '_merged.mp4'
            os.rename(merged_path, merged_output)
            print(f"   Merged (unedited) saved to: {merged_output}")
            merged_path = None  # Prevent deletion

    finally:
        # Clean up merged file unless --keep-merged
        if merged_path and os.path.exists(merged_path):
            os.remove(merged_path)

    print()
    print("✅ Done!")
    return 0


if __name__ == "__main__":
    exit(main())
