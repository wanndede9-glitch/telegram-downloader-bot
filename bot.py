import os
import re
import time
import asyncio
import logging
import aiohttp
import aiofiles
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction

import yt_dlp
from PIL import Image
import io

# ─── Logging Setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
logger = logging.getLogger("DownloaderBot")

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DOWNLOAD_PATH = Path("downloads")
DOWNLOAD_PATH.mkdir(exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit

# ─── Platform Detection ───────────────────────────────────────────────────────
PLATFORM_PATTERNS = {
    "youtube":   (r"(?:youtube\.com|youtu\.be)", "🎬", "YouTube"),
    "tiktok":    (r"tiktok\.com", "🎵", "TikTok"),
    "instagram": (r"instagram\.com", "📸", "Instagram"),
    "facebook":  (r"(?:facebook\.com|fb\.watch)", "👥", "Facebook"),
    "twitter":   (r"(?:twitter\.com|x\.com)", "🐦", "Twitter/X"),
    "soundcloud":(r"soundcloud\.com", "🎧", "SoundCloud"),
    "vimeo":     (r"vimeo\.com", "🎞", "Vimeo"),
    "reddit":    (r"reddit\.com", "🤖", "Reddit"),
    "pinterest": (r"pinterest\.com", "📌", "Pinterest"),
    "twitch":    (r"twitch\.tv", "🎮", "Twitch"),
    "dailymotion":(r"dailymotion\.com", "📹", "Dailymotion"),
    "tumblr":    (r"tumblr\.com", "💜", "Tumblr"),
}

def detect_platform(url: str) -> tuple:
    for key, (pattern, emoji, name) in PLATFORM_PATTERNS.items():
        if re.search(pattern, url, re.I):
            return key, emoji, name
    return "generic", "🌐", "Web"

def is_valid_url(url: str) -> bool:
    try:
        r = urlparse(url)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except:
        return False

# ─── Progress Bar Helper ──────────────────────────────────────────────────────
def make_progress_bar(percent: float, width: int = 12) -> str:
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:.0f}%"

def human_size(b: int) -> str:
    for unit in ["B","KB","MB","GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def human_time(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    elif s < 3600:
        return f"{s/60:.0f}m {s%60:.0f}s"
    return f"{s/3600:.0f}h {(s%3600)/60:.0f}m"

# ─── Download Stats Tracker ───────────────────────────────────────────────────
user_stats: dict[int, dict] = {}

def update_stats(user_id: int, success: bool, platform: str):
    if user_id not in user_stats:
        user_stats[user_id] = {"total": 0, "success": 0, "fail": 0, "platforms": {}}
    user_stats[user_id]["total"] += 1
    if success:
        user_stats[user_id]["success"] += 1
    else:
        user_stats[user_id]["fail"] += 1
    user_stats[user_id]["platforms"][platform] = user_stats[user_id]["platforms"].get(platform, 0) + 1

# ─── Keyboards ───────────────────────────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Video", callback_data="mode_video"),
            InlineKeyboardButton("🎵 Audio", callback_data="mode_audio"),
        ],
        [
            InlineKeyboardButton("📸 Photo/GIF", callback_data="mode_photo"),
            InlineKeyboardButton("⚡ Auto", callback_data="mode_auto"),
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        ],
        [
            InlineKeyboardButton("⚙️ Quality", callback_data="quality_menu"),
        ]
    ])

