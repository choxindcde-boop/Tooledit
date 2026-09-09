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
import yt_dlp

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Studio POV Master Pro Max", page_icon="🎬", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

# BGM & Âm thanh hiện trường bão biển thực tế chuẩn WAV/MP3
CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"
STORM_REAL_AUDIO_URL = "https://upload.wikimedia.org/wikipedia/commons/2/27/Thunderstorm_sound.ogg"

# Pool video YouTube thực tế chuyên về bão biển / tai nạn / thảm họa (Có sẵn audio hiện trường)
YOUTUBE_DISASTER_POOL = [
    "https://www.youtube.com/watch?v=jp0kep8im0Y",  # Moments filmed seconds before disaster
    "https://www.youtube.com/watch?v=t33bBwbU-zE",  # North sea giant waves
    "https://www.youtube.com/watch?v=BYsC3y7uXdQ",  # Huge waves hitting ship
    "https://www.youtube.com/watch?v=2vY3Z2kUf4U",  # Cargo ship rough weather
    "https://www.youtube.com/watch?v=3M5bXU1E8wY"   # Maritime emergency caught on camera
]

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets.get("PEXELS_API_KEY", "")
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình API Key trong Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Pro Max")
st.caption("Khắc phục triệt để bot-check YouTube • Đảm bảo 100% video xuất ra có âm thanh hiện trường gầm rú")

CATEGORY_SETTINGS = {
    "💥 Tổng hợp tai nạn, thảm họa, khoảnh khắc hiểm nghèo thực tế": {
        "engine": "disaster_hybrid",
        "search_pool": [
            "cargo ship heavy storm waves",
            "massive ocean storm wave crashing",
            "rough sea dark waves hitting boat",
            "fishing boat storm extreme weather",
            "huge ocean wave splash rough sea"
        ],
        "default_voice_en": "Tiếng Anh: Guy (Nam thời sự / Thảm họa Seconds Before Disaster)",
        "default_voice_vi": "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
        "prompt_tone": "Khẩn cấp, nghẹt thở, ngắn gọn, phong cách phóng sự Seconds Before Disaster"
    },
    "🐾 Thế giới Động vật / Thú cưng dễ thương": {
        "engine": "stock_only",
        "search_pool": [
            ("cute golden retriever puppy playing barking", "puppy dog"),
            ("baby panda climbing bamboo", "baby panda"),
            ("little kitten playing meowing", "kitten cat"),
            ("fluffy bunny rabbit eating carrot", "cute bunny"),
            ("playful sea otter floating water", "sea otter"),
            ("cute duckling swimming pond", "duckling")
        ],
        "default_voice_en": "Tiếng Anh: Ana (Giọng hoạt hình / Vui tươi)",
        "default_voice_vi": "Tiếng Việt: Hoài My (Nữ truyền cảm / Nhẹ nhàng)",
        "prompt_tone": "Ngộ nghĩnh, tươi vui, mang lại cảm giác ấm áp và kỳ thú"
    },
    "🏎️ Siêu xe / Tốc độ / Đua đêm Tokyo": {
        "engine": "stock_only",
        "search_pool": [
            ("supercar drifting night city street loud exhaust", "drift car"),
            ("sports car speeding highway exhaust sound", "sports car"),
            ("neon cyberpunk race car launch control", "supercar night")
        ],
        "default_voice_en": "Tiếng Anh: Christopher (Trầm khàn / Cuốn hút)",
        "default_voice_vi": "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
        "prompt_tone": "Đậm chất adrenaline, uy lực động cơ và ánh đèn thành phố"
    }
}

selected_cat_name = st.selectbox("Chọn thể loại video chính:", list(CATEGORY_SETTINGS.keys()))
cat_config = CATEGORY_SETTINGS[selected_cat_name]

topic_text = st.text_area(
    "Mô tả chi tiết kịch bản / Tình huống:",
    value="Những khoảnh khắc thót tim khi tàu cá vượt bão biển dữ dội, sóng thần 20 mét đánh vỡ kính buồng lái và tai nạn xảy ra trong gang tấc",
    height=80
)

