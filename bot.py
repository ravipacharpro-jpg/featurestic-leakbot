import os
import time
import threading
import urllib.request

import telebot
from telebot.types import (
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

ALBUM_WAIT = 2.5
FILE_CAPTION = "<b>Join @FeaturesticLeak</b>"
CAPTION_PARSE_MODE = "HTML"
lock = threading.Lock()
pending_albums = {}
recently_sent = {}


def get_file_caption(msg):
    """Caption for every document/file, never for photos or videos"""
    if msg.document:
        return FILE_CAPTION
    return None


def send_single(msg):
    caption = get_file_caption(msg)
    kwargs = {"caption": caption, "parse_mode": CAPTION_PARSE_MODE} if caption else {}
    if msg.document:
        bot.send_document(CHANNEL_ID, msg.document.file_id, **kwargs)
    elif msg.video:
        bot.send_video(CHANNEL_ID, msg.video.file_id, **kwargs)
    elif msg.photo:
        bot.send_photo(CHANNEL_ID, msg.photo[-1].file_id, **kwargs)
    elif msg.audio:
        bot.send_audio(CHANNEL_ID, msg.audio.file_id, **kwargs)
    elif msg.voice:
        bot.send_voice(CHANNEL_ID, msg.voice.file_id, **kwargs)


def to_input_media(msg):
    if msg.document:
        return InputMediaDocument(msg.document.file_id)
    if msg.video:
        return InputMediaVideo(msg.video.file_id)
    if msg.photo:
        return InputMediaPhoto(msg.photo[-1].file_id)
    if msg.audio:
        return InputMediaAudio(msg.audio.file_id)
    return None


@bot.message_handler(commands=["start"])
def send_start(message):
    bot.reply_to(message, "Bot online. Single ya album media forward karo, main channel pe upload kar dunga.")


@bot.message_handler(content_types=["document", "video", "photo", "audio", "voice"])
def handle_media(message):
    gid = message.media_group_id

    if not gid:
        try:
            send_single(message)
            bot.reply_to(message, "✅ Uploaded to channel!")
        except Exception as e:
            bot.reply_to(message, f"❌ Failed: {e}")
        return

    now = time.time()
    with lock:
        for old in [k for k, t in recently_sent.items() if now - t > 10]:
            recently_sent.pop(old, None)
        if gid in recently_sent:
            return
        pending_albums.setdefault(gid, []).append(message)
        is_first = len(pending_albums[gid]) == 1

    if not is_first:
        return

    time.sleep(ALBUM_WAIT)

    with lock:
        items = pending_albums.pop(gid, [])
    if not items:
        return

    medias = []
    for m in items:
        im = to_input_media(m)
        if im is not None and im not in medias:
            medias.append(im)
    if not medias:
        return

    # send_media_group() has no `caption` argument. Telegram only shows a
    # caption on the first item, so set it on that InputMedia object.
    first_file_caption = get_file_caption(items[0]) if items else None
    if first_file_caption:
        medias[0].caption = first_file_caption
        medias[0].parse_mode = CAPTION_PARSE_MODE

    recently_sent[gid] = time.time()
    try:
        bot.send_media_group(CHANNEL_ID, medias)
        bot.reply_to(items[0], f"✅ Album uploaded as one post ({len(medias)} media)!")
    except Exception as e:
        bot.reply_to(items[0], f"❌ Failed: {e}")


def run_polling():
    """Keep polling forever. Render restarts the process if it ever exits."""
    while True:
        try:
            print("Bot polling started...", flush=True)
            bot.polling(none_stop=True, interval=2, timeout=40)
        except Exception as e:
            print(f"Re-polling due to: {e}", flush=True)
            time.sleep(5)


def keep_alive():
    """Free Render web services sleep after 15 min idle. Ping ourselves every 9 min."""
    if not PUBLIC_URL:
        return
    while True:
        time.sleep(540)
        try:
            with urllib.request.urlopen(PUBLIC_URL + "/health", timeout=10) as r:
                print(f"Keep-alive: {r.status}", flush=True)
        except Exception as e:
            print(f"Keep-alive failed: {e}", flush=True)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Bot alive".encode("utf-8"))

    def log_message(self, *args):
        pass  # keep logs clean


if __name__ == "__main__":
    threading.Thread(target=run_polling, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    print(f"Health server on 0.0.0.0:{PORT} (public: {PUBLIC_URL or 'n/a'})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()
