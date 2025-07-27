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
import ffmpeg

app = Flask(__name__, static_folder='static')
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
progress_store = {}

def clean_youtube_url(url):
    """Remove playlist and other parameters from YouTube URL."""
    match = re.match(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11}))', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(2)}"
    return url

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
            return jsonify({"error": "No URL provided. Please enter a valid YouTube URL."}), 400
        cleaned_url = clean_youtube_url(url)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo[height<=720]+bestaudio/best',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(cleaned_url, download=False)
            if not info or info.get('is_private') or info.get('availability') == 'private':
                return jsonify({
                    "error": "This video is unavailable, private, or restricted. Try a different video or check if cookies are required."
                }), 400
            duration = str(timedelta(seconds=int(info.get('duration', 0))))
            return jsonify({
                "title": info.get('title', 'Unknown Title'),
                "duration": duration,
                "thumbnail": info.get('thumbnail', '') or ''
            })
    except yt_dlp.utils.DownloadError as e:
        logging.error(f"Video info error for {url}: {str(e)}")
        return jsonify({"error": f"Video is unavailable or restricted: {str(e)}"}), 400
    except Exception as e:
        logging.error(f"Unexpected error in /video_info for {url}: {str(e)}")
        return jsonify({"error": "Failed to fetch video info. Please try again later."}), 500

@app.route('/download', methods=['POST'])
def download():
    try:
        session_id = str(time.time())
        progress_store[session_id] = {"percentage": 0, "status": "Initializing", "error": "", "title": ""}
        url = request.form.get('url')
        format_type = request.form.get('format', 'mp4')
        resolution = request.form.get('resolution', '720p').replace('p', '')
        if not url:
            progress_store[session_id]['error'] = 'No URL provided'
            return jsonify({"error": "No URL provided. Please enter a valid YouTube URL.", "session_id": session_id}), 400
        cleaned_url = clean_youtube_url(url)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'format': f'bestvideo[height<={resolution}]+bestaudio/best',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(cleaned_url, download=False)
            if not info or info.get('is_private') or info.get('availability') == 'private':
                progress_store[session_id]['error'] = 'Video is unavailable, private, or restricted'
                return jsonify({
                    "error": "This video is unavailable, private, or restricted. Try a different video or check if cookies are required.",
                    "session_id": session_id
                }), 400
            progress_store[session_id]['title'] = info.get('title', 'Downloaded File')
        cookies_data = os.getenv('COOKIES_DATA')
        if cookies_data:
            with open('cookies.txt', 'w') as f:
                f.write(cookies_data)
            logging.info("Cookies data written to cookies.txt")
        output_file = f"downloads/{session_id}.{format_type}"
        os.makedirs('downloads', exist_ok=True)
        if os.path.exists(output_file):
            os.remove(output_file)
        options = {
            'outtmpl': output_file,
            'noplaylist': True,
            'progress_hooks': [lambda d: progress_hook(d, session_id)],
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        }
        try:
            ffmpeg_path = shutil.which('ffmpeg')
            if not ffmpeg_path:
                raise RuntimeError("FFmpeg not found in system PATH")
            options['ffmpeg_location'] = ffmpeg_path
        except Exception as e:
            logging.error(f"FFmpeg error: {str(e)}")
            progress_store[session_id]['error'] = 'FFmpeg is not installed or not found'
            return jsonify({"error": "Server error: FFmpeg is not installed or not found", "session_id": session_id}), 500
        if format_type == 'mp4':
            options['format'] = f'bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/best[height<={resolution}]'
            options['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        else:
            options['format'] = 'bestaudio[ext=m4a]'
            options['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        def download_thread():
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([cleaned_url])
            except yt_dlp.utils.DownloadError as e:
                logging.error(f"Download failed for {cleaned_url}: {str(e)}")
                progress_store[session_id]['error'] = f"Download failed: {str(e)}"
                progress_store[session_id]['status'] = 'Error'
            except Exception as e:
                logging.error(f"Unexpected download error for {cleaned_url}: {str(e)}")
                progress_store[session_id]['error'] = f"Unexpected error: {str(e)}"
                progress_store[session_id]['status'] = 'Error'
        Thread(target=download_thread, daemon=True).start()
        logging.info(f"Started download for {cleaned_url}, format: {format_type}, session: {session_id}")
        return jsonify({"status": "started", "session_id": session_id}), 200
    except yt_dlp.utils.DownloadError as e:
        logging.error(f"Download error for {url}: {str(e)}")
        progress_store[session_id]['error'] = f"Video is unavailable or restricted: {str(e)}"
        return jsonify({"error": f"Video is unavailable or restricted: {str(e)}", "session_id": session_id}), 400
    except Exception as e:
        logging.error(f"Unexpected error in /download for {url}: {str(e)}")
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
        title = progress_store[session_id].get('title', 'Downloaded File').replace('/', '_').replace('\\', '').replace(':', '_').replace('?', '_').replace('*', '_')
        response = send_file(file_path, as_attachment=True, download_name=f"{title}.{format_type}")
        def cleanup_file(path):
            time.sleep(300)  # 5 minutes
            if os.path.exists(path):
                os.remove(path)
                logging.info(f"Cleaned up file: {path}")
                progress_store.pop(session_id, None)
        Thread(target=cleanup_file, args=(file_path,), daemon=True).start()
        logging.info(f"Serving file: {file_path}")
        return response
    except Exception as e:
        logging.error(f"Error serving file: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    os.makedirs('downloads', exist_ok=True)
    port = int(os.getenv('PORT', 5000))  # Use Render's PORT env var
    app.run(debug=False, host='0.0.0.0', port=port)
