import os
import logging
from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp
import os
import ssl
import threading
import time
import glob

app = Flask(__name__)
ssl._create_default_https_context = ssl._create_unverified_context

# Set up logging
logging.basicConfig(level=logging.INFO)

# Track download progress
download_progress = {"percentage": 0, "status": "", "error": "", "title": ""}

def progress_hook(d):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0.0%').replace('%', '')
        try:
            download_progress['percentage'] = float(p)
        except ValueError:
            download_progress['percentage'] = 0
    elif d['status'] == 'finished':
        download_progress['status'] = 'Downloaded'
        download_progress['percentage'] = 100

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    global download_progress
    download_progress = {"percentage": 0, "status": "", "error": "", "title": ""}

    url = request.form.get('url')
    format_type = request.form.get('format', 'mp4')
    resolution = request.form.get('resolution', '720p').replace('p', '')

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    output_file = f"downloads/output.{format_type}"
    os.makedirs('downloads', exist_ok=True)
    if os.path.exists(output_file):
        os.remove(output_file)

    # Retrieve the cookies from the environment variable
    cookies_data = os.getenv('COOKIES_DATA')

    if cookies_data:
        # Save cookies data to cookies.txt
        with open('cookies.txt', 'w') as f:
            f.write(cookies_data)
        logging.info("Cookies data successfully written to cookies.txt")
    else:
        logging.error("COOKIES_DATA environment variable not set")

    # yt-dlp options
    options = {
        'cookies': 'cookies.txt',
        'outtmpl': output_file,
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': '/usr/bin/ffmpeg',
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
                info = ydl.extract_info(url, download=True)
                download_progress['title'] = info.get('title', 'Downloaded File')
        except Exception as e:
            download_progress['error'] = str(e)

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({"status": "started"}), 200

@app.route('/progress')
def progress():
    return jsonify(download_progress)

@app.route('/download_file')
def download_file():
    format_type = request.args.get('format', 'mp4')
    file_path = f"downloads/output.{format_type}"
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    app.run(debug=True)
