YouTube Downloader
A web-based YouTube downloader that allows users to download videos (MP4) or audio (MP3) by pasting a YouTube URL.
Access the Web App

Visit: https://youtubedownloaderr.onrender.com
Enter a YouTube URL, select MP3 or MP4, choose a resolution (for MP4), and click Download.
Note: The free tier may have a ~50-second delay on first access due to spin-down.

Desktop GUI (Alternative)
For a desktop version with full MP3/MP4 support:

Clone this repository: git clone https://github.com/VempatiAkhila6/YoutubeDownloaderr.git
Install Python 3.10+: python.org
Install FFmpeg: ffmpeg.org
Install dependencies: pip install yt-dlp customtkinter
Update the ffmpeg_path in YOU.py to your local FFmpeg installation.
Run: python YOU.py

Local Development (Web App)
To run the web app locally:

Clone this repository: git clone https://github.com/VempatiAkhila6/YoutubeDownloaderr.git
Install Python 3.10+: python.org
Install FFmpeg: ffmpeg.org
Install dependencies: pip install -r requirements.txt
Run: python app.py
Open http://localhost:5000 in your browser.

Legal Notice

Use this tool responsibly and respect YouTube’s Terms of Service.
Downloading copyrighted content without permission may violate laws in your region.

Contributing
Fork this repository and submit pull requests to improve the tool!
Troubleshooting

Deployment Errors: Ensure requirements.txt has one dependency per line and PYTHON_VERSION is set to 3.10.12.
FFmpeg Issues: Verify FFmpeg is installed (ffmpeg -version) and the path is correct in app.py or YOU.py.
Spin-Down Delays: The free tier may delay first access by ~50 seconds. Consider a paid plan for better performance.
Report issues via GitHub Issues.
