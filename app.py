# -*- coding: utf-8 -*-
import os
import re
import json
import math
import shutil
import random
import subprocess
import tempfile
import time
import urllib.parse
import asyncio

import streamlit as st
import requests
import imageio_ffmpeg
from groq import Groq
import edge_tts

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Studio Cinematic Story Master Pro", page_icon="⚡", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

# Nhạc nền điện ảnh kịch tính bản quyền mở
DRAMA_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong Secrets của Streamlit Cloud!")
    st.stop()

st.title("⚡ Studio Cinematic Story Master Pro")
st.caption("Khớp thị giác hành động sâu • Phân luồng giọng phim tài liệu • Lọc bỏ top đề xuất tĩnh")

# ==============================================================================
# GIAO DIỆN NGƯỜI DÙNG
# ==============================================================================
topic_genre = st.text_area(
    "Nhập chủ đề kịch bản chi tiết:",
    value="Một con tàu đánh cá gặp cơn bão lớn giữa đại dương đen kịt, sóng thần cuồn cuộn và cuộc chiến sinh tồn của các thủy thủ",
    height=100
)

col_t1, col_t2 = st.columns(2)
with col_t1:
    genre_type = st.selectbox(
        "Thể loại video (Để gán đúng giọng đọc & âm hưởng):",
        [
            "Thảm họa / Kịch tính / Sinh tồn / Lịch sử (Dramatic / Disaster)",
            "Thế giới Động vật / Thiên nhiên hoang dã (Wildlife / Nature)",
            "Đời sống / Chill / Tươi sáng (Lifestyle / Story)",
            "Huyền bí / Khoa học viễn tưởng (Sci-Fi / Mystery)"
        ]
    )
with col_t2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=300, value=25, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)

col_v1, col_v2 = st.columns(2)
with col_v1:
    language_mode = st.selectbox(
        "Ngôn ngữ & Giọng đọc mục tiêu:",
        [
            "Tiếng Anh: Christopher (Giọng tài liệu trầm khàn chuẩn Tây lông)",
            "Tiếng Anh: Guy (Nam Mỹ mạnh mẽ, cuốn hút)",
            "Tiếng Anh: Jenny (Nữ kể chuyện truyền cảm)",
            "Tiếng Việt: Nam Minh (Nam thời sự / tài liệu trầm)",
            "Tiếng Việt: Hoài My (Nữ truyền hình rõ chữ)"
        ]
    )
with col_v2:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["portrait (Dọc 9:16 Shorts/TikTok/Reels)", "landscape (Ngang 16:9 YouTube Chuẩn)"])

bgm_volume = st.slider("Âm lượng nhạc nền ngầm (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ AN TOÀN & CÀO DỮ LIỆU ĐA TẦNG (DEEP SCRAPING)
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=20) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                return True
    except Exception:
        pass
    return False

def get_audio_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 4.0

async def generate_voice_advanced(text: str, out_audio: str, voice_option: str):
    if "Christopher" in voice_option:
        voice_code = "en-US-ChristopherNeural"
        rate_val = "+0%"
    elif "Guy" in voice_option:
        voice_code = "en-US-GuyNeural"
        rate_val = "+2%"
    elif "Jenny" in voice_option:
        voice_code = "en-US-JennyNeural"
        rate_val = "+0%"
    elif "Nam Minh" in voice_option:
        voice_code = "vi-VN-NamMinhNeural"
        rate_val = "+3%"
    else:
        voice_code = "vi-VN-HoaiMyNeural"
        rate_val = "+2%"

    comm = edge_tts.Communicate(text, voice=voice_code, rate=rate_val)
    await comm.save(out_audio)

