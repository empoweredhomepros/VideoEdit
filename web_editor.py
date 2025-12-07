#!/usr/bin/env python3
"""
Browser-Based Multi-Clip Video Editor

A simple web interface for uploading, merging, and editing multiple video clips
with automatic silence detection.

Usage:
    python3 web_editor.py

Then open your browser to: http://localhost:5000
"""

import os
import tempfile
import subprocess
from pathlib import Path
from typing import List, Tuple
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import shutil

# Import our video processing functions
import sys
sys.path.append(os.path.dirname(__file__))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['OUTPUT_FOLDER'] = tempfile.mkdtemp()

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'}

# Store upload sessions
upload_sessions = {}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
    """Use Silero VAD to detect speech segments."""
    import torch

    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        trust_repo=True
    )

    (get_speech_timestamps, _, read_audio, _, _) = utils

    SAMPLE_RATE = 16000
    wav = read_audio(audio_path, sampling_rate=SAMPLE_RATE)

    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=SAMPLE_RATE,
        threshold=0.5,
        min_speech_duration_ms=int(min_speech_duration * 1000),
        min_silence_duration_ms=int(min_silence_duration * 1000),
        speech_pad_ms=100,
    )

    segments = []
    for ts in speech_timestamps:
        start_sec = ts['start'] / SAMPLE_RATE
        end_sec = ts['end'] / SAMPLE_RATE
        segments.append((start_sec, end_sec))

    return segments


def merge_close_segments(segments: List[Tuple[float, float]], max_gap: float) -> List[Tuple[float, float]]:
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


def add_padding(segments: List[Tuple[float, float]], padding_s: float, duration: float) -> List[Tuple[float, float]]:
    """Add padding around segments and merge any overlaps."""
    if not segments:
        return []

    padded = []
    for start, end in segments:
        new_start = max(0, start - padding_s)
        new_end = min(duration, end + padding_s)
        padded.append((new_start, new_end))

    merged = [padded[0]]
    for start, end in padded[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def concatenate_videos(input_files: List[str], output_path: str) -> None:
    """Concatenate multiple video files using FFmpeg."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        concat_file = f.name
        for video in input_files:
            abs_path = os.path.abspath(video)
            escaped_path = abs_path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")

    try:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            "-loglevel", "error",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-loglevel", "error",
                output_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


def concatenate_segments(input_path: str, segments: List[Tuple[float, float]], output_path: str) -> None:
    """Extract and concatenate video segments."""
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

        concat_path = os.path.join(tmpdir, "concat.txt")
        with open(concat_path, "w") as f:
            for seg_path in segment_files:
                f.write(f"file '{seg_path}'\n")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-c", "copy",
            "-loglevel", "error",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)


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


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle multiple file uploads."""
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    session_id = str(os.urandom(8).hex())
    session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    os.makedirs(session_folder, exist_ok=True)

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(session_folder, filename)
            file.save(filepath)
            uploaded_files.append({
                'name': filename,
                'path': filepath,
                'size': os.path.getsize(filepath)
            })

    upload_sessions[session_id] = uploaded_files

    return jsonify({
        'session_id': session_id,
        'files': uploaded_files
    })


@app.route('/process', methods=['POST'])
def process_videos():
    """Process the uploaded videos."""
    data = request.json
    session_id = data.get('session_id')
    file_order = data.get('file_order', [])
    min_silence = float(data.get('min_silence', 0.5))
    min_speech = float(data.get('min_speech', 0.25))
    padding = int(data.get('padding', 100))
    merge_gap = float(data.get('merge_gap', 0.3))

    if not session_id or session_id not in upload_sessions:
        return jsonify({'error': 'Invalid session'}), 400

    # Get files in specified order
    session_files = upload_sessions[session_id]
    file_map = {f['name']: f['path'] for f in session_files}

    if file_order:
        input_files = [file_map[name] for name in file_order if name in file_map]
    else:
        input_files = [f['path'] for f in session_files]

    if not input_files:
        return jsonify({'error': 'No valid files to process'}), 400

    try:
        # Step 1: Merge videos
        merged_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_merged.mp4')
        concatenate_videos(input_files, merged_path)

        duration = get_duration(merged_path)

        # Step 2: Extract audio and run VAD
        audio_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_audio.wav')
        extract_audio(merged_path, audio_path)

        speech_segments = get_speech_timestamps_silero(
            audio_path,
            min_speech_duration=min_speech,
            min_silence_duration=min_silence
        )

        os.remove(audio_path)

        if not speech_segments:
            return jsonify({'error': 'No speech detected'}), 400

        # Step 3: Process segments
        speech_segments = merge_close_segments(speech_segments, merge_gap)
        padding_s = padding / 1000
        speech_segments = add_padding(speech_segments, padding_s, duration)

        # Step 4: Create final video
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_final.mp4')
        concatenate_segments(merged_path, speech_segments, output_path)

        os.remove(merged_path)

        new_duration = get_duration(output_path)
        removed = duration - new_duration

        return jsonify({
            'success': True,
            'session_id': session_id,
            'download_url': f'/download/{session_id}',
            'stats': {
                'original_duration': round(duration, 2),
                'edited_duration': round(new_duration, 2),
                'removed_duration': round(removed, 2),
                'removed_percent': round(100 * removed / duration, 1),
                'segments_count': len(speech_segments)
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<session_id>')
def download_file(session_id):
    """Download the processed video."""
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_final.mp4')

    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        output_path,
        as_attachment=True,
        download_name='edited_video.mp4',
        mimetype='video/mp4'
    )


@app.route('/cleanup/<session_id>', methods=['POST'])
def cleanup_session(session_id):
    """Clean up session files."""
    # Clean upload folder
    session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    if os.path.exists(session_folder):
        shutil.rmtree(session_folder)

    # Clean output files
    for suffix in ['_merged.mp4', '_final.mp4', '_audio.wav']:
        filepath = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}{suffix}')
        if os.path.exists(filepath):
            os.remove(filepath)

    if session_id in upload_sessions:
        del upload_sessions[session_id]

    return jsonify({'success': True})


if __name__ == '__main__':
    print("🎬 Multi-Clip Video Editor - Web Interface")
    print("=" * 50)
    print("Starting server...")
    print("\n📱 Open your browser to: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 50)

    app.run(debug=True, host='0.0.0.0', port=5000)
