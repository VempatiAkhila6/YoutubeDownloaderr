import os
import logging
import time
import re
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
from datetime import timedelta
from threading import Thread
import shutil

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

logging.basicConfig(level=logging.INFO)
progress_store = {}

def clean_youtube_url(url):
    match = re.match(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11}))', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(2)}"
    return url

def progress_hook(d, session_id):
    progress = progress_store.get(session_id, {"percentage": 0, "status": "", "error": "", "title": ""})
    if d['status'] == 'downloading':
        try:
            p = d.get('_percent_str', '0.0%').replace('%', '')
            progress['percentage'] = float(p)
            progress['status'] = 'Downloading'
        except ValueError:
            progress['percentage'] = 0
    elif d['status'] == 'finished':
        progress['percentage'] = 100
        progress['status'] = 'Downloaded'
    elif d['status'] == 'error':
        progress['error'] = 'Download failed'
        progress['status'] = 'Error'
    progress_store[session_id] = progress

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_info', methods=['POST'])
def video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        cleaned_url = clean_youtube_url(url)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(cleaned_url, download=False)
            duration = str(timedelta(seconds=int(info.get('duration', 0))))
            return jsonify({
                "title": info.get('title', 'Unknown Title'),
                "duration": duration,
                "thumbnail": info.get('thumbnail', '')
            })
    except Exception as e:
        logging.error(f"Error fetching video info: {e}")
        return jsonify({"error": "Failed to fetch video info"}), 500

@app.route('/download', methods=['POST'])
def download():
    try:
        session_id = str(time.time())
        url = request.form.get('url')
        format_type = request.form.get('format', 'mp4')
        resolution = request.form.get('resolution', '720p').replace('p', '')

        if not url:
            return jsonify({"error": "No URL provided", "session_id": session_id}), 400

        cleaned_url = clean_youtube_url(url)
        output_file = f"downloads/{session_id}.{format_type}"
        os.makedirs('downloads', exist_ok=True)

        progress_store[session_id] = {
            "percentage": 0, "status": "Initializing", "error": "", "title": ""
        }

        def run_download():
            try:
                ydl_opts = {
                    'outtmpl': output_file,
                    'noplaylist': True,
                    'quiet': True,
                    'no_warnings': True,
                    'progress_hooks': [lambda d: progress_hook(d, session_id)],
                    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                }

                if format_type == 'mp4':
                    ydl_opts['format'] = f"bestvideo[height<={resolution}]+bestaudio/best"
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }]
                elif format_type == 'mp3':
                    ydl_opts['format'] = 'bestaudio[ext=m4a]'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(cleaned_url, download=True)
                    progress_store[session_id]['title'] = info.get('title', 'Downloaded File')

            except Exception as e:
                progress_store[session_id]['error'] = str(e)
                progress_store[session_id]['status'] = 'Error'
                logging.error(f"Download error: {e}")

        Thread(target=run_download, daemon=True).start()

        return jsonify({"status": "started", "session_id": session_id})
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({"error": "Server error", "session_id": session_id}), 500

@app.route('/progress')
def progress():
    session_id = request.args.get('session_id')
    if session_id in progress_store:
        return jsonify(progress_store[session_id])
    return jsonify({"error": "Invalid or missing session ID"}), 400

@app.route('/download_file')
def download_file():
    session_id = request.args.get('session_id')
    format_type = request.args.get('format', 'mp4')
    filepath = f"downloads/{session_id}.{format_type}"

    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    title = progress_store.get(session_id, {}).get('title', 'Downloaded_File')
    safe_title = re.sub(r'[\\/:"*?<>|]+', '_', title)
    response = send_file(filepath, as_attachment=True, download_name=f"{safe_title}.{format_type}")

    def cleanup():
        time.sleep(300)
        if os.path.exists(filepath):
            os.remove(filepath)
        progress_store.pop(session_id, None)

    Thread(target=cleanup, daemon=True).start()
    return response

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
