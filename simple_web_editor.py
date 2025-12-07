#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os, tempfile, subprocess, shutil
from pathlib import Path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['OUTPUT_FOLDER'] = tempfile.mkdtemp()

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'}
upload_sessions = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        # Merge videos
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

        # Get duration
        result = subprocess.run([
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            merged_path
        ], capture_output=True, text=True)
        duration = float(result.stdout.strip())

        # Simple silence removal using FFmpeg
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{session_id}_final.mp4')

        subprocess.run([
            'ffmpeg', '-y', '-i', merged_path,
            '-af', 'silenceremove=start_periods=1:start_duration=0.5:start_threshold=-40dB:detection=peak,silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-40dB:detection=peak',
            '-c:v', 'copy',
            '-loglevel', 'error',
            output_path
        ], check=True)

        os.remove(merged_path)

        # Get new duration
        result = subprocess.run([
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            output_path
        ], capture_output=True, text=True)
        new_duration = float(result.stdout.strip())
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
                'segments_count': 1
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
    app.run(debug=True, host='127.0.0.1', port=8000)
