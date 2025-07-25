from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp
import os
import ssl
import threading
import time
import glob
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

ssl._create_default_https_context = ssl._create_unverified_context

# Global variables for progress tracking
download_progress = {"percentage": 0, "status": "", "error": ""}

def download_progress_hook(d):
    global download_progress
    app.logger.debug(f"Progress hook: {d}")
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '0%').replace('%', '')
        try:
            download_progress['percentage'] = float(progress)
        except ValueError:
            download_progress['percentage'] = 0
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
    
    try:
        url = request.form.get('url')
        format_type = request.form.get('format')
        resolution = request.form.get('resolution', '720p').replace('p', '')

        if not url:
            download_progress['error'] = 'No URL provided'
            app.logger.error('No URL provided in download request')
            return jsonify(download_progress), 400

        output_file = f"downloads/output.{format_type}"
        if os.path.exists(output_file):
            os.remove(output_file)

        options = {
            'outtmpl': 'downloads/output.%(ext)s',
            'noplaylist': True,
            'progress_hooks': [download_progress_hook],
            'ffmpeg_location': '/usr/bin/ffmpeg',
        }

        if format_type == 'mp4':
            options['format'] = f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]'
            options['postprocessors'] = [{
                'key': 'FFmpegVideoRemuxer',
                'preferedformat': 'mp4',
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
                app.logger.error(f"Download error: {str(e)}")
                download_progress['error'] = str(e)

        threading.Thread(target=download_thread, daemon=True).start()
        app.logger.info(f"Started download for URL: {url}, format: {format_type}")
        return jsonify({"status": "started"}), 200

    except Exception as e:
        app.logger.error(f"Unexpected error in /download: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/progress')
def progress():
    try:
        global download_progress
        app.logger.debug(f"Progress requested: {download_progress}")
        return jsonify(download_progress), 200
    except Exception as e:
        app.logger.error(f"Error in /progress: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/download_file')
def download_file():
    try:
        global download_progress
        if download_progress.get('status') != 'Downloaded':
            app.logger.error("Download not complete")
            return jsonify({"error": "Download not complete"}), 400

        format_type = request.args.get('format', 'mp4')
        file_path = f"downloads/output.{format_type}"
        if not os.path.exists(file_path):
            app.logger.error(f"File not found: {file_path}")
            return jsonify({"error": "File not found"}), 404

        response = send_file(file_path, as_attachment=True)
        # Cleanup files older than 1 hour
        for file in glob.glob("downloads/output.*"):
            if os.path.getmtime(file) < time.time() - 3600:
                os.remove(file)
        app.logger.info(f"File sent: {file_path}")
        return response

    except Exception as e:
        app.logger.error(f"Error in /download_file: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    app.run(debug=True)