def quality_keyboard(platform: str, mode: str) -> InlineKeyboardMarkup:
    if mode == "video":
        buttons = [
            [
                InlineKeyboardButton("🔴 4K / Best", callback_data=f"dl_best_{platform}"),
                InlineKeyboardButton("🟡 1080p", callback_data=f"dl_1080_{platform}"),
            ],
            [
                InlineKeyboardButton("🟢 720p", callback_data=f"dl_720_{platform}"),
                InlineKeyboardButton("🔵 480p", callback_data=f"dl_480_{platform}"),
            ],
            [
                InlineKeyboardButton("⚡ Fast (360p)", callback_data=f"dl_360_{platform}"),
                InlineKeyboardButton("🎵 Audio Only", callback_data=f"dl_audio_{platform}"),
            ],
            [InlineKeyboardButton("« Back", callback_data="back_main")]
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("🎵 MP3 320kbps", callback_data=f"dl_mp3_320_{platform}"),
                InlineKeyboardButton("🎵 MP3 192kbps", callback_data=f"dl_mp3_192_{platform}"),
            ],
            [
                InlineKeyboardButton("🎵 MP3 128kbps", callback_data=f"dl_mp3_128_{platform}"),
                InlineKeyboardButton("🎧 OGG Best", callback_data=f"dl_ogg_{platform}"),
            ],
            [InlineKeyboardButton("« Back", callback_data="back_main")]
        ]
    return InlineKeyboardMarkup(buttons)

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")
    ]])

# ─── User Sessions ────────────────────────────────────────────────────────────
user_sessions: dict[int, dict] = {}

# ─── Welcome Message ─────────────────────────────────────────────────────────
WELCOME_TEXT = """
╔══════════════════════════════════╗
║   🚀  **NEXUS DOWNLOADER BOT**   ║
╚══════════════════════════════════╝

ស្វាគមន៍! ខ្ញុំអាចទាញយកពី **20+ platforms**:

🎬 YouTube • TikTok • Instagram
📸 Facebook • Twitter/X • Reddit  
🎵 SoundCloud • Vimeo • Twitch
🌐 And many more...

**របៀបប្រើ:**
1️⃣ ផ្ញើ URL ណាមួយមក
2️⃣ ជ្រើសរើសទម្រង់ & គុណភាព
3️⃣ រៀបចំទទួល file! ✅

ចុចប៊ូតុងខាងក្រោម ឬ ផ្ញើ URL ផ្ទាល់! 👇
"""

HELP_TEXT = """
📖 **NEXUS BOT - Help Guide**

**📋 Commands:**
/start — Main menu
/help — This guide
/stats — Your download stats
/cancel — Cancel current download
/formats `<URL>` — Show available formats

**🎯 Supported Platforms:**
• 🎬 YouTube (video, shorts, playlists)
• 🎵 TikTok (with/without watermark)
• 📸 Instagram (posts, reels, stories)
• 👥 Facebook (videos, reels)
• 🐦 Twitter/X (videos, GIFs)
• 🎧 SoundCloud (tracks, playlists)
• 🎞 Vimeo (HD videos)
• 🎮 Twitch (clips, VODs)
• 🤖 Reddit (videos, GIFs)
• 📹 Dailymotion, Tumblr & more!

**⚡ Tips:**
• Send URL directly for auto-detect
• Use /formats to see all qualities
• Max file size: 50MB per Telegram limits
• Audio mode downloads MP3/OGG
"""

# ─── Core Download Function ───────────────────────────────────────────────────
async def download_media(
    url: str,
    quality: str,
    mode: str,
    progress_callback=None
) -> dict:
    """Download media and return info dict."""

    output_tmpl = str(DOWNLOAD_PATH / "%(title).50s.%(ext)s")
    result = {"success": False, "files": [], "title": "", "duration": 0, "thumbnail": ""}

    if mode == "audio" or quality.startswith("mp3") or quality.startswith("ogg"):
        bitrate = "320" if "320" in quality else "192" if "192" in quality else "128"
        fmt = "bestaudio/best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": bitrate,
        }]
        ydl_opts = {
            "format": fmt,
            "outtmpl": output_tmpl,
            "postprocessors": postprocessors,
            "quiet": True,
            "no_warnings": True,
        }
    else:
        quality_map = {
            "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
            "720":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
            "480":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
            "360":  "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
            "audio":"bestaudio/best",
        }
        fmt = quality_map.get(quality, "best[ext=mp4]/best")
        ydl_opts = {
            "format": fmt,
            "outtmpl": output_tmpl,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }

    if progress_callback:
        last_update = [0]
        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed", 0) or 0
                eta = d.get("eta", 0) or 0
                if total > 0:
                    pct = downloaded / total * 100
                    if pct - last_update[0] >= 5:
                        last_update[0] = pct
                        asyncio.run_coroutine_threadsafe(
                            progress_callback(pct, human_size(downloaded), human_size(total),
                                              human_size(speed)+"/s", human_time(eta)),
                            asyncio.get_event_loop()
                        )
        ydl_opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            result["title"] = info.get("title", "Unknown")
            result["duration"] = info.get("duration", 0)
            result["thumbnail"] = info.get("thumbnail", "")
            result["uploader"] = info.get("uploader", "")
            result["view_count"] = info.get("view_count", 0)

            filename = ydl.prepare_filename(info)
            # Handle audio extraction rename
            for ext in [".mp3", ".ogg", ".m4a", ".webm", ".mp4", ".mkv"]:
                candidate = Path(filename).with_suffix(ext)
                if candidate.exists():
                    result["files"].append(str(candidate))
                    break
            else:
                # Try to find by stem
                stem = Path(filename).stem
                for f in DOWNLOAD_PATH.glob(f"{stem[:30]}*"):
                    result["files"].append(str(f))
                    break

            result["success"] = bool(result["files"])
    except Exception as e:
        result["error"] = str(e)

    return result

