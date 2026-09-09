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
CLIP_DURATION = 5.0  # Chuẩn xác 5.0s mỗi phân cảnh
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets.get("PEXELS_API_KEY", "")
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình API Key trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Pro Max")
st.caption("Cắt ghép chuẩn ≤ 5s • Tai nạn & Thảm họa cào YouTube thực tế • Động vật/Xe dùng Pexels/Pixabay")

CATEGORY_SETTINGS = {
    "💥 Tổng hợp tai nạn, thảm họa, khoảnh khắc hiểm nghèo thực tế": {
        "engine": "youtube_only",
        "search_pool": [
            "moments filmed seconds before disaster real footage",
            "ship disaster rough sea huge wave caught on camera",
            "airplane emergency landing incident real footage",
            "extreme maritime storm boat caught on camera",
            "shocking bridge collapse accident caught on camera",
            "helicopter rescue extreme weather incident"
        ],
        "default_voice_en": "Tiếng Anh: Guy (Nam thời sự / Thảm họa Seconds Before Disaster)",
        "default_voice_vi": "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
        "prompt_tone": "Khẩn cấp, nghẹt thở, ngắn gọn, phong cách phóng sự Seconds Before Disaster"
    },
    "🐾 Thế giới Động vật / Thú cưng dễ thương": {
        "engine": "pexels_pixabay_yt",
        "search_pool": [
            ("cute golden retriever puppy playing", "puppy dog"),
            ("baby panda climbing bamboo", "baby panda"),
            ("little kitten playing ball", "kitten cat"),
            ("fluffy bunny rabbit eating carrot", "cute bunny"),
            ("playful sea otter floating water", "sea otter"),
            ("cute duckling swimming pond", "duckling")
        ],
        "default_voice_en": "Tiếng Anh: Ana (Giọng hoạt hình / Vui tươi)",
        "default_voice_vi": "Tiếng Việt: Hoài My (Nữ truyền cảm / Nhẹ nhàng)",
        "prompt_tone": "Ngộ nghĩnh, tươi vui, mang lại cảm giác ấm áp và kỳ thú"
    },
    "🏎️ Siêu xe / Tốc độ / Đua đêm Tokyo": {
        "engine": "pexels_pixabay_yt",
        "search_pool": [
            ("supercar drifting night city street", "drift car"),
            ("sports car speeding highway exhaust sound", "sports car"),
            ("neon cyberpunk race car launch control", "supercar night"),
            ("supercar engine revving flame", "car exhaust")
        ],
        "default_voice_en": "Tiếng Anh: Christopher (Trầm khàn / Cuốn hút)",
        "default_voice_vi": "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
        "prompt_tone": "Đậm chất adrenaline, uy lực động cơ và ánh đèn thành phố"
    },
    "🌌 Khám phá / Khoa học viễn tưởng / Lịch sử": {
        "engine": "pexels_pixabay_yt",
        "search_pool": [
            ("deep space nebula stars flying", "space universe"),
            ("ancient ruins temple drone shot", "ancient ruins"),
            ("futuristic cyber city holographic", "sci fi city"),
            ("astronaut walking on mars", "astronaut space")
        ],
        "default_voice_en": "Tiếng Anh: Christopher (Trầm khàn / Cuốn hút)",
        "default_voice_vi": "Tiếng Việt: Nam Minh (Nam thời sự / Bản tin tài liệu)",
        "prompt_tone": "Bí ẩn, hùng vĩ, mang tầm vóc khám phá vũ trụ và lịch sử"
    }
}

selected_cat_name = st.selectbox("Chọn thể loại video chính:", list(CATEGORY_SETTINGS.keys()))
cat_config = CATEGORY_SETTINGS[selected_cat_name]

