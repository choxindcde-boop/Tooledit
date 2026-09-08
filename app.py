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

st.set_page_config(page_title="Studio POV Story Master Pro", page_icon="⚡", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
DRAMA_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong Secrets của Streamlit Cloud!")
    st.stop()

st.title("⚡ Studio Cinematic Story Master Pro")
st.caption("Khóa chặt chủ thể hình ảnh • 100% có mặt nhân vật/động vật • Cắt nối chuẩn nhịp 5s")

topic_genre = st.text_area(
    "Nhập chủ đề kịch bản chi tiết:",
    value="Những loài động vật con đáng yêu nhất thế giới tự nhiên và những khoảnh khắc vui đùa ngộ nghĩnh",
    height=90
)

col_t1, col_t2 = st.columns(2)
with col_t1:
    genre_type = st.selectbox(
        "Thể loại video:",
        [
            "Thế giới Động vật / Thú cưng (Animals / Pets)",
            "Thảm họa / Kịch tính / Bão biển / Sinh tồn (Storm / Disaster)",
            "Siêu xe / Tốc độ / Đua đêm (Supercars / Speed)",
            "Khám phá / Lịch sử / Khoa học (Exploration / Science)"
        ]
    )
with col_t2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=300, value=25, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)

col_v1, col_v2 = st.columns(2)
with col_v1:
    voice_choice = st.selectbox(
        "Ngôn ngữ & Giọng đọc:",
        [
            "Tiếng Anh: Christopher (Giọng tài liệu trầm khàn chuẩn Tây)",
            "Tiếng Anh: Ana (Giọng hoạt hình / động vật vui vẻ)",
            "Tiếng Anh: Guy (Nam kể chuyện cuốn hút)",
            "Tiếng Việt: Nam Minh (Nam trầm tài liệu / thời sự)",
            "Tiếng Việt: Hoài My (Nữ truyền cảm)"
        ]
    )
with col_v2:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube)", "portrait (Dọc 9:16 Shorts/TikTok)"])

