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

st.set_page_config(page_title="Studio POV Master Pro Max", page_icon="⚡", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

# DANH SÁCH GATEWAY INVIDIOUS VƯỢT BOT-CHECK YOUTUBE
INVIDIOUS_INSTANCES = [
    "https://inv.tux.pizza",
    "https://invidious.nerdvpn.de",
    "https://invidious.private.coffee",
    "https://yt.artemislena.eu"
]

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets.get("PEXELS_API_KEY", "")
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình API Key trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("⚡ Studio POV Master Pro Max (YouTube Direct Footage)")
st.caption("Cào trực tiếp YouTube Footage qua Invidious Gateway • Giữ nguyên tiếng hiện trường • Chuẩn phong cách Seconds Before Disaster")

# ==============================================================================
# DANH MỤC THỂ LOẠI
# ==============================================================================
CATEGORY_SETTINGS = {
    "💥 Tổng hợp tai nạn, thảm họa, khoảnh khắc hiểm nghèo thực tế": {
        "engine": "youtube_invidious",
        "default_topic": "Incredible plane crashes emergency landing and cargo ship heavy storm waves caught on camera",
        "search_pool": [
            "airplane emergency landing incident real footage caught on camera",
            "cargo ship heavy storm waves rough sea caught on camera",
            "airplane crosswind rough landing extreme",
            "ship disaster massive ocean wave hitting boat"
        ],
        "default_voice": "Tiếng Anh: Guy (Nam thời sự / Thảm họa Seconds Before Disaster)",
        "prompt_tone": "Khẩn cấp, dồn dập, nguy hiểm tột độ phong cách phóng sự Seconds Before Disaster"
    },
    "🐾 Thế giới Động vật / Thú cưng dễ thương": {
        "engine": "stock_only",
        "default_topic": "Những khoảnh khắc ngộ nghĩnh đáng yêu của thú cưng và muôn loài động vật hoang dã",
        "search_pool": [
            ("cute golden retriever puppy playing barking", "puppy dog"),
            ("baby panda climbing bamboo", "baby panda"),
            ("little kitten playing meowing", "kitten cat"),
            ("fluffy bunny rabbit eating carrot", "cute bunny")
        ],
        "default_voice": "Tiếng Anh: Ana (Giọng hoạt hình / Vui tươi)",
        "prompt_tone": "Ngộ nghĩnh, tươi vui, tràn ngập năng lượng tích cực và đáng yêu"
    },
    "🏎️ Siêu xe / Tốc độ / Đua đêm Tokyo": {
        "engine": "stock_only",
        "default_topic": "Những màn drift nghẹt thở của dàn siêu xe triệu đô trên đường cao tốc đêm",
        "search_pool": [
            ("supercar drifting night city street loud exhaust", "drift car night"),
            ("sports car speeding highway exhaust flames", "sports car speed"),
            ("neon cyberpunk race car launch control", "supercar acceleration")
        ],
        "default_voice": "Tiếng Anh: Christopher (Trầm khàn / Phim tài liệu)",
        "prompt_tone": "Hồi hộp, uy lực, phấn khích với tốc độ và âm thanh động cơ gầm rú"
    },
    "🌌 Khám phá / Khoa học viễn tưởng / Vũ trụ": {
        "engine": "stock_only",
        "default_topic": "Hành trình khám phá hố đen tử thần và những tàn tích văn minh cổ đại bí ẩn",
        "search_pool": [
            ("deep space nebula galaxy stars", "space exploration"),
            ("ancient ruins temple drone cinematic", "ancient civilization"),
            ("astronaut walking on mars surface", "astronaut space")
        ],
        "default_voice": "Tiếng Anh: Christopher (Trầm khàn / Phim tài liệu)",
        "prompt_tone": "Hùng vĩ, bí ẩn, mang tính khám phá vũ trụ sâu sắc"
    }
}

selected_cat_name = st.selectbox("Chọn thể loại video chính:", list(CATEGORY_SETTINGS.keys()))
cat_config = CATEGORY_SETTINGS[selected_cat_name]

topic_text = st.text_area(
    "Mô tả chi tiết kịch bản / Tình huống:",
    value=cat_config["default_topic"],
    height=80
)

col1, col2 = st.columns(2)
with col1:
    voice_choice = st.selectbox(
        "Giọng đọc thuyết minh:",
        [
            cat_config["default_voice"],
            "Tiếng Anh: Guy (Nam thời sự / Thảm họa Seconds Before Disaster)",
            "Tiếng Anh: Christopher (Trầm khàn / Phim tài liệu)",
            "Tiếng Anh: Ana (Giọng hoạt hình / Thiếu nhi)",
            "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
            "Tiếng Việt: Hoài My (Nữ truyền cảm / Nhẹ nhàng)"
        ]
    )
with col2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=120, value=20, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ sản xuất **{calc_clips} phân cảnh chuẩn xác** (mỗi cảnh đúng 5.0 giây).")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])
with col_opt2:
    raw_vol = st.slider("Âm lượng tiếng hiện trường (Gió/Động cơ/Sóng/Còi) (%):", min_value=40, max_value=200, value=120, step=10)

bgm_volume = st.slider("Âm lượng nhạc nền ngầm BGM (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM CÀO YOUTUBE QUA INVIDIOUS GATEWAY
# ==============================================================================

def search_youtube_invidious_stream(query: str, used_hashes: set) -> tuple:
    """Tìm kiếm YouTube qua Invidious API để lấy trực tiếp URL stream MP4 có âm thanh"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    random.shuffle(INVIDIOUS_INSTANCES)
    
    for instance in INVIDIOUS_INSTANCES:
        try:
            search_api = f"{instance}/api/v1/search?q={urllib.parse.quote(query)}&type=video&sort_by=relevance"
            r = requests.get(search_api, headers=headers, timeout=5)
            if r.ok:
                items = r.json()
                for item in items:
                    v_id = item.get("videoId")
                    dur = item.get("lengthSeconds", 0)
                    if v_id and v_id not in used_hashes and 15 <= dur <= 600:
                        # Lấy format video stream
                        vid_api = f"{instance}/api/v1/videos/{v_id}"
                        vr = requests.get(vid_api, headers=headers, timeout=5)
                        if vr.ok:
                            v_data = vr.json()
                            formats = v_data.get("formatStreams", [])
                            # Chọn format có sẵn cả hình lẫn tiếng (thường là 360p hoặc 720p container MP4)
                            target_stream = next((f["url"] for f in formats if f.get("container") == "mp4" and f.get("resolution") in ["720p", "480p", "360p"]), None)
                            if not target_stream and formats:
                                target_stream = formats[0].get("url")
                            if target_stream:
                                used_hashes.add(v_id)
                                return target_stream, dur
        except Exception:
            continue
    return None, 0

def fetch_stock_clip(query: str, p_key: str, pb_key: str, used_hashes: set, dest_path: str) -> bool:
    headers = {"Authorization": p_key.strip()} if p_key else {}
    if p_key:
        try:
            url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=10&page=1"
            r = requests.get(url, headers=headers, timeout=5)
            if r.ok and r.json().get("videos"):
                for v in r.json()["videos"]:
                    v_id = f"pexels_{v.get('id')}"
                    if v_id not in used_hashes:
                        files = v.get("video_files", [])
                        hd = next((f["link"] for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"), None)
                        if not hd and files:
                            hd = files[0].get("link")
                        if hd:
                            # Tải nhanh
                            with requests.get(hd, headers=headers, stream=True, timeout=8) as resp:
                                if resp.status_code == 200:
                                    with open(dest_path, "wb") as f:
                                        for chunk in resp.iter_content(chunk_size=32768):
                                            f.write(chunk)
                            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 15000:
                                used_hashes.add(v_id)
                                return True
        except Exception:
            pass
    return False

# ==============================================================================
# HÀM XỬ LÝ ÂM THANH & RENDER PHÂN ĐOẠN 5.0S
# ==============================================================================

async def generate_voice(text: str, out_audio: str, voice_option: str):
    if "Christopher" in voice_option:
        v_code = "en-US-ChristopherNeural"
    elif "Guy" in voice_option:
        v_code = "en-US-GuyNeural"
    elif "Ana" in voice_option:
        v_code = "en-US-AnaNeural"
    elif "Nam Minh" in voice_option:
        v_code = "vi-VN-NamMinhNeural"
    else:
        v_code = "vi-VN-HoaiMyNeural"

    comm = edge_tts.Communicate(text, voice=v_code, rate="+4%")
    await comm.save(out_audio)

def cut_stream_and_render_5s(stream_url_or_file: str, total_dur: float, voice_mp3: str, out_p: str, is_port: bool, raw_vol_float: float, workdir: str, idx: int):
    """
    Kéo trực tiếp 5.0 giây từ luồng URL hoặc file:
    - Đọc tuần tự qua HTTP stream bằng FFmpeg (chỉ tốn vài trăm KB băng thông).
    - Giữ nguyên luồng âm thanh gốc của YouTube (tiếng sóng biển, va chạm, gió rít).
    - Chuẩn hóa WAV 44.1kHz Stereo chống hoàn toàn lỗi 254.
    """
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"

    # Lấy điểm cắt từ 20% đến 60% thời lượng video để bốc đúng đoạn cao trào
    start_sec = 2.0
    if total_dur > (CLIP_DURATION + 4.0):
        start_sec = random.uniform(total_dur * 0.15, min(total_dur * 0.6, total_dur - CLIP_DURATION - 1.0))

    temp_v = os.path.join(workdir, f"tmp_v_{idx:03d}.mp4")
    norm_env_wav = os.path.join(workdir, f"tmp_env_{idx:03d}.wav")
    norm_voice_wav = os.path.join(workdir, f"tmp_voice_{idx:03d}.wav")

    # 1. Cắt video hình ảnh từ Stream URL
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", stream_url_or_file,
        "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f,
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        temp_v
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. Cắt âm thanh hiện trường gốc từ Stream URL (chuẩn hóa sang WAV 44.1kHz Stereo)
    cmd_audio = [
        FFMPEG_EXE, "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", stream_url_or_file,
        "-t", f"{CLIP_DURATION:.3f}",
        "-ar", "44100", "-ac", "2",
        norm_env_wav
    ]
    res_a = subprocess.run(cmd_audio, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Nếu luồng không có audio, bù tiếng động cơ / bão nhẹ
    if res_a.returncode != 0 or not os.path.exists(norm_env_wav) or os.path.getsize(norm_env_wav) < 5000:
        subprocess.run([
            FFMPEG_EXE, "-y",
            "-f", "lavfi", "-i", "anoisesrc=d=5:c=brown:r=44100:a=0.35",
            "-af", "lowpass=f=1200,tremolo=f=1.0:d=0.7",
            "-t", f"{CLIP_DURATION:.3f}",
            "-ar", "44100", "-ac", "2",
            norm_env_wav
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Chuẩn hóa voice đọc
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", voice_mp3,
        "-t", f"{CLIP_DURATION:.3f}",
        "-ar", "44100", "-ac", "2",
        norm_voice_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. Hòa âm tiếng hiện trường rõ nét + voice đọc
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", temp_v,
        "-i", norm_env_wav,
        "-i", norm_voice_wav,
        "-filter_complex",
        f"[1:a]volume={raw_vol_float:.2f},afade=t=in:ss=0:d=0.15,afade=t=out:st=4.8:d=0.2[a_env];[2:a]volume=1.0[a_voice];[a_env][a_voice]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{CLIP_DURATION:.3f}",
        out_p
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    for p in [temp_v, norm_env_wav, norm_voice_wav]:
        if os.path.exists(p):
            os.remove(p)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Sản Xuất Video Thật 100%", use_container_width=True, type="primary"):
    status = st.status(f"Hệ thống đang khởi động pipeline cào dữ liệu...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_yt_invidious_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in voice_choice
    raw_vol_float = raw_vol / 100.0
    total_video_time = calc_clips * CLIP_DURATION

    try:
        client = Groq(api_key=groq_key.strip())

        # 1. AI biên soạn kịch bản
        status.update(label=f"🧠 1/4: {LLM_MODEL} đang xây dựng câu chuyện kịch tính...")
        engine_mode = cat_config["engine"]
        pool = cat_config["search_pool"]

        prompt = f"""You are a professional documentary video director for viral channels like 'Seconds Before Disaster'.
Category: "{selected_cat_name}".
User prompt: "{topic_text}".
Total scenes: Exactly {calc_clips} scenes (5.0s each).
Language: {"English" if is_en else "Vietnamese"}.

STRICT RULES:
- Alternate subjects if multiple exist (e.g. plane landing vs cargo ship storm).
- `query_en`: 3-4 specific search keywords for real footage on YouTube (e.g., 'airplane emergency landing caught on camera', 'cargo ship massive storm waves rough sea', 'airplane crosswind landing extreme').
- `speech_text`: One dramatic narrative sentence under 12 words (~3.2 seconds).

Return ONLY a JSON list of {calc_clips} objects:
[
  {{"scene": 1, "speech_text": "...", "query_en": "airplane emergency landing caught on camera"}},
  {{"scene": 2, "speech_text": "...", "query_en": "cargo ship massive waves rough sea storm"}}
]"""

        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        raw_text = resp.choices[0].message.content.strip()
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        parsed_scenes = json.loads(match.group(0)) if match else []

        while len(parsed_scenes) < calc_clips:
            idx = len(parsed_scenes)
            q_val = pool[idx % len(pool)] if isinstance(pool[0], str) else pool[idx % len(pool)][0]
            parsed_scenes.append({
                "scene": idx + 1,
                "speech_text": f"Tình huống nguy cấp diễn biến dữ dội ở phân cảnh {idx + 1}.",
                "query_en": q_val
            })
        parsed_scenes = parsed_scenes[:calc_clips]

        # 2. Tạo Voice
        status.update(label="🎙️ 2/4: Đang tạo giọng đọc thuyết minh kịch tính...")
        scenes = []
        for idx, item in enumerate(parsed_scenes):
            v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
            asyncio.run(generate_voice(item["speech_text"], v_file, voice_choice))
            scenes.append({
                "query": item["query_en"],
                "audio": v_file
            })

        # 3. Tải Footage & Render 5.0s
        clips_txt = os.path.join(workdir, "clips.txt")

        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                status.update(label=f"🎬 3/4: Đang cào YouTube và xử lý phân cảnh {idx+1}/{calc_clips}...")
                scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                if engine_mode == "youtube_invidious":
                    stream_url, dur = search_youtube_invidious_stream(sc["query"], used_hashes)
                    if not stream_url:
                        # Thử từ khóa backup
                        backup_query = pool[idx % len(pool)]
                        stream_url, dur = search_youtube_invidious_stream(backup_query, used_hashes)

                    if stream_url:
                        cut_stream_and_render_5s(stream_url, dur, sc["audio"], scene_v, is_port, raw_vol_float, workdir, idx)
                    else:
                        # Dự phòng nhanh nếu toàn bộ gateway nghẽn mạng
                        fallback_file = os.path.join(workdir, f"fallback_{idx:03d}.mp4")
                        fetch_stock_clip("ocean storm waves", pexels_key, pixabay_key, used_hashes, fallback_file)
                        cut_stream_and_render_5s(fallback_file, 15.0, sc["audio"], scene_v, is_port, raw_vol_float, workdir, idx)
                else:
                    stock_file = os.path.join(workdir, f"stock_{idx:03d}.mp4")
                    fetch_stock_clip(sc["query"], pexels_key, pixabay_key, used_hashes, stock_file)
                    cut_stream_and_render_5s(stock_file, 15.0, sc["audio"], scene_v, is_port, raw_vol_float, workdir, idx)

                f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

        # 4. Nối cảnh & Ép hòa âm BGM
        status.update(label="⚡ 4/4: Ghép Master và xuất bản video thành phẩm...", state="running")
        temp_merged = os.path.join(workdir, "temp_merged.mp4")
        final_mp4 = os.path.join(workdir, "master_disaster_youtube.mp4")

        subprocess.run([
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
            "-i", clips_txt, "-c", "copy", temp_merged
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        bgm_raw = os.path.join(workdir, "bgm_raw.mp3")
        bgm_fitted = os.path.join(workdir, "bgm_fitted.wav")
        
        # Tải BGM
        headers = {"User-Agent": "Mozilla/5.0"}
        r_bgm = requests.get(CINEMATIC_BGM_URL, headers=headers, timeout=10)
        has_bgm = False
        if r_bgm.ok:
            with open(bgm_raw, "wb") as f:
                f.write(r_bgm.content)
            has_bgm = True

        if has_bgm and bgm_volume > 0:
            subprocess.run([
                FFMPEG_EXE, "-y",
                "-stream_loop", "-1", "-i", bgm_raw,
                "-t", f"{total_video_time:.3f}",
                "-ar", "44100", "-ac", "2",
                bgm_fitted
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            vol_bgm_float = bgm_volume / 100.0
            subprocess.run([
                FFMPEG_EXE, "-y",
                "-i", temp_merged,
                "-i", bgm_fitted,
                "-filter_complex",
                f"[0:a]volume=1.0[a0];[1:a]volume={vol_bgm_float:.2f}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-t", f"{total_video_time:.3f}",
                final_mp4
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            shutil.copy(temp_merged, final_mp4)

        status.update(label=f"🎉 Hoàn thành video {calc_clips * 5} giây chuẩn YouTube thực tế!", state="complete")

        with open(final_mp4, "rb") as out_f:
            v_bytes = out_f.read()

        st.video(v_bytes)
        st.download_button(
            label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
            data=v_bytes,
            file_name=f"disaster_youtube_{calc_clips * 5}s_{int(time.time())}.mp4",
            mime="video/mp4",
            use_container_width=True
        )

    except Exception as e:
        status.update(label=f"❌ Thất bại: {str(e)}", state="error")
        st.error(f"Chi tiết lỗi: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