# ─── Handlers ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
        ]])
    )

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    stats = user_stats.get(uid, {})
    total = stats.get("total", 0)
    success = stats.get("success", 0)
    fail = stats.get("fail", 0)
    platforms = stats.get("platforms", {})

    platform_lines = "\n".join(
        f"  {PLATFORM_PATTERNS.get(p, ('','🌐',''))[1]} {PLATFORM_PATTERNS.get(p, ('','',p))[2]}: **{c}**"
        for p, c in sorted(platforms.items(), key=lambda x: -x[1])[:5]
    ) or "  _(none yet)_"

    rate = f"{success/total*100:.0f}%" if total else "N/A"
    text = f"""
📊 **Your Download Stats**

✅ Success: **{success}**
❌ Failed: **{fail}**
📦 Total: **{total}**
🎯 Success Rate: **{rate}**

🏆 **Top Platforms:**
{platform_lines}
"""
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
        ]])
    )

async def cmd_formats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Usage: `/formats <URL>`\n\nExample:\n`/formats https://youtu.be/dQw4w9WgXcQ`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    url = ctx.args[0]
    if not is_valid_url(url):
        await update.message.reply_text("❌ Invalid URL!")
        return

    msg = await update.message.reply_text("⏳ Fetching available formats...")

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        video_fmts = [f for f in formats if f.get("vcodec") != "none" and f.get("height")]
        audio_fmts = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]

        # Deduplicate by height
        seen_h = set()
        video_lines = []
        for f in sorted(video_fmts, key=lambda x: -(x.get("height") or 0)):
            h = f.get("height")
            if h and h not in seen_h:
                seen_h.add(h)
                size = f.get("filesize") or f.get("filesize_approx") or 0
                sz = f" (~{human_size(size)})" if size else ""
                video_lines.append(f"  🎬 {h}p{sz}")

        audio_lines = []
        for f in audio_fmts[:4]:
            abr = f.get("abr", 0)
            ext = f.get("ext", "?")
            audio_lines.append(f"  🎵 {ext.upper()} {abr:.0f}kbps" if abr else f"  🎵 {ext.upper()}")

        title = info.get("title", "Unknown")[:50]
        dur = human_time(info.get("duration", 0))

        text = f"""
🎯 **Available Formats**

📌 **{title}**
⏱ Duration: `{dur}`

**📹 Video Qualities:**
{chr(10).join(video_lines) or '  _(none)_'}

**🎵 Audio Formats:**
{chr(10).join(audio_lines) or '  _(none)_'}

_Use buttons below to download!_
"""
        _, emoji, platform_name = detect_platform(url)
        user_sessions[update.effective_user.id] = {"url": url, "platform": platform_name}

        await msg.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=quality_keyboard("saved", "video")
        )
    except Exception as e:
        await msg.edit_text(f"❌ Could not fetch formats:\n`{str(e)[:200]}`", parse_mode=ParseMode.MARKDOWN)

