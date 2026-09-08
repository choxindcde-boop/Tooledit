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

st.set_page_config(page_title="Studio POV Story Master 5s", page_icon="🎬", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

# Nhạc nền điện ảnh / kịch tính an toàn
CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Story Master 5s")
st.caption("Cắt ghép đa cảnh 5s liên hoàn • AI Kể chuyện liền mạch • Hỗ trợ song ngữ Anh / Việt")

# Cấu hình kịch bản & thể loại
topic_genre = st.text_area(
    "Nhập thể loại / Chủ đề câu chuyện muốn dựng:",
    value="Một con tàu đánh cá gặp cơn bão lớn giữa đại dương đen kịt, sóng thần cuồn cuộn và cuộc chiến sinh tồn của các thủy thủ",
    placeholder="VD: Động vật đáng yêu; Tàu thuyền gặp thảm họa trên biển; Đua xe đêm mưa Tokyo; Khám phá bí ẩn sao Hỏa..."
)

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["portrait (Dọc 9:16 Shorts/TikTok/Reels)", "landscape (Ngang 16:9 YouTube Chuẩn)"])
with col_opt2:
    total_sec_input = st.number_input("Tổng thời lượng mong muốn (giây):", min_value=10, max_value=300, value=25, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ chia câu chuyện thành **{calc_clips} phân cảnh liên hoàn**, mỗi cảnh đúng 5.0 giây (tổng {calc_clips * 5}s).")

col_v1, col_v2 = st.columns(2)
with col_v1:
    language_mode = st.selectbox(
        "Ngôn ngữ thuyết minh & Kể chuyện:",
        ["Tiếng Việt (Giọng Nam trầm truyền cảm)", "Tiếng Việt (Giọng Nữ truyền hình)", "Tiếng Anh (US English - View ngoại)"]
    )
with col_v2:
    bgm_volume = st.slider("Âm lượng nhạc nền điện ảnh (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ AN TOÀN & B-ROLL ĐA NGUỒN
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

async def generate_voice(text: str, out_audio: str, lang_choice: str):
    if "Tiếng Anh" in lang_choice:
        voice_name = "en-US-AnaNeural"
    elif "Nam trầm" in lang_choice:
        voice_name = "vi-VN-NamMinhNeural"
    else:
        voice_name = "vi-VN-HoaiMyNeural"
    
    comm = edge_tts.Communicate(text, voice=voice_name, rate="+4%")
    await comm.save(out_audio)

def fetch_from_pexels(query: str, p_key: str, used_hashes: set) -> str:
    headers = {"Authorization": p_key.strip()}
    for q in [query, f"{query} cinematic", f"{query} close up"]:
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
                    target = v_files.get("large") or v_files.get("medium") or v_files.get("small")
                    if target and target.get("url"):
                        used_hashes.add(v_id)
                        return target["url"]
    except Exception:
        pass
    return None

def fetch_multi_source_clip(query: str, p_key: str, pb_key: str, used_hashes: set) -> str:
    if pb_key and random.random() > 0.5:
        clip = fetch_from_pixabay(query, pb_key, used_hashes)
        if clip:
            return clip

    clip = fetch_from_pexels(query, p_key, used_hashes)
    if not clip and pb_key:
        clip = fetch_from_pixabay(query, pb_key, used_hashes)
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
        start_sec = random.uniform(1.0, min(3.0, raw_dur - CLIP_DURATION - 0.5))

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
if st.button("🚀 Bắt Đầu Tạo Video Câu Chuyện Đa Cảnh 5s", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập thể loại hoặc chủ đề câu chuyện.")
    else:
        status = st.status(f"Đang chuẩn bị sản xuất câu chuyện gồm {calc_clips} cảnh 5s...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="story_5s_")
        used_hashes = set()
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in language_mode

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. AI viết câu chuyện liền mạch gồm đúng calc_clips câu
            status.update(label=f"🧠 1/4: AI viết kịch bản câu chuyện liền mạch gồm {calc_clips} phân đoạn...")
            lang_instruction = "English" if is_en else "Vietnamese"
            prompt = f"""You are an elite cinematic storyteller and documentary video director.
Topic/Genre: "{topic_genre}".
Number of scenes: Exactly {calc_clips} consecutive scenes.
Language: {lang_instruction}.

GOAL: Tell a continuous, gripping story across {calc_clips} scenes (each scene will be exactly 5 seconds long).
For each scene:
1. `speech_text`: One concise narrative line (under 12 words) progressing the storyline. The text must sound cinematic and immersive.
2. `query_en`: 2-3 specific English keywords for stock search matching this exact scene's visual (e.g., if ship disaster: "cargo ship storm waves", "dark ocean lightning", "ship sinking water", "rescue boat sea").

Return ONLY a valid JSON list of {calc_clips} objects:
[
  {{"scene": 1, "speech_text": "...", "query_en": "..."}},
  ...
]"""

            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.5)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            parsed_scenes = json.loads(match.group(0)) if match else []

            # Đảm bảo đủ số cảnh yêu cầu
            if len(parsed_scenes) < calc_clips:
                while len(parsed_scenes) < calc_clips:
                    idx = len(parsed_scenes) + 1
                    parsed_scenes.append({
                        "scene": idx,
                        "speech_text": f"Góc nhìn chân thực đầy kịch tính ở phân cảnh thứ {idx}.",
                        "query_en": topic_genre
                    })
            parsed_scenes = parsed_scenes[:calc_clips]

            st.write("📋 **Kịch bản câu chuyện được AI phân bổ:**")
            for sc in parsed_scenes:
                st.write(f"- **Cảnh {sc['scene']} (5s):** {sc['speech_text']} *(Tìm: `{sc['query_en']}`)*")

            # 2. Tạo Voice thuyết minh
            status.update(label="🎙️ 2/4: Đang tạo giọng đọc dẫn chuyện chuyên nghiệp...")
            scenes = []
            for idx, item in enumerate(parsed_scenes):
                voice_file = os.path.join(workdir, f"voice_{idx:02d}.mp3")
                asyncio.run(generate_voice(item["speech_text"], voice_file, language_mode))

                scenes.append({
                    "query": item["query_en"],
                    "audio": voice_file,
                    "dur": CLIP_DURATION
                })

            # 3. Tải B-roll đa nguồn & cắt đúng 5.0 giây
            status.update(label="🎬 3/4: Đang tải các góc máy khác biệt từ Pexels & Pixabay...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = fetch_multi_source_clip(sc["query"], pexels_key, pixabay_key, used_hashes)
                    if not v_url:
                        v_url = fetch_multi_source_clip(topic_genre, pexels_key, pixabay_key, used_hashes)

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

            # 4. Xuất Master + Lồng BGM điện ảnh
            status.update(label="⚡ 4/4: Ghép thành video hoàn chỉnh và hòa âm BGM...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "story_master_5s.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_path = os.path.join(workdir, "bgm.mp3")
            has_bgm = (bgm_volume > 0) and download_file_safe(CINEMATIC_BGM_URL, bgm_path)
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

            status.update(label=f"🎉 Hoàn thành video câu chuyện {calc_clips * 5}s xuất sắc!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
                data=v_bytes,
                file_name=f"story_5s_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
