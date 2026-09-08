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

st.set_page_config(page_title="Kids Animal Sounds & Facts Studio Pro", page_icon="🐾", layout="centered")

FPS = 30
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
KIDS_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

ANIMAL_SOUNDS = {
    "cow": "https://www.myinstants.com/media/sounds/cow-moo.mp3",
    "cat": "https://www.myinstants.com/media/sounds/cat-meow.mp3",
    "dog": "https://www.myinstants.com/media/sounds/dog-bark.mp3",
    "lion": "https://www.myinstants.com/media/sounds/lion-roar.mp3",
    "elephant": "https://www.myinstants.com/media/sounds/elephant-sound.mp3",
    "duck": "https://www.myinstants.com/media/sounds/quack_5.mp3",
    "sheep": "https://www.myinstants.com/media/sounds/sheep-bleat.mp3",
    "horse": "https://www.myinstants.com/media/sounds/horse-neigh.mp3",
    "wolf": "https://www.myinstants.com/media/sounds/wolf-howling.mp3",
    "rooster": "https://www.myinstants.com/media/sounds/rooster-crowing.mp3"
}

# Tự động nạp API key từ Secrets
try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🐾 Kids Animal Sounds Studio (Multi-Source)")
st.caption("Tổng hợp Pexels + Pixabay • Bộ lọc chống trùng clip tuyệt đối • Tiếng kêu động vật chân thực")

col1, col2 = st.columns(2)
with col1:
    language_mode = st.selectbox("Ngôn ngữ thuyết minh:", ["Tiếng Anh (Cho trẻ em toàn cầu - View ngoại)", "Tiếng Việt (Kids Việt Nam)"])
with col2:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["portrait (Dọc 9:16 Shorts/Reels)", "landscape (Ngang 16:9 YouTube Chuẩn)"])

custom_animals = st.text_area(
    "Danh sách loài vật muốn tạo (ngăn cách bằng dấu phẩy):",
    value="cow, lion, cat, dog, elephant, duck",
    placeholder="Nhập tên tiếng Anh các loài vật..."
)

# ==============================================================================
# HÀM XỬ LÝ ĐA NGUỒN (PEXELS + PIXABAY) & CHỐNG TRÙNG LẶP
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

async def generate_voice(text: str, out_audio: str, is_en: bool):
    voice_name = "en-US-AnaNeural" if is_en else "vi-VN-HoaiMyNeural"
    comm = edge_tts.Communicate(text, voice=voice_name, rate="+0%")
    await comm.save(out_audio)