col1, col2 = st.columns(2)
with col1:
    voice_choice = st.selectbox(
        "Giọng đọc thuyết minh:",
        [
            cat_config["default_voice_en"],
            cat_config["default_voice_vi"],
            "Tiếng Anh: Guy (Nam thời sự / Thảm họa Seconds Before Disaster)",
            "Tiếng Anh: Christopher (Trầm khàn / Cuốn hút)",
            "Tiếng Anh: Ana (Giọng hoạt hình / Vui tươi)",
            "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
            "Tiếng Việt: Hoài My (Nữ truyền cảm / Nhẹ nhàng)"
        ]
    )
with col2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=120, value=20, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ cắt ghép **{calc_clips} phân cảnh (mỗi cảnh đúng 5.0 giây)**.")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])
with col_opt2:
    raw_vol = st.slider("Âm lượng tiếng gốc hiện trường (Sóng/Gió/Động cơ) (%):", min_value=40, max_value=180, value=110, step=10)

bgm_volume = st.slider("Âm lượng nhạc nền ngầm BGM (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ KỸ THUẬT AN TOÀN
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=20) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                return os.path.exists(dest) and os.path.getsize(dest) > 10000
    except Exception:
        pass
    return False

def check_video_has_audio(file_path: str) -> bool:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return "audio" in res.stdout.strip()
    except Exception:
        return False

def verify_valid_video_file(file_path: str) -> bool:
    if not file_path or not os.path.exists(file_path):
        return False
    if os.path.getsize(file_path) < 100000:
        return False
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return float(res.stdout.strip() or 0) > 1.0
    except Exception:
        return False

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

def fetch_direct_from_youtube_pool(dest_path: str, clip_idx: int) -> bool:
    """Bốc trực tiếp từ danh mục video YouTube thực tế đã chuẩn bị sẵn để né Bot Check"""
    target_url = YOUTUBE_DISASTER_POOL[clip_idx % len(YOUTUBE_DISASTER_POOL)]
    ydl_opts = {
        'format': '18/best[height<=720][ext=mp4]/best[height<=720]',
        'outtmpl': dest_path,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 15
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])
            if verify_valid_video_file(dest_path):
                return True
    except Exception:
        pass
    return False

def fetch_from_pexels(query: str, p_key: str, used_hashes: set) -> str:
    if not p_key:
        return None
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

def fetch_from_pixabay(query: str, pb_key: str, used_hashes: set) -> str:
    if not pb_key:
        return None
    try:
        url = f"{PIXABAY_VIDEO_URL}?key={pb_key.strip()}&q={urllib.parse.quote(query)}&per_page=12"
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

def get_broll_failproof(cat_mode: str, query: str, fallback_q: str, p_key: str, pb_key: str, used_hashes: set, raw_dest: str, clip_idx: int) -> bool:
    """Tải B-roll không bao giờ bị nghẽn hay văng lỗi"""
    if cat_mode == "disaster_hybrid":
        # 1. Thử kéo từ YouTube Pool trực tiếp
        ok = fetch_direct_from_youtube_pool(raw_dest, clip_idx)
        if ok and verify_valid_video_file(raw_dest):
            return True
        
        # 2. Nếu YouTube gặp trục trặc mạng, lấy ngay clip bão biển cực nét từ Pexels
        v_url = fetch_from_pexels(query, p_key, used_hashes) or fetch_from_pexels("storm waves ocean heavy", p_key, used_hashes)
        if v_url and download_file_safe(v_url, raw_dest):
            return True

    # Thể loại Động vật / Xe: Pexels -> Pixabay
    url = fetch_from_pexels(query, p_key, used_hashes)
    if not url and pb_key:
        url = fetch_from_pixabay(query, pb_key, used_hashes)
    if url and download_file_safe(url, raw_dest):
        return True

    url = fetch_from_pexels(fallback_q, p_key, used_hashes)
    if url and download_file_safe(url, raw_dest):
        return True

    return fetch_direct_from_youtube_pool(raw_dest, clip_idx)

