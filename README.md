# 🎬 AI-Parser & Analyzer Instagram Reels (Apple Silicon MLX)

App locally scans reels for the current year (up lo 350 posts), filters Top-25 by views, downloads metadata and runs Whisper Turbo transcription with timestamps.

---

## 🚥 Features

- ✍️ One-click Desktop launcher with native macOS dialog.
- 📄 Up-to-year depth scan (up to 350 reels).
- 🌐 auto-login via Google Chrome profile session.
- timestamped Whisper Turbo audio transcription locally on Apple Silicon.
- 📦 Complete metadata: views, likes, comments, dates, full captions.
- 📶 Automatically generates Markdown report in outputs/.

---

## 🏦 Quick Start

1. Install system dependencies:
   brew install ffmpeg

2. Setup environment:
   git clone https://github.com/alkorider932/reels-parser-ai.git
   cd reels-parser-ai
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt

3. One-time authorization:
   ./venv/bin/python3 login_instagram.py

4. Run via Desktop icon or terminal:
   ./venv/bin/python3 analyze_competitor.py "https://www.instagram.com/username/"
