import os
import re
import asyncio
import requests
import yt_dlp
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ChatAction

# ============ إعدادات البوت ============

BOT_TOKEN = "8502627092:AAEdShsL9gz6OMaRNBHZ3HznrnmdtkwDa3o"  # ضع التوكن هناimport os
import asyncio
import requests
import yt_dlp
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ChatAction

# ============ إعدادات البوت ============

# التوكن الآن من متغير بيئة (Environment Variable)


if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود في متغيرات البيئة! تأكد من إضافته في Railway.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv")

# منصات محظورة (محميّة/مدفوعة)
BLOCKED_DOMAINS = [
    "netflix.com",
    "shahid.net",
    "shahed4u",
    "osn.com",
    "disneyplus.com",
    "amazon.com",
    "hbomax.com",
]

# إعدادات yt-dlp
ydl_opts = {
    "format": "best[height<=720][filesize<50M]/best[height<=480]/best[height<=360]",
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 30,
    "retries": 5,
    "fragment_retries": 5,
    "extract_flat": False,
    "noplaylist": True,
}


def looks_like_direct_video(url: str) -> bool:
    """
    يتحقق إن كان الرابط ينتهي بامتداد فيديو مباشر (mp4/webm/mov/mkv)
    """
    base = url.split("?", 1)[0].lower()
    return base.endswith(VIDEO_EXTS)


def is_blocked_domain(url: str) -> bool:
    """
    يتحقق إن كان الرابط من ضمن الدومينات المحظورة في BLOCKED_DOMAINS
    """
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return any(b in hostname for b in BLOCKED_DOMAINS)
    except Exception:
        return False


def get_video_info(url: str) -> dict:
    """
    يستخرج معلومات الفيديو باستخدام yt-dlp بدون تحميل
    """
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "success": True,
                "title": info.get("title", "فيديو"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "غير معروف"),
                "view_count": info.get("view_count", 0),
                "thumbnail": info.get("thumbnail", ""),
                "url": info.get("url"),          # stream / direct URL
                "ext": info.get("ext", "mp4"),
                "filesize": info.get("filesize"),
                "webpage_url": info.get("webpage_url", url),
            }
    except Exception as e:
        print(f"Video extract error: {e}")
        return {"success": False, "error": str(e)}


def get_direct_video_url(url: str) -> dict:
    """
    دالة ديناميكية:
    - لو الرابط ملف فيديو مباشر → type = direct
    - غير ذلك → تحاول yt-dlp على أي منصة غير محظورة
    """
    if looks_like_direct_video(url):
        return {
            "success": True,
            "type": "direct",
            "url": url,
            "title": "فيديو مباشر",
            "duration": 0,
            "uploader": "غير معروف",
            "ext": url.split("?")[0].split(".")[-1],
        }

    info = get_video_info(url)
    if info.get("success") and info.get("url"):
        try:
            hostname = (urlparse(info.get("webpage_url", url)).hostname or "").lower()
            parts = hostname.split(".")
            platform = "link"
            if len(parts) >= 2:
                platform = parts[-2]      # facebook, youtube, vimeo ...
        except Exception:
            platform = "link"

        info["type"] = platform
        return info

    return {
        "success": False,
        "error": "تعذر استخراج رابط الفيديو من هذا الرابط.",
    }


def download_with_ytdlp(url: str, save_path: str) -> dict:
    """
    تحميل الفيديو باستخدام yt-dlp إلى ملف محلي مؤقت
    """
    try:
        opts = ydl_opts.copy()
        opts["outtmpl"] = save_path.replace(".mp4", ".%(ext)s")

        print(f"[yt-dlp] بدء التحميل من: {url}")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        base = save_path.replace(".mp4", "")
        for ext in ["mp4", "webm", "mkv", "mov"]:
            possible = f"{base}.{ext}"
            if os.path.exists(possible):
                size = os.path.getsize(possible)
                print(f"[yt-dlp] تم العثور على الملف: {possible} (الحجم: {size} bytes)")
                if size > 0:
                    if possible != save_path:
                        os.rename(possible, save_path)
                    return {"success": True, "file_path": save_path, "file_size": size}

        return {"success": False, "error": "لم يتم إنشاء الملف بعد التحميل"}
    except Exception as e:
        print(f"download_with_ytdlp error: {e}")
        return {"success": False, "error": str(e)}