def fetch_from_pexels(query: str, p_key: str, used_hashes: set) -> str:
    headers = {"Authorization": p_key.strip()}
    for q in [f"{query} close up", query, f"{query} wild"]:
        try:
            page = random.randint(1, 3)
            url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(q)}&per_page=12&page={page}"
            r = requests.get(url, headers=headers, timeout=8)
            if r.ok and r.json().get("videos"):
                videos = r.json()["videos"]
                random.shuffle(videos)
                for v in videos:
                    v_id = f"pexels_{v.get('id')}"
                    if v_id not in used_hashes:
                        files = v.get("video_files", [])
                        hd = next((f["link"] for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"), None)
                        if not hd and files:
                            hd = files[0].get("link")
                        if hd:
                            used_hashes.add(v_id)
                            return hd
        except Exception:
            continue
    return None

def fetch_from_pixabay(query: str, pb_key: str, used_hashes: set) -> str:
    if not pb_key or not pb_key.strip():
        return None
    try:
        page = random.randint(1, 2)
        url = f"{PIXABAY_VIDEO_URL}?key={pb_key.strip()}&q={urllib.parse.quote(query)}&per_page=15&page={page}"
        r = requests.get(url, timeout=8)
        if r.ok and r.json().get("hits"):
            hits = r.json()["hits"]
            random.shuffle(hits)
            for v in hits:
                v_id = f"pixabay_{v.get('id')}"
                if v_id not in used_hashes:
                    v_files = v.get("videos", {})
                    # Ưu tiên lấy file cỡ medium/large chuẩn HD
                    target = v_files.get("large") or v_files.get("medium") or v_files.get("small")
                    if target and target.get("url"):
                        used_hashes.add(v_id)
                        return target["url"]
    except Exception:
        pass
    return None

def fetch_multi_source_clip(query: str, p_key: str, pb_key: str, used_hashes: set) -> str:
    """Cơ chế đa nguồn: Luân phiên tìm trên Pixabay và Pexels, loại trừ toàn bộ clip đã lấy"""
    # Nếu có key Pixabay, đổi nguồn ngẫu nhiên giữa Pexels và Pixabay để tăng độ đa dạng
    if pb_key and random.random() > 0.5:
        clip = fetch_from_pixabay(query, pb_key, used_hashes)
        if clip:
            return clip

    clip = fetch_from_pexels(query, p_key, used_hashes)
    if not clip and pb_key:
        clip = fetch_from_pixabay(query, pb_key, used_hashes)
    return clip

def cut_clip_clean(raw_p: str, out_p: str, dur: float, is_port: bool):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"
    
    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_p]
    try:
        raw_dur = float(subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip() or 10.0)
    except Exception:
        raw_dur = 10.0

    start_sec = 0.5
    if raw_dur > (dur + 2.0):
        start_sec = random.uniform(1.0, min(3.0, raw_dur - dur - 0.5))

    cmd = [
        FFMPEG_EXE, "-y", "-ss", f"{start_sec:.2f}",
        "-i", raw_p, "-t", f"{dur:.3f}",
        "-vf", res_f,
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        out_p
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Tạo Video Animal Sounds Đa Nguồn", use_container_width=True, type="primary"):
    status = st.status("Khởi động hệ thống sản xuất video giáo dục đa nguồn...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="kids_multi_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in language_mode

    try:
        client = Groq(api_key=groq_key.strip())

        # 1. AI biên soạn Fun Facts
        status.update(label="🧠 1/4: AI tạo danh sách sự thật thú vị cho từng loài...")
        prompt = f"""You are a content creator for kids educational channels (like 'Kids ABCD').
Animals list: "{custom_animals}".
Language: {"English" if is_en else "Vietnamese"}.

Create a JSON list for each animal.
Requirements:
- `animal_key`: Single lowercase English keyword (cow, cat, dog, lion, duck, elephant, sheep, horse, wolf, rooster).
- `search_query`: 2-3 English words to search stock footage (e.g., 'cow eating field', 'lion wild close up').
- `fun_fact`: A short, simple fact for kids (10-15 words).

Return ONLY valid JSON:
[
  {{"animal_key": "cow", "search_query": "cow farm field", "fun_fact": "Cows have best friends and like spending time together."}},
  {{"animal_key": "lion", "search_query": "lion wildlife close up", "fun_fact": "A lion roar can be heard up to 8 kilometers away."}}
]"""

        resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.4)
        match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
        parsed_scenes = json.loads(match.group(0)) if match else []

        # 2. Xử lý âm thanh (Tiếng kêu tự nhiên + Voice thuyết minh)
        status.update(label="🎙️ 2/4: Ghép tiếng kêu tự nhiên và voice thuyết minh...")
        scenes = []
        for idx, item in enumerate(parsed_scenes):
            key = item.get("animal_key", "cat").lower()
            fact_text = item.get("fun_fact", "")

            voice_path = os.path.join(workdir, f"voice_{idx:02d}.mp3")
            asyncio.run(generate_voice(fact_text, voice_path, is_en))

            sfx_url = ANIMAL_SOUNDS.get(key, ANIMAL_SOUNDS["cat"])
            sfx_path = os.path.join(workdir, f"sfx_{idx:02d}.mp3")
            download_file_safe(sfx_url, sfx_path)

            concat_list = os.path.join(workdir, f"concat_{idx:02d}.txt")
            with open(concat_list, "w", encoding="utf-8") as f_c:
                f_c.write(f"file '{os.path.abspath(sfx_path)}'\n")
                f_c.write(f"file '{os.path.abspath(voice_path)}'\n")

            combined_audio = os.path.join(workdir, f"combo_aud_{idx:02d}.mp3")
            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c:a", "libmp3lame", "-b:a", "192k",
                combined_audio
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            total_dur = get_audio_duration(combined_audio)
            scenes.append({
                "query": item.get("search_query", f"{key} animal"),
                "audio": combined_audio,
                "dur": max(4.5, total_dur + 0.4)
            })

        # 3. Tải clip đa nguồn (Pexels + Pixabay) và cắt chuẩn
        status.update(label="🎬 3/4: Quét B-roll đa nguồn (Pexels/Pixabay), lọc trùng lặp...")
        clips_txt = os.path.join(workdir, "clips.txt")
        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                v_url = fetch_multi_source_clip(sc["query"], pexels_key, pixabay_key, used_hashes)
                if not v_url:
                    v_url = fetch_multi_source_clip("cute wildlife animal", pexels_key, pixabay_key, used_hashes)

                raw_v = os.path.join(workdir, f"r_{idx:02d}.mp4")
                cut_v = os.path.join(workdir, f"c_{idx:02d}.mp4")
                download_file_safe(v_url, raw_v)

                cut_clip_clean(raw_v, cut_v, sc["dur"], is_port)
                if os.path.exists(raw_v):
                    os.remove(raw_v)

                synced_v = os.path.join(workdir, f"synced_{idx:02d}.mp4")
                cmd_sync = [
                    FFMPEG_EXE, "-y", "-i", cut_v, "-i", sc["audio"],
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", synced_v
                ]
                subprocess.run(cmd_sync, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")

        # 4. Xuất Master + Lồng nhạc nền thiếu nhi
        status.update(label="⚡ 4/4: Ghép toàn bộ phân cảnh và hòa âm BGM...", state="running")
        temp_merged = os.path.join(workdir, "temp_merged.mp4")
        final_mp4 = os.path.join(workdir, "kids_animals_master.mp4")

        subprocess.run([
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
            "-i", clips_txt, "-c", "copy", temp_merged
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        bgm_path = os.path.join(workdir, "kids_bgm.mp3")
        has_bgm = download_file_safe(KIDS_BGM_URL, bgm_path)

        if has_bgm:
            cmd_mix = [
                FFMPEG_EXE, "-y",
                "-i", temp_merged,
                "-stream_loop", "-1", "-i", bgm_path,
                "-filter_complex", "[0:a]volume=1.0[a0];[1:a]volume=0.12[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
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

        status.update(label="🎉 Video Animal Sounds Đa Nguồn đã hoàn tất!", state="complete")

        with open(final_mp4, "rb") as out_f:
            v_bytes = out_f.read()

        st.video(v_bytes)
        st.download_button(
            label="⬇️ Tải Video Hoàn Chỉnh Về Máy",
            data=v_bytes,
            file_name=f"kids_animals_multisource_{int(time.time())}.mp4",
            mime="video/mp4",
            use_container_width=True
        )

    except Exception as e:
        status.update(label=f"❌ Thất bại: {str(e)}", state="error")
        st.error(f"Chi tiết lỗi: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
