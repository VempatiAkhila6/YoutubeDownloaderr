from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp
import os
import ssl
import threading
import time
import glob

app = Flask(__name__)

ssl._create_default_https_context = ssl._create_unverified_context

# Global variables for progress tracking
download_progress = {"percentage": 0, "status": "", "error": ""}

def download_progress_hook(d):
    global download_progress
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '0%').replace('%', '')
        try:
            download_progress['percentage'] = float(progress)
        except ValueError:
            pass
    elif d['status'] == 'finished':
        download_progress['percentage'] = 100
        download_progress['status'] = 'Downloaded'
    elif d['status'] == 'error':
        download_progress['error'] = 'Download failed'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    global download_progress
    download_progress = {"percentage": 0, "status": "", "error": ""}
    
    url = request.form.get('url')
    format_type = request.form.get('format')
    resolution = request.form.get('resolution', '720p').replace('p', '')

    if not url:
        download_progress['error'] = 'No URL provided'
        return jsonify(download_progress)

    output_file = f"downloads/output.{format_type}"
    if os.path.exists(output_file):
        os.remove(output_file)

    options = {
        'outtmpl': 'downloads/output.%(ext)s',
        'noplaylist': True,
        'progress_hooks': [download_progress_hook],
        'ffmpeg_location': '/usr/bin/ffmpeg',  # Render's FFmpeg path
    }

    if format_type == 'mp4':
        options['format'] = f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]'
        options['postprocessors'] = [{
            'key': 'FFmpegVideoRemuxer',
            'preferedformat': 'mp4',  # Corrected for MP4 remuxing
        }]
    else:  # mp3
        options['format'] = 'bestaudio/best'
        options['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    def download_thread():
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as e:
            download_progress['error'] = str(e)

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/progress')
def progress():
    global download_progress
    return jsonify(download_progress)

@app.route('/download_file')
def download_file():
    global download_progress
    if download_progress.get('status') == 'Downloaded':
        format_type = request.args.get('format', 'mp4')
        file_path = f"downloads/output.{format_type}"
        if os.path.exists(file_path):
            response = send_file(file_path, as_attachment=True)
            # Cleanup files older than 1 hour
            for file in glob.glob("downloads/output.*"):
                if os.path.getmtime(file) < time.time() - 3600:
                    os.remove(file)
            return response
        else:
            return jsonify({"error": "File not found"}), 404
    return jsonify({"error": "Download not complete"}), 400

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    app.run(debug=True)
