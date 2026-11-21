import os
import time
import threading

import telebot
from telebot.types import (
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

bot = telebot.TeleBot(BOT_TOKEN)

ALBUM_WAIT = 2.5
lock = threading.Lock()
pending_albums = {}
recently_sent = {}


def get_zip_caption(msg):
    """Return caption only for ZIP files, None otherwise"""
    if msg.document and msg.document.file_name:
        name = msg.document.file_name.lower()
        if name.endswith('.zip'):
            return "Join @FeaturesticLeak"
    return None


def send_single(msg):
    caption = get_zip_caption(msg)
    if msg.document:
        bot.send_document(CHANNEL_ID, msg.document.file_id, caption=caption)
    elif msg.video:
        bot.send_video(CHANNEL_ID, msg.video.file_id, caption=caption)
    elif msg.photo:
        bot.send_photo(CHANNEL_ID, msg.photo[-1].file_id, caption=caption)
    elif msg.audio:
        bot.send_audio(CHANNEL_ID, msg.audio.file_id, caption=caption)
    elif msg.voice:
        bot.send_voice(CHANNEL_ID, msg.voice.file_id, caption=caption)


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

    recently_sent[gid] = time.time()
    try:
        # Use caption only if first item is a ZIP file
        first_zip_caption = get_zip_caption(items[0]) if items else None
        bot.send_media_group(CHANNEL_ID, medias, caption=first_zip_caption)
        bot.reply_to(items[0], f"✅ Album uploaded as one post ({len(medias)} media)!")
    except Exception as e:
        bot.reply_to(items[0], f"❌ Failed: {e}")


if __name__ == "__main__":
    start_time = time.time()
    while time.time() - start_time < 16200:
        try:
            bot.polling(none_stop=True, interval=2, timeout=40)
        except Exception as e:
            print(f"Re-polling due to: {e}", flush=True)
            time.sleep(5)