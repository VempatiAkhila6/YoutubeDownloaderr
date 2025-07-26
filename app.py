from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp
import os
import ssl
import threading
import logging

app = Flask(__name__)
ssl._create_default_https_context = ssl._create_unverified_context

# Set up logging
logging.basicConfig(level=logging.INFO)

# Create cookies.txt from environment variable if exists
cookie_data = os.getenv('COOKIES_DATA')
if cookie_data:
    with open('cookies.txt', 'w') as f:
        f.write(cookie_data)
    app.logger.info("cookies.txt created from environment variable COOKIES_DATA.")
else:
    app.logger.warning("Environment variable COOKIES_DATA not found. Proceeding without cookies.txt.")

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

    cookie_path = os.path.join(os.getcwd(), 'cookies.txt')
    options = {
        'outtmpl': output_file,
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': '/usr/bin/ffmpeg',
    }

    # Use cookies only if cookies.txt exists
    if os.path.exists(cookie_path):
        options['cookies'] = cookie_path

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
                download_progress['status'] = 'Downloaded'
        except Exception as e:
            download_progress['error'] = str(e)
            download_progress['status'] = 'Error'

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