async def handle_url_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = re.findall(r'https?://[^\s]+', text)

    if not urls:
        await update.message.reply_text(
            "🤔 No valid URL found.\n\nSend a URL to download, or use /help for help!",
            reply_markup=main_menu_keyboard()
        )
        return

    url = urls[0]
    platform_key, emoji, platform_name = detect_platform(url)
    user_sessions[update.effective_user.id] = {"url": url, "platform": platform_key}

    text_reply = f"""
{emoji} **{platform_name}** link detected!

🔗 `{url[:60]}{'...' if len(url)>60 else ''}`

**Select download format:**
"""
    await update.message.reply_text(
        text_reply,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=quality_keyboard(platform_key, "video")
    )

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id

    # ── Navigation ──
    if data == "back_main":
        await query.edit_message_text(
            WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )
        return

    if data == "help":
        await query.edit_message_text(
            HELP_TEXT, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
            ]])
        )
        return

    if data == "my_stats":
        stats = user_stats.get(uid, {})
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        fail = stats.get("fail", 0)
        rate = f"{success/total*100:.0f}%" if total else "N/A"
        await query.edit_message_text(
            f"📊 **Stats**\n\n✅ {success} Success\n❌ {fail} Failed\n📦 {total} Total\n🎯 {rate} Rate",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
            ]])
        )
        return

    if data == "quality_menu":
        await query.edit_message_text(
            "⚙️ **Quality Settings**\n\nFirst send a URL, then choose quality!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
            ]])
        )
        return

    if data.startswith("mode_"):
        mode = data.split("_")[1]
        ctx.user_data["mode"] = mode
        mode_labels = {"video":"🎬 Video","audio":"🎵 Audio","photo":"📸 Photo","auto":"⚡ Auto"}
        await query.edit_message_text(
            f"✅ Mode set to **{mode_labels.get(mode, mode)}**!\n\nNow send your URL 👇",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
            ]])
        )
        return

    if data == "cancel_download":
        ctx.user_data.pop("downloading", None)
        await query.edit_message_text("❌ Download cancelled.")
        return

    # ── Download Actions ──
    if data.startswith("dl_"):
        session = user_sessions.get(uid)
        if not session:
            await query.edit_message_text(
                "⚠️ Session expired. Please send your URL again!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
                ]])
            )
            return

        url = session["url"]
        parts = data[3:].split("_", 1)
        quality = parts[0]
        mode = "audio" if quality in ("audio","mp3","ogg") else "video"

        # Show downloading UI
        start_time = time.time()
        prog_msg = await query.edit_message_text(
            f"⚡ **Starting Download...**\n\n"
            f"🔗 Platform: **{session['platform']}**\n"
            f"⏳ Initializing...\n\n"
            f"{make_progress_bar(0)}\n\n"
            f"_Please wait..._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_keyboard()
        )

        last_edit = [time.time()]

        async def progress_cb(pct, done, total, speed, eta):
            now = time.time()
            if now - last_edit[0] < 2:
                return
            last_edit[0] = now
            elapsed = human_time(now - start_time)
            try:
                await prog_msg.edit_text(
                    f"⬇️ **Downloading...**\n\n"
                    f"🔗 Platform: **{session['platform']}**\n"
                    f"📦 {done} / {total}\n"
                    f"⚡ Speed: {speed}\n"
                    f"⏱ ETA: {eta}  │  Elapsed: {elapsed}\n\n"
                    f"{make_progress_bar(pct)}\n",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=cancel_keyboard()
                )
            except:
                pass

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: asyncio.run(download_media(url, quality, mode))
        )

        # Workaround: run download in thread properly
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _sync_download(url, quality, mode)
        )

        update_stats(uid, result["success"], session.get("platform","generic"))
        elapsed_total = human_time(time.time() - start_time)

        if not result["success"]:
            err = result.get("error", "Unknown error")[:300]
            await prog_msg.edit_text(
                f"❌ **Download Failed**\n\n"
                f"```\n{err}\n```\n\n"
                f"⏱ Time: {elapsed_total}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Try Again", callback_data=data),
                    InlineKeyboardButton("🏠 Menu", callback_data="back_main")
                ]])
            )
            return

        # Upload file
        filepath = result["files"][0]
        file_size = Path(filepath).stat().st_size
        title = result.get("title", "Download")[:50]
        duration = result.get("duration", 0)
        uploader = result.get("uploader", "")

        if file_size > MAX_FILE_SIZE:
            await prog_msg.edit_text(
                f"⚠️ **File Too Large!**\n\n"
                f"📦 Size: **{human_size(file_size)}**\n"
                f"📏 Limit: **50 MB**\n\n"
                f"Try a lower quality! 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=quality_keyboard(session["platform"], mode)
            )
            Path(filepath).unlink(missing_ok=True)
            return

        await prog_msg.edit_text(
            f"📤 **Uploading...**\n\n"
            f"📄 **{title}**\n"
            f"📦 Size: {human_size(file_size)}\n"
            f"⏱ Download took: {elapsed_total}\n\n"
            f"{make_progress_bar(100)} ✅",
            parse_mode=ParseMode.MARKDOWN
        )

        caption = (
            f"✅ **{title}**\n"
            f"{'👤 ' + uploader + chr(10) if uploader else ''}"
            f"{'⏱ Duration: ' + human_time(duration) + chr(10) if duration else ''}"
            f"📦 Size: {human_size(file_size)}\n"
            f"🌐 via **Nexus Downloader Bot**"
        )

        try:
            with open(filepath, "rb") as f:
                if mode == "audio" or filepath.endswith(".mp3"):
                    await update.effective_chat.send_audio(
                        audio=f, caption=caption, parse_mode=ParseMode.MARKDOWN,
                        title=title, duration=duration
                    )
                else:
                    await update.effective_chat.send_video(
                        video=f, caption=caption, parse_mode=ParseMode.MARKDOWN,
                        duration=duration, supports_streaming=True
                    )
            await prog_msg.delete()
        except Exception as e:
            await prog_msg.edit_text(
                f"❌ Upload failed: `{str(e)[:200]}`",
                parse_mode=ParseMode.MARKDOWN
            )
        finally:
            Path(filepath).unlink(missing_ok=True)

        # Show success menu
        await update.effective_chat.send_message(
            f"🎉 **Done!** Download complete.\n\nDownload another one? 👇",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )


def _sync_download(url: str, quality: str, mode: str) -> dict:
    """Synchronous wrapper for yt-dlp."""
    output_tmpl = str(DOWNLOAD_PATH / "%(title).50s.%(ext)s")
    result = {"success": False, "files": [], "title": "", "duration": 0}

    if mode == "audio" or quality in ("mp3", "ogg", "audio"):
        bitrate = "320" if "320" in quality else "192" if "192" in quality else "128"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_tmpl,
            "postprocessors": [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":bitrate}],
            "quiet": True, "no_warnings": True,
        }
    else:
        quality_map = {
            "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]",
            "720":  "bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]",
            "480":  "bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480]",
            "360":  "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]",
        }
        fmt = quality_map.get(quality, "best[ext=mp4]/best")
        ydl_opts = {
            "format": fmt,
            "outtmpl": output_tmpl,
            "quiet": True, "no_warnings": True,
            "merge_output_format": "mp4",
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            result["title"] = info.get("title","Unknown")
            result["duration"] = info.get("duration", 0)
            result["uploader"] = info.get("uploader","")

            filename = ydl.prepare_filename(info)
            for ext in [".mp3",".ogg",".m4a",".webm",".mp4",".mkv",".flv"]:
                candidate = Path(filename).with_suffix(ext)
                if candidate.exists():
                    result["files"].append(str(candidate))
                    break

            if not result["files"]:
                stem = Path(filename).stem[:30]
                for f in sorted(DOWNLOAD_PATH.glob(f"*")):
                    if stem.lower()[:15] in f.name.lower():
                        result["files"].append(str(f))
                        break

            result["success"] = bool(result["files"])
    except Exception as e:
        result["error"] = str(e)

    return result

# ─── Error Handler ────────────────────────────────────────────────────────────
async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {ctx.error}", exc_info=ctx.error)

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("formats", cmd_formats))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Errors
    app.add_error_handler(error_handler)

    logger.info("🚀 Nexus Downloader Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
