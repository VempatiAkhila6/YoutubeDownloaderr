import os
import ssl
import threading
import logging
from flask import Flask, request, render_template, send_file, jsonify

import yt_dlp

app = Flask(__name__)

# Disable SSL verification if needed (for Render or local issues)
ssl._create_default_https_context = ssl._create_unverified_context

# Setup logging
logging.basicConfig(level=logging.INFO)

# Download progress shared dict
download_progress = {
    "percentage": 0,
    "status": "",
    "error": "",
    "title": ""
}

# Write cookies.txt on startup from env variable (if exists)
COOKIES_DATA = os.environ.get("COOKIES_DATA")
if COOKIES_DATA:
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(COOKIES_DATA)
    logging.info("cookies.txt file created from COOKIES_DATA env var")
else:
    logging.warning("COOKIES_DATA env var not set; cookies.txt not created")

def progress_hook(d):
    try:
        if d['status'] == 'downloading':
            p_str = d.get('_percent_str', '0.0%').replace('%', '').strip()
            download_progress['percentage'] = float(p_str)
            download_progress['status'] = 'Downloading'
        elif d['status'] == 'finished':
            download_progress['percentage'] = 100
            download_progress['status'] = 'Finished downloading'
    except Exception as e:
        logging.error(f"Error in progress_hook: {e}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    global download_progress
    download_progress = {
        "percentage": 0,
        "status": "Starting download",
        "error": "",
        "title": ""
    }

    url = request.form.get('url')
    format_type = request.form.get('format', 'mp4').lower()
    resolution = request.form.get('resolution', '720p').replace('p', '')

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    os.makedirs('downloads', exist_ok=True)
    output_file = f"downloads/output.{format_type}"

    if os.path.exists(output_file):
        os.remove(output_file)

    ydl_opts = {
        'cookies': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'outtmpl': output_file,
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
        # 'ffmpeg_location': '/usr/bin/ffmpeg',  # uncomment if ffmpeg not in PATH
    }

    if format_type == 'mp4':
        ydl_opts['format'] = f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegVideoRemuxer', 'preferredformat': 'mp4'}]
    elif format_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        return jsonify({"error": f"Unsupported format: {format_type}"}), 400

    def download_thread():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                download_progress['title'] = info.get('title', 'Downloaded File')
                download_progress['status'] = 'Download complete'
        except Exception as e:
            logging.error(f"Download failed: {e}")
            download_progress['error'] = str(e)
            download_progress['status'] = 'Error occurred'

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({"status": "started"}), 200

@app.route('/progress')
def progress():
    return jsonify(download_progress)

@app.route('/download_file')
def download_file():
    format_type = request.args.get('format', 'mp4').lower()
    file_path = f"downloads/output.{format_type}"

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)

# DEBUG: check cookies content (optional, remove in production)
@app.route('/debug_cookies')
def debug_cookies():
    if os.path.exists('cookies.txt'):
        with open('cookies.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        return f"<pre>{content}</pre>"
    else:
        return "cookies.txt not found", 404

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    app.run(debug=True)