def download_video_fallback(direct_url: str, save_path: str) -> dict:
    """
    تحميل بديل باستخدام requests من رابط مباشر/stream
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        print(f"[fallback] محاولة التحميل المباشر من: {direct_url}")

        with requests.get(direct_url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        size = os.path.getsize(save_path)
        print(f"[fallback] تم التحميل: {size} bytes")
        if size > 0:
            return {"success": True, "file_path": save_path, "file_size": size}
        return {"success": False, "error": "الملف الملتقط فارغ"}
    except Exception as e:
        print(f"download_video_fallback error: {e}")
        return {"success": False, "error": str(e)}


async def send_video_direct(message: Message, direct_url: str, caption: str, duration: int | None):
    """
    المحاولة الأولى: إرسال الفيديو مباشرة من الرابط إلى تيليجرام (للروابط المباشرة فقط)
    """
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        await message.answer_video(
            video=direct_url,
            caption=caption,
            duration=duration or None,
            supports_streaming=True,
        )
        return {"success": True}
    except Exception as e:
        print(f"send_video_direct error: {e}")
        return {"success": False, "error": str(e)}


# ================== commands ==================

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 أهلاً بك في بوت الفيديو.\n\n"
        "أرسل رابط من أي موقع يدعم الفيديو (YouTube, TikTok, Facebook, X, Vimeo, ...).\n"
        "أو رابط فيديو مباشر (.mp4 / .webm / .mov / .mkv).\n\n"
        "📌 البوت يحظر بعض المنصات المحمية (مثل Netflix, Shahid...).\n"
        "📌 يحاول أولاً الإرسال مباشرة للروابط المباشرة، وإذا فشل يحمل مؤقتًا ثم يرسل ويحذف الملف."
    )


@router.message(F.text)
async def handle_link(message: Message):
    url = (message.text or "").strip()

    if not url.startswith("http"):
        await message.answer("❌ الرجاء إرسال رابط صحيح يبدأ بـ http أو https.")
        return

    if is_blocked_domain(url):
        await message.answer(
            "⛔ هذا الموقع محمي أو غير مدعوم (مثل منصات الأفلام المدفوعة)، لا يمكن التعامل معه."
        )
        return

    wait_msg = await message.answer("🔍 جاري تحليل الرابط...")

    try:
        video_info = get_direct_video_url(url)

        if not video_info.get("success"):
            await wait_msg.edit_text(f"❌ {video_info.get('error', 'تعذر التعامل مع الرابط.')}")
            return

        vtype = video_info.get("type", "unknown")

        if vtype == "direct":
            platform_name = "رابط مباشر"
        elif vtype in ["link", "unknown"]:
            platform_name = "منصة غير معروفة"
        else:
            platform_name = vtype.capitalize()

        info_text = f"✅ تم العثور على فيديو من: {platform_name}\n"

        if video_info.get("title"):
            title = video_info["title"]
            if len(title) > 50:
                title = title[:50] + "..."
            info_text += f"📹 {title}\n"

        if video_info.get("uploader"):
            info_text += f"👤 {video_info['uploader']}\n"

        if video_info.get("duration"):
            minutes = video_info["duration"] // 60
            seconds = video_info["duration"] % 60
            info_text += f"⏱️ {minutes}:{seconds:02d}\n"

        direct_url = video_info.get("url") or url
        duration = video_info.get("duration", 0)
        caption = f"✅ {platform_name}"
        if video_info.get("title"):
            caption += f" | {video_info['title'][:30]}"

        if vtype == "direct":
            await wait_msg.edit_text(info_text + "\n📤 محاولة إرسال مباشر بدون تحميل...")
            send_result = await send_video_direct(message, direct_url, caption, duration)

            if send_result["success"]:
                await wait_msg.delete()
                print("✅ أُرسل الفيديو مباشرة بدون تحميل.")
                return

            await wait_msg.edit_text(
                info_text + "\n⚠️ فشل الإرسال المباشر، جاري التحميل المؤقت ثم الإرسال..."
            )
        else:
            await wait_msg.edit_text(info_text + "\n⬇️ جاري التحميل...")

        ext = video_info.get("ext", "mp4")
        tmp_path = f"video_temp.{ext}"

        if vtype == "direct":
            dl = download_video_fallback(direct_url, tmp_path)
        else:
            dl = download_with_ytdlp(url, tmp_path)
            if (not dl["success"]) and video_info.get("url"):
                dl = download_video_fallback(video_info["url"], tmp_path)

        if not dl["success"]:
            await wait_msg.edit_text(f"❌ فشل تحميل الفيديو:\n{dl['error']}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return

        if dl["file_size"] > 50 * 1024 * 1024:
            await wait_msg.edit_text("❌ حجم الفيديو أكبر من 50MB، لا يمكن إرساله.")
            os.remove(tmp_path)
            return

        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)

        video_file = FSInputFile(tmp_path)
        await message.answer_video(
            video=video_file,
            caption=caption,
            duration=duration or None,
            supports_streaming=True,
        )

        await wait_msg.delete()
        print("✅ تم تحميل الفيديو مؤقتاً وإرساله، ثم حذفه.")

    except Exception as e:
        print(f"Unexpected error: {e}")
        try:
            await wait_msg.edit_text(f"❌ حدث خطأ غير متوقع أثناء معالجة الرابط:\n{e}")
        except Exception:
            pass
    finally:
        for fname in os.listdir("."):
            if fname.startswith("video_temp.") and os.path.isfile(fname):
                try:
                    os.remove(fname)
                    print(f"🧹 تم حذف الملف المؤقت: {fname}")
                except Exception as ee:
                    print(f"خطأ أثناء حذف الملف المؤقت {fname}: {ee}")


async def main():
    print("🚀 Bot is running...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv")

# منصات محظورة (محميّة/مدفوعة)
BLOCKED_DOMAINS = [
    "netflix.com",
    "shahid.net",
    "shahed4u",
    "osn.com",
    "disneyplus.com",
    "amazon.com",
    "hbomax.com",
]

# إعدادات yt-dlp
ydl_opts = {
    "format": "best[height<=720][filesize<50M]/best[height<=480]/best[height<=360]",
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 30,
    "retries": 5,
    "fragment_retries": 5,
    "extract_flat": False,
    "noplaylist": True,
}


# ================== helpers ==================

def looks_like_direct_video(url: str) -> bool:
    """
    يتحقق إن كان الرابط ينتهي بامتداد فيديو مباشر (mp4/webm/mov/mkv)
    """
    base = url.split("?", 1)[0].lower()
    return base.endswith(VIDEO_EXTS)


def is_blocked_domain(url: str) -> bool:
    """
    يتحقق إن كان الرابط من ضمن الدومينات المحظورة في BLOCKED_DOMAINS
    """
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return any(b in hostname for b in BLOCKED_DOMAINS)
    except Exception:
        return False


def get_video_info(url: str) -> dict:
    """
    يستخرج معلومات الفيديو باستخدام yt-dlp بدون تحميل
    """
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "success": True,
                "title": info.get("title", "فيديو"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "غير معروف"),
                "view_count": info.get("view_count", 0),
                "thumbnail": info.get("thumbnail", ""),
                "url": info.get("url"),          # stream / direct URL
                "ext": info.get("ext", "mp4"),
                "filesize": info.get("filesize"),
                "webpage_url": info.get("webpage_url", url),
            }
    except Exception as e:
        print(f"Video extract error: {e}")
        return {"success": False, "error": str(e)}


def get_direct_video_url(url: str) -> dict:
    """
    دالة ديناميكية:
    - لو الرابط ملف فيديو مباشر → type = direct
    - غير ذلك → تحاول yt-dlp على أي منصة غير محظورة
    """
    # 1) لو الرابط ملف فيديو مباشر (ينتهي بامتداد معروف)
    if looks_like_direct_video(url):
        return {
            "success": True,
            "type": "direct",
            "url": url,
            "title": "فيديو مباشر",
            "duration": 0,
            "uploader": "غير معروف",
            "ext": url.split("?")[0].split(".")[-1],
        }

    # 2) أي منصة أخرى غير محظورة → نعتمد على yt-dlp مباشرة
    info = get_video_info(url)
    if info.get("success") and info.get("url"):
        # نحاول استنتاج اسم المنصة من الدومين
        try:
            hostname = (urlparse(info.get("webpage_url", url)).hostname or "").lower()
            parts = hostname.split(".")
            platform = "link"
            if len(parts) >= 2:
                # مثال: www.facebook.com → facebook
                platform = parts[-2]
        except Exception:
            platform = "link"

        info["type"] = platform   # مثال: facebook, youtube, vimeo, ...
        return info

    # 3) فشل الاستخراج
    return {
        "success": False,
        "error": "تعذر استخراج رابط الفيديو من هذا الرابط.",
    }


def download_with_ytdlp(url: str, save_path: str) -> dict:
    """
    تحميل الفيديو باستخدام yt-dlp إلى ملف محلي مؤقت
    """
    try:
        opts = ydl_opts.copy()
        opts["outtmpl"] = save_path.replace(".mp4", ".%(ext)s")

        print(f"[yt-dlp] بدء التحميل من: {url}")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        base = save_path.replace(".mp4", "")
        for ext in ["mp4", "webm", "mkv", "mov"]:
            possible = f"{base}.{ext}"
            if os.path.exists(possible):
                size = os.path.getsize(possible)
                print(f"[yt-dlp] تم العثور على الملف: {possible} (الحجم: {size} bytes)")
                if size > 0:
                    if possible != save_path:
                        os.rename(possible, save_path)
                    return {"success": True, "file_path": save_path, "file_size": size}

        return {"success": False, "error": "لم يتم إنشاء الملف بعد التحميل"}
    except Exception as e:
        print(f"download_with_ytdlp error: {e}")
        return {"success": False, "error": str(e)}


def download_video_fallback(direct_url: str, save_path: str) -> dict:
    """
    تحميل بديل باستخدام requests من رابط مباشر/stream
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        print(f"[fallback] محاولة التحميل المباشر من: {direct_url}")

        with requests.get(direct_url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        size = os.path.getsize(save_path)
        print(f"[fallback] تم التحميل: {size} bytes")
        if size > 0:
            return {"success": True, "file_path": save_path, "file_size": size}
        return {"success": False, "error": "الملف الملتقط فارغ"}
    except Exception as e:
        print(f"download_video_fallback error: {e}")
        return {"success": False, "error": str(e)}


async def send_video_direct(message: Message, direct_url: str, caption: str, duration: int | None):
    """
    المحاولة الأولى: إرسال الفيديو مباشرة من الرابط إلى تيليجرام (للروابط المباشرة فقط)
    """
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        await message.answer_video(
            video=direct_url,
            caption=caption,
            duration=duration or None,
            supports_streaming=True,
        )
        return {"success": True}
    except Exception as e:
        print(f"send_video_direct error: {e}")
        return {"success": False, "error": str(e)}


# ================== commands ==================

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 أهلاً بك في بوت الفيديو.\n\n"
        "أرسل رابط من أي موقع يدعم الفيديو (YouTube, TikTok, Facebook, X, Vimeo, ...).\n"
        "أو رابط فيديو مباشر (.mp4 / .webm / .mov / .mkv).\n\n"
        "📌 البوت يحظر بعض المنصات المحمية (مثل Netflix, Shahid...).\n"
        "📌 يحاول أولاً الإرسال مباشرة للروابط المباشرة، وإذا فشل يحمل مؤقتًا ثم يرسل ويحذف الملف."
    )