bgm_volume = st.slider("Âm lượng nhạc nền (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ
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

async def generate_voice(text: str, out_audio: str, voice_option: str):
    if "Christopher" in voice_option:
        v_code = "en-US-ChristopherNeural"
    elif "Ana" in voice_option:
        v_code = "en-US-AnaNeural"
    elif "Guy" in voice_option:
        v_code = "en-US-GuyNeural"
    elif "Nam Minh" in voice_option:
        v_code = "vi-VN-NamMinhNeural"
    else:
        v_code = "vi-VN-HoaiMyNeural"

    comm = edge_tts.Communicate(text, voice=v_code, rate="+3%")
    await comm.save(out_audio)

def fetch_pexels_clip(query: str, p_key: str, used_hashes: set) -> str:
    headers = {"Authorization": p_key.strip()}
    for page in [1, 2, 3]:
        try:
            url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=12&page={page}"
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

def fetch_pixabay_clip(query: str, pb_key: str, used_hashes: set) -> str:
    if not pb_key or not pb_key.strip():
        return None
    try:
        url = f"{PIXABAY_VIDEO_URL}?key={pb_key.strip()}&q={urllib.parse.quote(query)}&per_page=15"
        r = requests.get(url, timeout=8)
        if r.ok and r.json().get("hits"):
            hits = r.json()["hits"]
            random.shuffle(hits)
            for v in hits:
                v_id = f"pixabay_{v.get('id')}"
                if v_id not in used_hashes:
                    v_files = v.get("videos", {})
                    target = v_files.get("large") or v_files.get("medium") or v_files.get("small")
                    if target and target.get("url"):
                        used_hashes.add(v_id)
                        return target["url"]
    except Exception:
        pass
    return None

def get_exact_subject_clip(query: str, fallback_query: str, p_key: str, pb_key: str, used_hashes: set) -> str:
    # 1. Tìm bằng từ khóa chi tiết của con vật/tàu
    clip = fetch_pexels_clip(query, p_key, used_hashes)
    if not clip and pb_key:
        clip = fetch_pixabay_clip(query, pb_key, used_hashes)
    
    # 2. Nếu không có, tìm bằng từ khóa dự phòng trực diện
    if not clip:
        clip = fetch_pexels_clip(fallback_query, p_key, used_hashes)
    if not clip and pb_key:
        clip = fetch_pixabay_clip(fallback_query, pb_key, used_hashes)
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
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Sản Xuất Video Chuẩn Chủ Thể 100%", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập chủ đề kịch bản.")
    else:
        status = st.status(f"Đang phân tích kịch bản và khóa chủ thể ({calc_clips} cảnh)...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="master_exact_")
        used_hashes = set()
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in voice_choice

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. Ép AI chỉ sinh danh từ động vật / tàu thuyền cụ thể
            status.update(label=f"🧠 1/4: AI khóa chặt chủ thể danh từ cụ thể cho từng cảnh...")
            prompt = f"""You are a professional video director.
Topic: "{topic_genre}".
Genre: "{genre_type}".
Total scenes: Exactly {calc_clips} scenes (each is 5 seconds).
Language: {"English" if is_en else "Vietnamese"}.

STRICT INSTRUCTION:
- If Topic is ANIMALS: `query_en` MUST be a specific animal noun + action: `cute puppy playing`, `baby panda eating`, `kitten close up`, `sea otter swimming`, `fluffy bunny rabbit`. NEVER use landscape words like 'forest', 'meadow', 'sunlight', 'tree'.
- If Topic is SHIP / STORM: `query_en` MUST be: `cargo ship storm waves`, `massive ocean wave`, `lightning dark sea`, `fishing boat rough ocean`.
- `fallback_en`: 2 simple words identifying the exact subject (e.g. `cute puppy`, `baby panda`, `ship storm`).
- `speech_text`: A continuous, engaging sentence under 12 words that reads in ~3 seconds.

Return ONLY a valid JSON list of {calc_clips} objects:
[
  {{"scene": 1, "speech_text": "...", "query_en": "cute puppy playing", "fallback_en": "cute dog"}},
  {{"scene": 2, "speech_text": "...", "query_en": "baby panda eating bamboo", "fallback_en": "baby panda"}}
]"""

            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            parsed_scenes = json.loads(match.group(0)) if match else []

            # Danh sách dự phòng nếu LLM thiếu cảnh
            animal_pool = [
                ("cute puppy dog", "puppy dog"),
                ("baby panda climbing", "baby panda"),
                ("cute kitten playing", "kitten cat"),
                ("fluffy bunny rabbit", "cute rabbit"),
                ("sea otter floating", "sea otter"),
                ("little duckling swimming", "cute duckling")
            ]
            while len(parsed_scenes) < calc_clips:
                idx = len(parsed_scenes)
                pick = animal_pool[idx % len(animal_pool)]
                parsed_scenes.append({
                    "scene": idx + 1,
                    "speech_text": "These adorable moments bring pure joy and wonder to our world." if is_en else "Những khoảnh khắc đáng yêu này mang lại niềm vui bất tận.",
                    "query_en": pick[0],
                    "fallback_en": pick[1]
                })
            parsed_scenes = parsed_scenes[:calc_clips]

            # 2. Tạo Voice thuyết minh
            status.update(label="🎙️ 2/4: Đang tạo giọng đọc thuyết minh...")
            scenes = []
            for idx, item in enumerate(parsed_scenes):
                voice_file = os.path.join(workdir, f"voice_{idx:02d}.mp3")
                asyncio.run(generate_voice(item["speech_text"], voice_file, voice_choice))

                scenes.append({
                    "query": item["query_en"],
                    "fallback": item.get("fallback_en", "cute animal"),
                    "audio": voice_file,
                    "dur": CLIP_DURATION
                })

            # 3. Tải B-roll đúng chủ thể 100%
            status.update(label="🎬 3/4: Đang tải B-roll đúng chuẩn chủ thể (không lấy cảnh rác)...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = get_exact_subject_clip(sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes)
                    if not v_url:
                        v_url = get_exact_subject_clip("cute puppy dog", "cat", pexels_key, pixabay_key, used_hashes)

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

            # 4. Xuất Master + Lồng BGM
            status.update(label="⚡ 4/4: Ghép video hoàn chỉnh & hòa âm Master...", state="running")
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

            status.update(label=f"🎉 Hoàn thành video {calc_clips * 5}s chuẩn xác!", state="complete")

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