topic_text = st.text_area(
    "Mô tả chi tiết kịch bản / Tình huống:",
    value="Những khoảnh khắc thót tim khi máy bay hạ cánh khẩn cấp, tàu thuyền chao đảo giữa sóng thần và tai nạn bất ngờ xảy ra trong gang tấc",
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
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=300, value=20, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ cắt ghép **{calc_clips} phân cảnh thực tế (mỗi cảnh đúng 5.0 giây)**.")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])
with col_opt2:
    raw_vol = st.slider("Âm lượng tiếng gốc hiện trường (Gió/Sóng/Còi/Va chạm) (%):", min_value=20, max_value=100, value=65, step=5)

bgm_volume = st.slider("Âm lượng nhạc nền ngầm BGM (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ AN TOÀN
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0"}
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

def check_video_has_audio(file_path: str) -> bool:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return "audio" in res.stdout.strip()
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

def fetch_from_youtube_fast(query: str, used_hashes: set, dest_path: str) -> bool:
    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
        'default_search': 'ytsearch10',
        'max_downloads': 1,
        'outtmpl': dest_path,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 15,
        'download_ranges': lambda info_dict, ydl: [{'start_time': 10, 'end_time': 45}]
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_res = ydl.extract_info(f"ytsearch10:{query}", download=False)
            if search_res and 'entries' in search_res:
                for entry in search_res['entries']:
                    if not entry:
                        continue
                    v_id = f"yt_{entry.get('id')}"
                    dur = entry.get('duration', 0)
                    if v_id not in used_hashes and 10 <= dur <= 1200:
                        ydl.download([entry['webpage_url']])
                        if os.path.exists(dest_path):
                            used_hashes.add(v_id)
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

def get_hybrid_broll(cat_mode: str, query: str, fallback_q: str, p_key: str, pb_key: str, used_hashes: set, raw_dest: str) -> bool:
    if cat_mode == "youtube_only":
        ok = fetch_from_youtube_fast(query, used_hashes, raw_dest)
        if not ok:
            ok = fetch_from_youtube_fast("moments filmed seconds before disaster", used_hashes, raw_dest)
        return ok

    url = fetch_from_pexels(query, p_key, used_hashes)
    if not url and pb_key:
        url = fetch_from_pixabay(query, pb_key, used_hashes)
    if url:
        return download_file_safe(url, raw_dest)

    url = fetch_from_pexels(fallback_q, p_key, used_hashes)
    if not url and pb_key:
        url = fetch_from_pixabay(fallback_q, pb_key, used_hashes)
    if url:
        return download_file_safe(url, raw_dest)

    return fetch_from_youtube_fast(query, used_hashes, raw_dest)

def process_scene_wav_pipeline(raw_v: str, voice_mp3: str, out_p: str, is_port: bool, raw_vol_float: float, workdir: str, idx: int):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"

    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_v]
    try:
        raw_dur = float(subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip() or 10.0)
    except Exception:
        raw_dur = 10.0

    # Lấy điểm cắt ngẫu nhiên trong khoảng cao trào
    start_sec = 0.5
    if raw_dur > (CLIP_DURATION + 2.0):
        start_sec = random.uniform(1.0, min(5.0, raw_dur - CLIP_DURATION - 0.5))

    temp_v = os.path.join(workdir, f"tmp_v_{idx:03d}.mp4")
    norm_raw_wav = os.path.join(workdir, f"tmp_raw_{idx:03d}.wav")
    norm_voice_wav = os.path.join(workdir, f"tmp_voice_{idx:03d}.wav")

    # 1. Cắt hình ảnh đúng 5.0 giây
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", raw_v,
        "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f,
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        temp_v
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. Cắt và chuẩn hóa âm thanh gốc hiện trường đúng 5.0 giây (WAV 44.1kHz Stereo)
    has_audio = check_video_has_audio(raw_v)
    if has_audio:
        subprocess.run([
            FFMPEG_EXE, "-y",
            "-ss", f"{start_sec:.2f}",
            "-i", raw_v,
            "-t", f"{CLIP_DURATION:.3f}",
            "-ar", "44100", "-ac", "2",
            norm_raw_wav
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        subprocess.run([
            FFMPEG_EXE, "-y",
            "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:r=44100:a=0.1",
            "-af", "lowpass=f=1200",
            "-t", f"{CLIP_DURATION:.3f}",
            "-ar", "44100", "-ac", "2",
            norm_raw_wav
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Chuẩn hóa giọng đọc sang WAV 44.1kHz Stereo
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", voice_mp3,
        "-t", f"{CLIP_DURATION:.3f}",
        "-ar", "44100", "-ac", "2",
        norm_voice_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. Hòa âm tiếng hiện trường + giọng đọc
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", temp_v,
        "-i", norm_raw_wav,
        "-i", norm_voice_wav,
        "-filter_complex",
        f"[1:a]volume={raw_vol_float:.2f},afade=t=in:ss=0:d=0.2,afade=t=out:st=4.8:d=0.2[a0];[2:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{CLIP_DURATION:.3f}",
        out_p
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    for p in [temp_v, norm_raw_wav, norm_voice_wav]:
        if os.path.exists(p):
            os.remove(p)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Sản Xuất Master Pro Max", use_container_width=True, type="primary"):
    status = st.status(f"Hệ thống đang chuẩn bị sản xuất {calc_clips} phân cảnh...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_promax_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in voice_choice
    raw_vol_float = raw_vol / 100.0
    total_video_time = calc_clips * CLIP_DURATION

    try:
        client = Groq(api_key=groq_key.strip())

        # 1. AI biên soạn câu chuyện
        status.update(label=f"🧠 1/4: {LLM_MODEL} đang sinh kịch bản câu chuyện...")
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
                if engine_mode == "youtube_only":
                    q_val = pool[idx % len(pool)]
                    fb_val = q_val
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

        # 3. Tải B-roll và xử lý phân cảnh đúng ≤ 5s
        status.update(label=f"🎬 3/4: Đang trích xuất video thực tế ({engine_mode})...")
        clips_txt = os.path.join(workdir, "clips.txt")

        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                raw_v = os.path.join(workdir, f"r_{idx:03d}.mp4")
                scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                ok = get_hybrid_broll(engine_mode, sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes, raw_v)
                if not ok:
                    fallback_base = pool[0] if engine_mode == "youtube_only" else pool[0][0]
                    get_hybrid_broll(engine_mode, fallback_base, fallback_base, pexels_key, pixabay_key, used_hashes, raw_v)

                process_scene_wav_pipeline(raw_v, sc["audio"], scene_v, is_port, raw_vol_float, workdir, idx)

                if os.path.exists(raw_v):
                    os.remove(raw_v)

                f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

        # 4. Nối cảnh & Ép hòa âm BGM
        status.update(label="⚡ 4/4: Ghép Master và hoàn tất hòa âm BGM...", state="running")
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

        status.update(label=f"🎉 Hoàn thành video {calc_clips * 5} giây hoàn hảo!", state="complete")

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