@router.message(F.text)
async def handle_link(message: Message):
    url = (message.text or "").strip()

    if not url.startswith("http"):
        await message.answer("❌ الرجاء إرسال رابط صحيح يبدأ بـ http أو https.")
        return

    # حظر الدومينات المحمية
    if is_blocked_domain(url):
        await message.answer(
            "⛔ هذا الموقع محمي أو غير مدعوم (مثل منصات الأفلام المدفوعة)، لا يمكن التعامل معه."
        )
        return

    wait_msg = await message.answer("🔍 جاري تحليل الرابط...")

    try:
        video_info = get_direct_video_url(url)

        if not video_info.get("success"):
            await wait_msg.edit_text(f"❌ {video_info.get('error', 'تعذر التعامل مع الرابط.')}")
            return

        vtype = video_info.get("type", "unknown")

        # تحديد اسم المنصة
        if vtype == "direct":
            platform_name = "رابط مباشر"
        elif vtype in ["link", "unknown"]:
            platform_name = "منصة غير معروفة"
        else:
            platform_name = vtype.capitalize()  # facebook → Facebook

        info_text = f"✅ تم العثور على فيديو من: {platform_name}\n"

        if video_info.get("title"):
            title = video_info["title"]
            if len(title) > 50:
                title = title[:50] + "..."
            info_text += f"📹 {title}\n"

        if video_info.get("uploader"):
            info_text += f"👤 {video_info['uploader']}\n"

        if video_info.get("duration"):
            minutes = video_info["duration"] // 60
            seconds = video_info["duration"] % 60
            info_text += f"⏱️ {minutes}:{seconds:02d}\n"

        direct_url = video_info.get("url") or url
        duration = video_info.get("duration", 0)
        caption = f"✅ {platform_name}"
        if video_info.get("title"):
            caption += f" | {video_info['title'][:30]}"

        # =========================
        # 1) محاولة إرسال مباشر فقط لو type == direct (رابط ملف فيديو)
        # =========================
        if vtype == "direct":
            await wait_msg.edit_text(info_text + "\n📤 محاولة إرسال مباشر بدون تحميل...")
            send_result = await send_video_direct(message, direct_url, caption, duration)

            if send_result["success"]:
                await wait_msg.delete()
                print("✅ أُرسل الفيديو مباشرة بدون تحميل.")
                return

            # فشل الإرسال المباشر لرابط مباشر → نستخدم تحميل مؤقت
            await wait_msg.edit_text(
                info_text + "\n⚠️ فشل الإرسال المباشر، جاري التحميل المؤقت ثم الإرسال..."
            )
        else:
            # أي منصة أخرى → لا نحاول إرسال مباشر، نذهب مباشرة للتحميل
            await wait_msg.edit_text(info_text + "\n⬇️ جاري التحميل...")

        # =========================
        # 2) تحميل مؤقت ثم إرسال من ملف
        # =========================
        ext = video_info.get("ext", "mp4")
        tmp_path = f"video_temp.{ext}"

        if vtype == "direct":
            # direct لكنه فشل كـ URL عند تيليجرام → نحاول التحميل من نفس الرابط
            dl = download_video_fallback(direct_url, tmp_path)
        else:
            # منصات أخرى: نحاول أولاً بـ yt-dlp
            dl = download_with_ytdlp(url, tmp_path)
            if (not dl["success"]) and video_info.get("url"):
                dl = download_video_fallback(video_info["url"], tmp_path)

        if not dl["success"]:
            await wait_msg.edit_text(f"❌ فشل تحميل الفيديو:\n{dl['error']}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return

        if dl["file_size"] > 50 * 1024 * 1024:
            await wait_msg.edit_text("❌ حجم الفيديو أكبر من 50MB، لا يمكن إرساله.")
            os.remove(tmp_path)
            return

        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)

        video_file = FSInputFile(tmp_path)
        await message.answer_video(
            video=video_file,
            caption=caption,
            duration=duration or None,
            supports_streaming=True,
        )

        await wait_msg.delete()
        print("✅ تم تحميل الفيديو مؤقتاً وإرساله، ثم حذفه.")

    except Exception as e:
        print(f"Unexpected error: {e}")
        try:
            await wait_msg.edit_text(f"❌ حدث خطأ غير متوقع أثناء معالجة الرابط:\n{e}")
        except Exception:
            pass
    finally:
        # تنظيف أي ملف مؤقت لو بقي
        for fname in os.listdir("."):
            if fname.startswith("video_temp.") and os.path.isfile(fname):
                try:
                    os.remove(fname)
                    print(f"🧹 تم حذف الملف المؤقت: {fname}")
                except Exception as ee:
                    print(f"خطأ أثناء حذف الملف المؤقت {fname}: {ee}")


# ================== run ==================

async def main():
    print("🚀 Bot is running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
