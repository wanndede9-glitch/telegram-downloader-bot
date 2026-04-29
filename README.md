# 🚀 Nexus Downloader Bot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Railway](https://img.shields.io/badge/Railway-Deploy-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![yt-dlp](https://img.shields.io/badge/yt--dlp-Powered-FF0000?style=for-the-badge)

**A powerful Telegram bot to download media from 20+ platforms**

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎬 **Multi-Platform** | YouTube, TikTok, Instagram, Facebook, Twitter/X, SoundCloud, Vimeo, Twitch, Reddit & more |
| 🎯 **Quality Selection** | 4K, 1080p, 720p, 480p, 360p video + MP3 320/192/128kbps audio |
| ⚡ **Real-time Progress** | Live download progress bar with speed & ETA |
| 📊 **User Stats** | Track downloads per user per platform |
| 🎵 **Audio Extraction** | Extract MP3 from any video URL |
| 🔘 **Beautiful UI** | Rich inline keyboards and formatted messages |
| 📋 **Format Inspector** | `/formats <url>` shows all available qualities |

---

## 🚀 Deploy to Railway

### Step 1 — Create Bot Token

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Follow prompts, copy your **Bot Token**

### Step 2 — Deploy on Railway

**Option A: One-Click (GitHub)**

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → **New Project**
3. Select **Deploy from GitHub repo**
4. Choose your repo

**Option B: Railway CLI**

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Init & deploy
railway init
railway up
```

### Step 3 — Set Environment Variables

In Railway dashboard → your project → **Variables** tab:

```
BOT_TOKEN = your_telegram_bot_token_here
```

### Step 4 — Set Service Type

In Railway → your service → **Settings**:
- Change **Start Command** to: `python bot.py`
- Or it auto-reads from `Procfile`

---

## 🏠 Local Development

```bash
# Clone repo
git clone https://github.com/your-username/telegram-downloader-bot
cd telegram-downloader-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (required for audio)
# macOS:   brew install ffmpeg
# Ubuntu:  sudo apt install ffmpeg
# Windows: https://ffmpeg.org/download.html

# Setup environment
cp .env.example .env
# Edit .env and add your BOT_TOKEN

# Run bot
python bot.py
```

---

## 📱 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show main menu |
| `/help` | Detailed help guide |
| `/stats` | Your download statistics |
| `/formats <url>` | Show available formats for URL |
| `/cancel` | Cancel current download |

---

## 🎯 Supported Platforms

```
🎬 YouTube          📸 Instagram        🎵 TikTok
👥 Facebook         🐦 Twitter/X        🎧 SoundCloud
🎞 Vimeo            🎮 Twitch           🤖 Reddit
📹 Dailymotion      💜 Tumblr           📌 Pinterest
🌐 + 100s more via yt-dlp
```

---

## 📁 Project Structure

```
telegram-downloader-bot/
├── bot.py              # Main bot code
├── requirements.txt    # Python dependencies
├── railway.toml        # Railway configuration
├── nixpacks.toml       # Build config (includes ffmpeg)
├── Procfile            # Process definition
├── .env.example        # Environment variables template
├── .gitignore
└── README.md
```

---

## ⚙️ Configuration

All config is via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ Yes | — | Telegram bot token |

---

## 🛠 Tech Stack

- **[python-telegram-bot](https://python-telegram-bot.org/)** v21 — Telegram Bot API
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — Media downloader engine
- **FFmpeg** — Audio/video processing
- **Railway** — Cloud deployment

---

<div align="center">
Made with ❤️ | Powered by yt-dlp + python-telegram-bot
</div>