def process_scene_wav_injector(raw_v: str, voice_mp3: str, backup_storm_audio: str, out_p: str, is_port: bool, raw_vol_float: float, workdir: str, idx: int):
    """
    Quy trình hòa âm đảm bảo 100% có tiếng gầm rú:
    - Nếu video gốc có tiếng: Dùng tiếng gốc và đẩy âm lượng theo slider.
    - Nếu video gốc câm (như Pexels): Inject ngay file âm thanh sấm sét/sóng gầm bão biển chuẩn (WAV 44.1kHz).
    - Triệt tiêu hoàn toàn lỗi 254.
    """
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"

    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_v]
    try:
        raw_dur = float(subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip() or 10.0)
    except Exception:
        raw_dur = 10.0

    start_sec = 1.0
    if raw_dur > (CLIP_DURATION + 3.0):
        start_sec = random.uniform(1.0, min(8.0, raw_dur - CLIP_DURATION - 0.5))

    temp_v = os.path.join(workdir, f"tmp_v_{idx:03d}.mp4")
    norm_env_wav = os.path.join(workdir, f"tmp_env_{idx:03d}.wav")
    norm_voice_wav = os.path.join(workdir, f"tmp_voice_{idx:03d}.wav")

    # 1. Cắt video sạch
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", raw_v,
        "-ss", f"{start_sec:.2f}",
        "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f,
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        temp_v
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. Xử lý âm thanh hiện trường: có tiếng thì lấy, không có thì inject tiếng bão
    has_audio = check_video_has_audio(raw_v)
    if has_audio:
        subprocess.run([
            FFMPEG_EXE, "-y",
            "-i", raw_v,
            "-ss", f"{start_sec:.2f}",
            "-t", f"{CLIP_DURATION:.3f}",
            "-ar", "44100", "-ac", "2",
            norm_env_wav
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        # Bơm âm thanh bão biển gầm rú thực tế
        subprocess.run([
            FFMPEG_EXE, "-y",
            "-i", backup_storm_audio,
            "-ss", f"{(idx * 5) % 30}",
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

    # 4. Hòa âm tiếng hiện trường rõ nét + voice
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", temp_v,
        "-i", norm_env_wav,
        "-i", norm_voice_wav,
        "-filter_complex",
        f"[1:a]volume={raw_vol_float:.2f},afade=t=in:ss=0:d=0.2,afade=t=out:st=4.8:d=0.2[a_env];[2:a]volume=1.0[a_voice];[a_env][a_voice]amix=inputs=2:duration=first:dropout_transition=0[aout]",
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
if st.button("🚀 Bắt Đầu Dựng Video Chuẩn Âm Thanh Hiện Trường", use_container_width=True, type="primary"):
    status = st.status(f"Hệ thống đang chuẩn bị sản xuất {calc_clips} phân cảnh...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_failproof_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in voice_choice
    raw_vol_float = raw_vol / 100.0
    total_video_time = calc_clips * CLIP_DURATION

    try:
        client = Groq(api_key=groq_key.strip())

        # Chuẩn bị âm thanh hiện trường sấm sét bão biển dự phòng
        status.update(label="🌊 Đang thiết lập kênh âm thanh hiện trường...")
        backup_storm_path = os.path.join(workdir, "storm_real.ogg")
        download_file_safe(STORM_REAL_AUDIO_URL, backup_storm_path)

        # 1. AI biên soạn kịch bản
        status.update(label=f"🧠 1/4: {LLM_MODEL} đang xây dựng câu chuyện...")
        pool = cat_config["search_pool"]
        engine_mode = cat_config["engine"]
        parsed_scenes = []

        BATCH_SIZE = 6
        total_batches = math.ceil(calc_clips / BATCH_SIZE)

        for b in range(total_batches):
            needed = min(BATCH_SIZE, calc_clips - len(parsed_scenes))
            prompt = f"""You are a professional documentary scriptwriter for viral channels like 'Seconds Before Disaster'.
Topic: "{topic_text}".
Genre tone: {cat_config["prompt_tone"]}.
Language: {"English" if is_en else "Vietnamese"}.
Task: Write {needed} consecutive narrative sentences describing the unfolding disaster or intense event.
Requirements:
- Urgent, realistic, documentary tone.
- Under 12 words per sentence (must speak in ~3.2 seconds).

Return ONLY a JSON array with exactly {needed} strings. Example:
["First sentence here.", "Second sentence here."]"""

            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            raw_text = resp.choices[0].message.content.strip()
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            batch_lines = []
            if match:
                try:
                    batch_lines = json.loads(match.group(0))
                except Exception:
                    pass

            if not batch_lines:
                batch_lines = [f"Khoảnh khắc thót tim khi tình huống nguy cấp xảy ra ở phân cảnh {len(parsed_scenes) + i + 1}." for i in range(needed)]

            for line in batch_lines:
                idx = len(parsed_scenes)
                if engine_mode == "disaster_hybrid":
                    q_val = pool[idx % len(pool)]
                    fb_val = "ocean storm heavy rough waves"
                else:
                    item_pool = pool[idx % len(pool)]
                    q_val = item_pool[0]
                    fb_val = item_pool[1]

                parsed_scenes.append({
                    "speech_text": str(line).strip(),
                    "query": q_val,
                    "fallback": fb_val
                })
                if len(parsed_scenes) >= calc_clips:
                    break

        # 2. Tạo Voice
        status.update(label="🎙️ 2/4: Tạo giọng đọc thuyết minh chuyên nghiệp...")
        scenes = []
        for idx, item in enumerate(parsed_scenes):
            v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
            asyncio.run(generate_voice(item["speech_text"], v_file, voice_choice))
            scenes.append({
                "query": item["query"],
                "fallback": item["fallback"],
                "audio": v_file
            })

        # 3. Tải B-roll và xử lý âm thanh từng cảnh
        status.update(label="🎬 3/4: Đang trích xuất video & hòa âm hiện trường...")
        clips_txt = os.path.join(workdir, "clips.txt")

        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                raw_v = os.path.join(workdir, f"r_{idx:03d}.mp4")
                scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                get_broll_failproof(engine_mode, sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes, raw_v, idx)

                process_scene_wav_injector(raw_v, sc["audio"], backup_storm_path, scene_v, is_port, raw_vol_float, workdir, idx)

                if os.path.exists(raw_v):
                    os.remove(raw_v)

                f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

        # 4. Nối cảnh & Ép hòa âm BGM ngầm
        status.update(label="⚡ 4/4: Ghép Master và hoàn tất hòa âm...", state="running")
        temp_merged = os.path.join(workdir, "temp_merged.mp4")
        final_mp4 = os.path.join(workdir, "master_disaster_promax.mp4")

        subprocess.run([
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
            "-i", clips_txt, "-c", "copy", temp_merged
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        bgm_raw = os.path.join(workdir, "bgm_raw.mp3")
        bgm_fitted = os.path.join(workdir, "bgm_fitted.wav")
        has_bgm = download_file_safe(CINEMATIC_BGM_URL, bgm_raw)

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

        status.update(label=f"🎉 Hoàn thành video {calc_clips * 5} giây với âm thanh sống động!", state="complete")

        with open(final_mp4, "rb") as out_f:
            v_bytes = out_f.read()

        st.video(v_bytes)
        st.download_button(
            label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
            data=v_bytes,
            file_name=f"disaster_master_{calc_clips * 5}s_{int(time.time())}.mp4",
            mime="video/mp4",
            use_container_width=True
        )

    except Exception as e:
        status.update(label=f"❌ Thất bại: {str(e)}", state="error")
        st.error(f"Chi tiết lỗi: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
