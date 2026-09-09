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

st.set_page_config(page_title="Studio POV Master Pro Max", page_icon="🎬", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

# Nhạc nền BGM MP3 chuẩn (Không dùng OGG để tránh lỗi 254)
CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"
# Âm thanh bão biển gầm rú MP3 chuẩn
REAL_STORM_SFX_MP3 = "https://cdn.freesound.org/previews/512/512130_6142149-lq.mp3"

# KHO VIDEO THẢM HỌA THỰC TẾ TRỰC TIẾP (Tải trực tiếp MP4 có sẵn âm thanh hiện trường, không bị Bot Check)
DISASTER_REAL_VIDEOS = [
    # Cảnh sóng biển Bắc Hải đập mạn tàu (Có tiếng sóng gió thật)
    "https://ia600708.us.archive.org/28/items/NorthSeaStormFootage/NorthSeaStorm.mp4",
    # Tàu vượt sóng lớn đại dương quay từ buồng lái
    "https://upload.wikimedia.org/wikipedia/commons/transcoded/8/87/Rough_seas_aboard_the_RRS_James_Clark_Ross.webm/Rough_seas_aboard_the_RRS_James_Clark_Ross.webm.720p.vp9.webm",
    # Bão biển dữ dội đánh dạt mạn thuyền
    "https://upload.wikimedia.org/wikipedia/commons/transcoded/a/a2/Wave_crashing_over_the_bow_of_a_ship.ogv/Wave_crashing_over_the_bow_of_a_ship.ogv.720p.webm",
    # Sóng thần và gió giật biển khơi
    "https://ia800201.us.archive.org/12/items/BigWavesHittingBoat/BigWaves.mp4"
]

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets.get("PEXELS_API_KEY", "")
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình API Key trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Pro Max")
st.caption("Kho Video Thực Tế Mở • 100% Âm Thanh Hiện Trường Thật • Loại bỏ hoàn toàn lỗi 254")

CATEGORY_SETTINGS = {
    "💥 Tổng hợp tai nạn, thảm họa, khoảnh khắc hiểm nghèo thực tế": {
        "engine": "archive_real_disaster",
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
        "engine": "stock_mode",
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
        "engine": "stock_mode",
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
st.info(f"💡 Hệ thống sẽ cắt ghép **{calc_clips} phân cảnh thực tế (mỗi cảnh đúng 5.0 giây)**.")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])
with col_opt2:
    raw_vol = st.slider("Âm lượng tiếng gốc hiện trường (Sóng/Gió/Động cơ) (%):", min_value=40, max_value=180, value=110, step=10)

bgm_volume = st.slider("Âm lượng nhạc nền ngầm BGM (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ AN TOÀN
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=25) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=32768):
                        f.write(chunk)
                return os.path.exists(dest) and os.path.getsize(dest) > 20000
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

def verify_valid_media(file_path: str) -> bool:
    if not file_path or not os.path.exists(file_path):
        return False
    if os.path.getsize(file_path) < 50000:
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

def get_broll_reliable(cat_mode: str, query: str, fallback_q: str, p_key: str, pb_key: str, used_hashes: set, raw_dest: str, clip_idx: int) -> bool:
    """Tải B-roll trực tiếp tốc độ cao không bị phụ thuộc vào YouTube Bot Check"""
    if cat_mode == "archive_real_disaster":
        # 1. Tải video bão biển thật từ kho tư liệu mở
        direct_url = DISASTER_REAL_VIDEOS[clip_idx % len(DISASTER_REAL_VIDEOS)]
        ok = download_file_safe(direct_url, raw_dest)
        if ok and verify_valid_media(raw_dest):
            return True

        # 2. Dự phòng: Tải video sóng thần bão biển nét từ Pexels
        p_url = fetch_from_pexels(query, p_key, used_hashes) or fetch_from_pexels("storm waves ocean heavy", p_key, used_hashes)
        if p_url and download_file_safe(p_url, raw_dest):
            return True

    # Thể loại Động vật / Xe: Dùng Pexels -> Pixabay
    url = fetch_from_pexels(query, p_key, used_hashes)
    if not url and pb_key:
        url = fetch_from_pixabay(query, pb_key, used_hashes)
    if url and download_file_safe(url, raw_dest):
        return True

    url = fetch_from_pexels(fallback_q, p_key, used_hashes)
    if url and download_file_safe(url, raw_dest):
        return True

    return download_file_safe(DISASTER_REAL_VIDEOS[0], raw_dest)

def cut_and_mix_5s_bulletproof(raw_v: str, voice_mp3: str, backup_storm_mp3: str, out_p: str, is_port: bool, raw_vol_float: float, workdir: str, idx: int):
    """
    Quy trình cắt ghép chống crash FFmpeg 254:
    - Tuyệt đối không đọc file .ogg.
    - Chuẩn hóa âm thanh qua MP3/WAV 44.1kHz Stereo.
    - Cắt đúng 5.0 giây, khuếch đại âm thanh hiện trường sống động.
    """
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"

    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_v]
    try:
        raw_dur = float(subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip() or 10.0)
    except Exception:
        raw_dur = 10.0

    start_sec = 0.5
    if raw_dur > (CLIP_DURATION + 2.0):
        start_sec = random.uniform(0.5, min(6.0, raw_dur - CLIP_DURATION - 0.5))

    temp_v = os.path.join(workdir, f"tmp_v_{idx:03d}.mp4")
    norm_env_wav = os.path.join(workdir, f"tmp_env_{idx:03d}.wav")
    norm_voice_wav = os.path.join(workdir, f"tmp_voice_{idx:03d}.wav")

    # 1. Cắt video hình ảnh (không kèm âm thanh)
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

    # 2. Xử lý âm thanh hiện trường (nếu video có tiếng thì dùng tiếng gốc, nếu câm thì inject tiếng bão MP3)
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
        subprocess.run([
            FFMPEG_EXE, "-y",
            "-i", backup_storm_mp3,
            "-ss", f"{(idx * 5) % 20}",
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
if st.button("🚀 Bắt Đầu Dựng Video Thực Tế (Fixed 254 & YouTube)", use_container_width=True, type="primary"):
    status = st.status(f"Hệ thống đang chuẩn bị sản xuất {calc_clips} phân cảnh...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_robust_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in voice_choice
    raw_vol_float = raw_vol / 100.0
    total_video_time = calc_clips * CLIP_DURATION

    try:
        client = Groq(api_key=groq_key.strip())

        # Tải sẵn file âm thanh bão biển MP3 chuẩn (Bỏ hoàn toàn file OGG)
        status.update(label="🌊 Đang thiết lập kênh âm thanh hiện trường MP3 chuẩn...")
        backup_storm_path = os.path.join(workdir, "storm_real.mp3")
        download_file_safe(REAL_STORM_SFX_MP3, backup_storm_path)

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
                if engine_mode == "archive_real_disaster":
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
        status.update(label="🎬 3/4: Đang trích xuất video thực tế & hòa âm hiện trường...")
        clips_txt = os.path.join(workdir, "clips.txt")

        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                raw_v = os.path.join(workdir, f"r_{idx:03d}.mp4")
                scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                get_broll_reliable(engine_mode, sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes, raw_v, idx)

                cut_and_mix_5s_bulletproof(raw_v, sc["audio"], backup_storm_path, scene_v, is_port, raw_vol_float, workdir, idx)

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
