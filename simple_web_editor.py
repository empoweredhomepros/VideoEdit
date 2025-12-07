#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os, tempfile, subprocess, shutil, re
from pathlib import Path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['OUTPUT_FOLDER'] = tempfile.mkdtemp()

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'}
upload_sessions = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_silence(video_path, threshold_db=-40, min_duration=0.5):
    """Detect silent sections using FFmpeg."""
    cmd = [
        'ffmpeg', '-i', video_path,
        '-af', f'silencedetect=noise={threshold_db}dB:d={min_duration}',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    silence_starts = re.findall(r'silence_start: ([\d.]+)', stderr)
    silence_ends = re.findall(r'silence_end: ([\d.]+)', stderr)

    silences = []
    for i, start in enumerate(silence_starts):
        if i < len(silence_ends):
            silences.append((float(start), float(silence_ends[i])))
        else:
            silences.append((float(start), None))

    return silences

def get_duration(video_path):
    """Get video duration in seconds."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def calculate_keep_segments(silences, duration, buffer=0.1):
    """Calculate which segments to keep (inverse of silence)."""
    if not silences:
        return [(0, duration)]

    keep_segments = []
    current_pos = 0.0

    for silence_start, silence_end in silences:
        if silence_end is None:
            silence_end = duration

        # Add small buffer for transitions
        adjusted_start = silence_start + buffer
        adjusted_end = silence_end - buffer

        # Only cut if meaningful silence remains after buffering (at least 0.3s)
        if adjusted_end - adjusted_start < 0.3:
            # Silence too short after buffering, skip cutting it
            continue

        if adjusted_start > current_pos:
            keep_segments.append((current_pos, adjusted_start))

        current_pos = adjusted_end

    if current_pos < duration:
        keep_segments.append((current_pos, duration))

    return keep_segments

def extract_and_concat_segments(input_path, segments, output_path):
    """Extract video segments and concatenate with smooth crossfades."""

    if len(segments) == 1:
        # Single segment, just extract it
        start, end = segments[0]
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start),
            '-i', input_path,
            '-t', str(end - start),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            '-loglevel', 'error',
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        segment_files = []

        # Extract each segment
        for i, (start, end) in enumerate(segments):
            seg_path = os.path.join(tmpdir, f'seg_{i:04d}.mp4')
            duration = end - start

            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start),
                '-i', input_path,
                '-t', str(duration),
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-b:a', '192k',
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts',
                '-loglevel', 'error',
                seg_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            segment_files.append(seg_path)

        # Build crossfade filter (0.1 second crossfades for smooth transitions)
        fade_duration = 0.1

        # Build the filter for 2 segments (simpler approach)
        if len(segment_files) == 2:
            # Get duration of first segment
            result = subprocess.run([
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                segment_files[0]
            ], capture_output=True, text=True)
            dur0 = float(result.stdout.strip())

            offset = dur0 - fade_duration

            cmd = [
                'ffmpeg', '-y',
                '-i', segment_files[0],
                '-i', segment_files[1],
                '-filter_complex',
                f'[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset}[vout];'
                f'[0:a][1:a]acrossfade=d={fade_duration}[aout]',
                '-map', '[vout]',
                '-map', '[aout]',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-b:a', '192k',
                '-movflags', '+faststart',
                '-loglevel', 'error',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return

        # Fallback: simple concatenation without crossfade
        concat_path = os.path.join(tmpdir, 'concat.txt')
        with open(concat_path, 'w') as f:
            for seg_path in segment_files:
                f.write(f"file '{seg_path}'\n")

        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_path,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            '-loglevel', 'error',
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
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
    return jsonify({'session_id': session_id, 'files': uploaded_files})

@app.route('/process', methods=['POST'])
def process_videos():
    data = request.json
    session_id = data.get('session_id')
    file_order = data.get('file_order', [])

    if not session_id or session_id not in upload_sessions:
        return jsonify({'error': 'Invalid session'}), 400

    session_files = upload_sessions[session_id]
    file_map = {f['name']: f['path'] for f in session_files}

    if file_order:
        input_files = [file_map[name] for name in file_order if name in file_map]
    else:
        input_files = [f['path'] for f in session_files]

    try:
        # Step 1: Merge videos
        merged_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_merged.mp4')
        concat_file = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_concat.txt')

        with open(concat_file, 'w') as f:
            for video in input_files:
                f.write(f"file '{os.path.abspath(video)}'\n")

        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            '-loglevel', 'error',
            merged_path
        ], check=True)

        os.remove(concat_file)

        # Step 2: Get duration
        duration = get_duration(merged_path)

        # Step 3: Detect silence (cut 0.5s+ pauses)
        silences = detect_silence(merged_path, threshold_db=-40, min_duration=0.5)

        # Step 4: Calculate segments to keep
        keep_segments = calculate_keep_segments(silences, duration, buffer=0.1)

        if not keep_segments:
            return jsonify({'error': 'No content detected after silence removal'}), 400

        # Step 5: Extract and concatenate segments (video + audio together)
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_final.mp4')
        extract_and_concat_segments(merged_path, keep_segments, output_path)

        os.remove(merged_path)

        # Step 6: Get new duration
        new_duration = get_duration(output_path)
        removed = max(0, duration - new_duration)

        return jsonify({
            'success': True,
            'session_id': session_id,
            'download_url': f'/download/{session_id}',
            'stats': {
                'original_duration': round(duration, 2),
                'edited_duration': round(new_duration, 2),
                'removed_duration': round(removed, 2),
                'removed_percent': round(100 * removed / duration, 1) if duration > 0 else 0,
                'segments_count': len(keep_segments)
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<session_id>')
def download_file(session_id):
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_final.mp4')
    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(output_path, as_attachment=True, download_name='edited_video.mp4', mimetype='video/mp4')

if __name__ == '__main__':
    print('🎬 Multi-Clip Video Editor - Simple Version')
    print('=' * 50)
    print('📱 Open your browser to: http://127.0.0.1:8000')
    print('Press Ctrl+C to stop')
    print('=' * 50)
    print()
    print('✅ This version cuts BOTH video and audio to keep them in sync!')
    print()
    app.run(debug=True, host='127.0.0.1', port=8000)
