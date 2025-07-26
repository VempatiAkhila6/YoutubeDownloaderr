import os
import logging
import time
import glob
import threading import Thread
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import ssl
from datetime import timedelta

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend communication

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Disable SSL verification for yt-dlp
ssl._create_default_https_context = ssl._create_unverified_context

# Thread-safe progress tracking per session
progress_store = {}

def progress_hook(d, session_id):
    progress = progress_store.get(session_id, {"percentage": 0, "status": "", "error": "", "title": ""})
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0.0%').replace('%', '')
        try:
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
def home():
    return render_template('index.html')

@app.route('/video_info', methods=['POST'])
def video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookies': 'cookies.txt' if os.path.exists('cookies.txt') else None
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or info.get('is_private') or info.get('availability') == 'private':
                return jsonify({"error": "Video is unavailable, private, or restricted"}), 400
            duration = str(timedelta(seconds=int(info.get('duration', 0))))
            return jsonify({
                "title": info.get('title', 'Unknown Title'),
                "duration": duration,
                "thumbnail": info.get('thumbnail', '')
            })
    except Exception as e:
        logging.error(f"Video info error for {url}: {str(e)}")
        return jsonify({"error": f"Failed to fetch video info: {str(e)}"}), 400

@app.route('/download', methods=['POST'])
def download():
    try:
        session_id = str(time.time())  # Unique ID for each download
        progress_store[session_id] = {"percentage": 0, "status": "Initializing", "error": "", "title": ""}

        url = request.form.get('url')
        format_type = request.form.get('format', 'mp4')
        resolution = request.form.get('resolution', '720p').replace('p', '')

        if not url:
            return jsonify({"error": "No URL provided", "session_id": session_id}), 400

        # Check video availability
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookies': 'cookies.txt' if os.path.exists('cookies.txt') else None
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or info.get('is_private') or info.get('availability') == 'private':
                progress_store[session_id]['error'] = 'Video is unavailable, private, or restricted'
                return jsonify({"error": "Video is unavailable, private, or restricted", "session_id": session_id}), 400
            progress_store[session_id]['title'] = info.get('title', 'Downloaded File')

        # Handle cookies
        cookies_data = os.getenv('COOKIES_DATA')
        if cookies_data:
            with open('cookies.txt', 'w') as f:
                f.write(cookies_data)
            logging.info("Cookies data written to cookies.txt")
        else:
            logging.warning("COOKIES_DATA not set; proceeding without cookies")

        output_file = f"downloads/{session_id}.{format_type}"
        os.makedirs('downloads', exist_ok=True)
        if os.path.exists(output_file):
            os.remove(output_file)

        # yt-dlp options
        options = {
            'outtmpl': output_file,
            'noplaylist': True,
            'progress_hooks': [lambda d: progress_hook(d, session_id)],
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': '/usr/bin/ffmpeg',
            'cookies': 'cookies.txt' if os.path.exists('cookies.txt') else None
        }

        if format_type == 'mp4':
            options['format'] = f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]'
            options['postprocessors'] = [{'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'}]
        else:  # mp3
            options['format'] = 'bestaudio'
            options['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }]

        def download_thread():
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([url])
            except Exception as e:
                logging.error(f"Download failed for {url}: {str(e)}")
                progress_store[session_id]['error'] = f"Download failed: {str(e)}"
                progress_store[session_id]['status'] = 'Error'

        Thread(target=download_thread, daemon=True).start()
        logging.info(f"Started download for {url}, format: {format_type}, session: {session_id}")
        return jsonify({"status": "started", "session_id": session_id}), 200
    except Exception as e:
        logging.error(f"Error in /download for {url}: {str(e)}")
        progress_store[session_id]['error'] = f"Server error: {str(e)}"
        return jsonify({"error": f"Server error: {str(e)}", "session_id": session_id}), 500

@app.route('/progress')
def progress():
    session_id = request.args.get('session_id')
    if not session_id or session_id not in progress_store:
        return jsonify({"error": "Invalid or missing session ID"}), 400
    return jsonify(progress_store[session_id])

@app.route('/download_file')
def download_file():
    try:
        session_id = request.args.get('session_id')
        format_type = request.args.get('format', 'mp4')
        if not session_id or session_id not in progress_store:
            return jsonify({"error": "Invalid or missing session ID"}), 400

        file_path = f"downloads/{session_id}.{format_type}"
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return jsonify({"error": "File not found"}), 404

        title = progress_store[session_id].get('title', 'Downloaded File').replace('/', '_').replace('\\', '_')
        response = send_file(file_path, as_attachment=True, download_name=f"{title}.{format_type}")

        # Schedule file cleanup
        def cleanup_file(path):
            time.sleep(3600)  # Retain file for 1 hour
            if os.path.exists(path):
                os.remove(path)
                logging.info(f"Cleaned up file: {path}")

        Thread(target=cleanup_file, args=(file_path,), daemon=True).start()
        logging.info(f"Serving file: {file_path}")
        return response
    except Exception as e:
        logging.error(f"Error serving file: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    app.run(debug=True)