def fetch_deep_pexels_clip(query: str, p_key: str, used_hashes: set, must_keywords: list) -> str:
    headers = {"Authorization": p_key.strip()}
    # Cào ngẫu nhiên trang 2, 3 hoặc 4 để né sạch các video tĩnh ở trang 1
    pages_to_crawl = [random.randint(2, 4), random.randint(1, 2)]
    
    for page in pages_to_crawl:
        try:
            url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=15&page={page}"
            r = requests.get(url, headers=headers, timeout=8)
            if r.ok and r.json().get("videos"):
                videos = r.json()["videos"]
                # Sắp xếp ưu tiên video có URL hoặc tags khớp với hành động mạnh (storm, wave, rough, ...)
                scored_videos = []
                for v in videos:
                    v_id = f"pexels_{v.get('id')}"
                    if v_id in used_hashes:
                        continue
                    
                    # Điểm số liên quan ngữ cảnh
                    score = 0
                    v_url_text = v.get("url", "").lower()
                    for mk in must_keywords:
                        if mk.lower() in v_url_text:
                            score += 5
                    
                    scored_videos.append((score, v, v_id))
                
                scored_videos.sort(key=lambda x: x[0], reverse=True)
                for _, v_obj, v_id in scored_videos:
                    files = v_obj.get("video_files", [])
                    hd = next((f["link"] for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"), None)
                    if not hd and files:
                        hd = files[0].get("link")
                    if hd:
                        used_hashes.add(v_id)
                        return hd
        except Exception:
            continue
    return None

def fetch_deep_pixabay_clip(query: str, pb_key: str, used_hashes: set, must_keywords: list) -> str:
    if not pb_key or not pb_key.strip():
        return None
    try:
        page = random.randint(1, 3)
        url = f"{PIXABAY_VIDEO_URL}?key={pb_key.strip()}&q={urllib.parse.quote(query)}&per_page=20&page={page}"
        r = requests.get(url, timeout=8)
        if r.ok and r.json().get("hits"):
            hits = r.json()["hits"]
            scored_hits = []
            for v in hits:
                v_id = f"pixabay_{v.get('id')}"
                if v_id in used_hashes:
                    continue
                
                score = 0
                tags_str = v.get("tags", "").lower()
                for mk in must_keywords:
                    if mk.lower() in tags_str:
                        score += 5
                scored_hits.append((score, v, v_id))

            scored_hits.sort(key=lambda x: x[0], reverse=True)
            for _, v_obj, v_id in scored_hits:
                v_files = v_obj.get("videos", {})
                target = v_files.get("large") or v_files.get("medium") or v_files.get("small")
                if target and target.get("url"):
                    used_hashes.add(v_id)
                    return target["url"]
    except Exception:
        pass
    return None

def get_high_relevance_broll(query: str, p_key: str, pb_key: str, used_hashes: set, must_keywords: list) -> str:
    # Quét luân phiên cả 2 nguồn, ưu tiên video có điểm tương quan cao nhất
    clip = fetch_deep_pexels_clip(query, p_key, used_hashes, must_keywords)
    if not clip and pb_key:
        clip = fetch_deep_pixabay_clip(query, pb_key, used_hashes, must_keywords)
    if not clip:
        # Fallback với từ khóa hành động gắt
        fallback_query = " ".join(must_keywords[:2]) if must_keywords else "ocean waves storm"
        clip = fetch_deep_pexels_clip(fallback_query, p_key, used_hashes, must_keywords)
    return clip

def cut_clip_exact_5s(raw_p: str, out_p: str, is_port: bool):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"
    
    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_p]
    try:
        raw_dur = float(subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip() or 10.0)
    except Exception:
        raw_dur = 10.0

    start_sec = 0.5
    if raw_dur > (CLIP_DURATION + 2.0):
        start_sec = random.uniform(1.0, min(4.0, raw_dur - CLIP_DURATION - 0.5))

    cmd = [
        FFMPEG_EXE, "-y", "-ss", f"{start_sec:.2f}",
        "-i", raw_p, "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f,
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        out_p
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT MASTER
# ==============================================================================
if st.button("🚀 Bắt Đầu Sản Xuất Master Video (Khớp Visual 100%)", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập chủ đề kịch bản.")
    else:
        status = st.status(f"Hệ thống đang sản xuất kịch bản {calc_clips} cảnh...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="master_pro_")
        used_hashes = set()
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in language_mode

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. AI viết kịch bản điện ảnh + Bóc tách từ khóa hành động vật lý (Loại bỏ từ trừu tượng)
            status.update(label=f"🧠 1/4: AI xây dựng cốt truyện điện ảnh và trích xuất từ khóa thị giác mạnh...")
            prompt = f"""You are a Hollywood documentary director and visual effects supervisor.
Topic: "{topic_genre}".
Genre: "{genre_type}".
Total scenes: Exactly {calc_clips} consecutive scenes (each lasts 5.0 seconds).
Language: {"English" if is_en else "Vietnamese"}.

STRICT RULES FOR QUERIES:
- DO NOT use abstract or peaceful words like "beauty", "sunrise", "calm", "resting", "wonder".
- If the topic is a STORM or DISASTER, EVERY SINGLE query must contain aggressive, violent physical terms: `storm waves`, `huge sea waves`, `lightning dark clouds`, `ship heavy rain`, `rough sea water`.
- For each scene provide:
  + `speech_text`: Short, gripping narrative (under 12 words) that reads in about 3 seconds.
  + `query_en`: 2-3 specific English words for physical action.
  + `must_keywords`: Array of 2-3 raw tags to verify relevance (e.g. ["storm", "waves", "sea"]).

Return ONLY a valid JSON array of {calc_clips} objects:
[
  {{
    "scene": 1,
    "speech_text": "...",
    "query_en": "rough ocean storm waves",
    "must_keywords": ["storm", "waves", "sea"]
  }}
]"""

            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            parsed_scenes = json.loads(match.group(0)) if match else []

            # Đảm bảo đủ số cảnh
            while len(parsed_scenes) < calc_clips:
                idx = len(parsed_scenes) + 1
                parsed_scenes.append({
                    "scene": idx,
                    "speech_text": f"Những khoảnh khắc căng thẳng tiếp theo ở phân cảnh {idx}.",
                    "query_en": "heavy storm rough ocean",
                    "must_keywords": ["storm", "waves"]
                })
            parsed_scenes = parsed_scenes[:calc_clips]

            # 2. Tạo giọng đọc truyền cảm chuẩn phong cách tài liệu
            status.update(label="🎙️ 2/4: Đang tạo giọng đọc tài liệu (Documentary Voice)...")
            scenes = []
            for idx, item in enumerate(parsed_scenes):
                voice_file = os.path.join(workdir, f"voice_{idx:02d}.mp3")
                asyncio.run(generate_voice_advanced(item["speech_text"], voice_file, language_mode))

                scenes.append({
                    "query": item["query_en"],
                    "must_keywords": item.get("must_keywords", []),
                    "audio": voice_file,
                    "dur": CLIP_DURATION
                })

            # 3. Tải B-roll đào sâu trang 2-4 & Lọc tags
            status.update(label="🎬 3/4: Đào sâu kho video Pexels/Pixabay, lọc bỏ video tĩnh...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = get_high_relevance_broll(sc["query"], pexels_key, pixabay_key, used_hashes, sc["must_keywords"])
                    if not v_url:
                        v_url = get_high_relevance_broll("huge ocean waves storm", pexels_key, pixabay_key, used_hashes, ["storm", "waves"])

                    raw_v = os.path.join(workdir, f"raw_{idx:02d}.mp4")
                    cut_v = os.path.join(workdir, f"c_{idx:02d}.mp4")
                    download_file_safe(v_url, raw_v)

                    cut_clip_exact_5s(raw_v, cut_v, is_port)
                    if os.path.exists(raw_v):
                        os.remove(raw_v)

                    synced_v = os.path.join(workdir, f"synced_{idx:02d}.mp4")
                    cmd_sync = [
                        FFMPEG_EXE, "-y",
                        "-i", cut_v,
                        "-i", sc["audio"],
                        "-t", f"{CLIP_DURATION:.3f}",
                        "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k",
                        synced_v
                    ]
                    subprocess.run(cmd_sync, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")

            # 4. Xuất Master + Hòa âm BGM điện ảnh
            status.update(label="⚡ 4/4: Ghép chuỗi cảnh & hòa âm Master...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "master_story_pro.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_path = os.path.join(workdir, "drama_bgm.mp3")
            has_bgm = (bgm_volume > 0) and download_file_safe(DRAMA_BGM_URL, bgm_path)
            vol_float = bgm_volume / 100.0

            if has_bgm:
                cmd_mix = [
                    FFMPEG_EXE, "-y",
                    "-i", temp_merged,
                    "-stream_loop", "-1", "-i", bgm_path,
                    "-filter_complex", f"[0:a]volume=1.0[a0];[1:a]volume={vol_float:.2f}[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    final_mp4
                ]
                subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                shutil.copy(temp_merged, final_mp4)

            status.update(label=f"🎉 Hoàn thành video {calc_clips * 5}s chuẩn điện ảnh!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
                data=v_bytes,
                file_name=f"cinematic_story_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
