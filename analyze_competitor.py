import os
import sys
import json
import time
import re
import glob
import subprocess
from datetime import datetime
from urllib.parse import urlparse
import yt_dlp
import mlx_whisper
from playwright.sync_api import sync_playwright

OUTPUT_DIR = "outputs"
SESSION_DIR = os.path.abspath("browser_session")
TEMP_AUDIO_DIR = "temp_audio"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")

def format_number(n):
    if not n:
        return "0"
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)

def format_timestamp(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def clean_instagram_url(raw_input):
    raw_input = raw_input.strip()
    if "instagram.com" in raw_input:
        parsed = urlparse(raw_input)
        path_parts = [p for p in parsed.path.split("/") if p and p not in ("reels", "reel", "p")]
        username = path_parts[0] if path_parts else "competitor"
    else:
        username = raw_input.lstrip("@").split("/")[0].split("?")[0].strip()
    
    clean_url = f"https://www.instagram.com/{username}/"
    return clean_url, username

def parse_views_str(v_str):
    if not v_str:
        return 0
    v_str = v_str.upper().replace(" ", "").replace(",", ".").replace("ПРОСМОТРОВ", "").replace("VIEWS", "").replace("V", "").strip()
    try:
        if "K" in v_str or "К" in v_str:
            num = float(re.sub(r"[^0-9.]", "", v_str))
            return int(num * 1000)
        if "M" in v_str or "М" in v_str:
            num = float(re.sub(r"[^0-9.]", "", v_str))
            return int(num * 1000000)
        digits = re.sub(r"[^0-9]", "", v_str)
        return int(digits) if digits else 0
    except Exception:
        return 0

def fetch_reel_metadata_and_audio(url, shortcode):
    out_tmpl = os.path.join(TEMP_AUDIO_DIR, f"{shortcode}.%(ext)s")
    for f in glob.glob(os.path.join(TEMP_AUDIO_DIR, f"{shortcode}.*")):
        try:
            os.remove(f)
        except Exception:
            pass

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_tmpl,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
    }

    meta = {
        "caption": "",
        "likes": 0,
        "comments": 0,
        "upload_date": "Не указана",
        "audio_path": None
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                meta["caption"] = info.get("description") or info.get("title") or ""
                meta["likes"] = info.get("like_count") or 0
                meta["comments"] = info.get("comment_count") or 0
                
                # Форматирование даты публикации
                raw_date = info.get("upload_date")
                if raw_date and len(raw_date) == 8:
                    meta["upload_date"] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                elif info.get("timestamp"):
                    meta["upload_date"] = datetime.fromtimestamp(info["timestamp"]).strftime('%Y-%m-%d')
                    
        target = os.path.join(TEMP_AUDIO_DIR, f"{shortcode}.mp3")
        if os.path.exists(target):
            meta["audio_path"] = target
        else:
            candidates = glob.glob(os.path.join(TEMP_AUDIO_DIR, f"{shortcode}.*"))
            if candidates:
                meta["audio_path"] = candidates[0]
    except Exception as e:
        # Резервный вызов через CLI
        try:
            cmd = [
                sys.executable.replace("python3", "yt-dlp"),
                "-x", "--audio-format", "mp3",
                "-o", out_tmpl,
                url
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            target = os.path.join(TEMP_AUDIO_DIR, f"{shortcode}.mp3")
            if os.path.exists(target):
                meta["audio_path"] = target
        except Exception:
            pass

    return meta

def transcribe_audio_with_timestamps(audio_path):
    if not audio_path or not os.path.exists(audio_path):
        return "[Аудиодорожка недоступна]"
        
    try:
        res = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
            language="ru"
        )
        
        segments = res.get("segments", [])
        if not segments:
            full_text = res.get("text", "").strip()
            return f"> {full_text}" if full_text else "[Речь не распознана]"
            
        formatted_lines = []
        for seg in segments:
            start_str = format_timestamp(seg.get("start", 0))
            end_str = format_timestamp(seg.get("end", 0))
            text_seg = seg.get("text", "").strip()
            if text_seg:
                formatted_lines.append(f"> `[{start_str} - {end_str}]` {text_seg}")
                
        return "\n".join(formatted_lines)
    except Exception as e:
        return f"[Ошибка транскрибации: {e}]"
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass

def extract_posts_playwright(profile_url):
    reels_data = {}
    bio_text = ""

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page()

        def handle_response(response):
            nonlocal reels_data
            if "/graphql/query" in response.url or "/api/v1/" in response.url:
                try:
                    data = response.json()
                    parse_graphql_data(data, reels_data)
                except Exception:
                    pass

        page.on("response", handle_response)
        
        reels_page_url = profile_url.rstrip("/") + "/reels/"
        print(f"🌐 Открытие страницы в Chrome: {reels_page_url}")
        page.goto(reels_page_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        try:
            header_elem = page.query_selector("header")
            if header_elem:
                bio_text = header_elem.inner_text()
        except Exception:
            bio_text = ""

        scroll_attempts = 0
        max_scrolls = 25
        last_count = 0

        while len(reels_data) < 100 and scroll_attempts < max_scrolls:
            try:
                anchors = page.query_selector_all('a[href*="/reel/"]')
                for a in anchors:
                    href = a.get_attribute("href") or ""
                    match = re.search(r'/reel/([^/?#]+)', href)
                    if match:
                        sc = match.group(1)
                        if sc not in reels_data:
                            views = parse_views_str(a.inner_text())
                            reels_data[sc] = {
                                "shortcode": sc,
                                "url": f"https://www.instagram.com/reel/{sc}/",
                                "views": views,
                                "likes": 0,
                                "comments": 0,
                                "caption": "",
                                "upload_date": "Не указана"
                            }
            except Exception:
                pass

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2.5)
            scroll_attempts += 1
            current_count = len(reels_data)
            print(f"📊 Собрано публикаций в пуле: {current_count}/100...")
            if current_count == last_count and scroll_attempts > 6:
                break
            last_count = current_count

        browser.close()

    return reels_data, bio_text

def parse_graphql_data(data, reels_dict):
    def recursive_search(obj):
        if isinstance(obj, dict):
            if "shortcode" in obj or "code" in obj:
                sc = obj.get("shortcode") or obj.get("code")
                views = (
                    obj.get("play_count") or 
                    obj.get("view_count") or 
                    obj.get("video_view_count") or 
                    obj.get("video_play_count") or 0
                )
                likes = (
                    obj.get("edge_media_preview_like", {}).get("count") or 
                    obj.get("like_count") or 0
                )
                comments = (
                    obj.get("edge_media_to_comment", {}).get("count") or 
                    obj.get("comment_count") or 0
                )
                
                # Дата
                taken_at = obj.get("taken_at_timestamp") or obj.get("taken_at")
                upload_date = "Не указана"
                if taken_at:
                    try:
                        upload_date = datetime.fromtimestamp(int(taken_at)).strftime('%Y-%m-%d')
                    except Exception:
                        pass
                
                caption = ""
                edge_text = obj.get("edge_media_to_caption", {}).get("edges", [])
                if edge_text and isinstance(edge_text, list):
                    caption = edge_text[0].get("node", {}).get("text", "")
                elif "caption" in obj and isinstance(obj["caption"], dict):
                    caption = obj["caption"].get("text", "")
                    
                if sc:
                    if sc not in reels_dict or reels_dict[sc]["views"] == 0:
                        reels_dict[sc] = {
                            "shortcode": sc,
                            "url": f"https://www.instagram.com/reel/{sc}/",
                            "views": int(views),
                            "likes": int(likes),
                            "comments": int(comments),
                            "caption": caption.strip(),
                            "upload_date": upload_date
                        }
            for v in obj.values():
                recursive_search(v)
        elif isinstance(obj, list):
            for item in obj:
                recursive_search(item)

    recursive_search(data)

def main():
    if len(sys.argv) < 2:
        print("Использование: python analyze_competitor.py <Instagram_URL>")
        sys.exit(1)

    raw_input = sys.argv[1]
    clean_url, username = clean_instagram_url(raw_input)
    print(f"🎯 Профиль для анализа: @{username} ({clean_url})")

    reels_dict, bio_text = extract_posts_playwright(clean_url)

    if not reels_dict:
        print("⚠️ Не удалось получить список Reels. Запустите login_instagram.py.")
        sys.exit(1)

    print(f"\n✅ Всего уникальных роликов собрано: {len(reels_dict)}")
    sorted_reels = sorted(reels_dict.values(), key=lambda x: x["views"], reverse=True)[:25]
    print(f"🏆 Отобран Топ-{len(sorted_reels)} самых вирусных роликов для расшифровки.")

    results = []
    for idx, item in enumerate(sorted_reels, 1):
        print(f"\n[{idx}/{len(sorted_reels)}] 🚀 Анализ и транскрибация: {item['url']} ({format_number(item['views'])} просм.)")
        
        # Получаем аудио + глубокие метаданные (описание, дату, комментарии)
        meta = fetch_reel_metadata_and_audio(item["url"], item["shortcode"])
        
        # Обогащаем поля, если yt-dlp нашел больше деталей
        if meta["caption"]:
            item["caption"] = meta["caption"]
        if meta["likes"] and item["likes"] == 0:
            item["likes"] = meta["likes"]
        if meta["comments"] and item["comments"] == 0:
            item["comments"] = meta["comments"]
        if meta["upload_date"] != "Не указана":
            item["upload_date"] = meta["upload_date"]

        if not meta["audio_path"]:
            print("⏭️ Аудиодорожка не найдена.")
            item["transcription"] = "[Аудиодорожка недоступна]"
        else:
            print("🎙️ Whisper Turbo генерирует таймкоды речи...")
            item["transcription"] = transcribe_audio_with_timestamps(meta["audio_path"])
            print("✅ Расшифровка готова.")

        results.append(item)

    # Генерация полного отчета в Markdown
    report_filename = f"{clean_filename(username)}_reels_report.md"
    report_path = os.path.join(OUTPUT_DIR, report_filename)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 🎬 Анализ Reels профиля @{username}\n\n")
        f.write(f"**Ссылка на профиль:** {clean_url}\n")
        f.write(f"**Дата анализа:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if bio_text:
            f.write("## 📌 Описание профиля (Bio)\n")
            f.write(f"```\n{bio_text.strip()}\n```\n\n")

        f.write(f"## 🏆 Топ-{len(results)} вирусных роликов по просмотрам\n\n---\n\n")

        for idx, r in enumerate(results, 1):
            f.write(f"### {idx}. Reel: {r['url']}\n\n")
            f.write(f"* **👁️ Просмотры:** {format_number(r['views'])}\n")
            f.write(f"* **❤️ Лайки:** {format_number(r['likes'])}\n")
            f.write(f"* **💬 Комментарии:** {format_number(r['comments'])}\n")
            f.write(f"* **📅 Дата публикации:** {r['upload_date']}\n")
            
            if r['caption']:
                clean_cap = r['caption'].strip()
                f.write(f"\n**📝 Описание ролика:**\n```\n{clean_cap}\n```\n")
                
            f.write(f"\n**🗣️ Транскрипция речи с таймкодами:**\n{r['transcription']}\n\n---\n\n")

    print(f"\n🎉 Анализ успешно завершён!")
    print(f"📄 Отчёт сохранён в: {os.path.abspath(report_path)}")

if __name__ == "__main__":
    main()
