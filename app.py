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

# Nhạc nền BGM chuẩn MP3
CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

# Thư viện âm thanh xung lực MP3 chuẩn (Tuyệt đối không dùng OGG để chống lỗi 254)
SFX_ASSETS = {
    "airplane": "https://upload.wikimedia.org/wikipedia/commons/transcoded/5/5a/Jet_flyby.ogg/Jet_flyby.ogg.mp3",
    "ship": "https://upload.wikimedia.org/wikipedia/commons/transcoded/2/27/Thunderstorm_sound.ogg/Thunderstorm_sound.ogg.mp3",
    "disaster": "https://upload.wikimedia.org/wikipedia/commons/transcoded/2/27/Thunderstorm_sound.ogg/Thunderstorm_sound.ogg.mp3"
}

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets.get("PEXELS_API_KEY", "")
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình API Key trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Pro Max (Full Sound FX)")
st.caption("Khớp chủ thể linh hoạt • Âm thanh xung lực chân thực • Cắt ghép chuẩn xác ≤ 5.0s")

topic_text = st.text_area(
    "Mô tả chi tiết kịch bản / Tình huống:",
    value="Các vụ tai nạn máy bay hạ cánh khẩn cấp trong bão, tàu lớn chao đảo giữa sóng thần",
    height=80
)

col1, col2 = st.columns(2)
with col1:
    voice_choice = st.selectbox(
        "Giọng đọc thuyết minh:",
        [
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
st.info(f"💡 Hệ thống sẽ chia kịch bản thành **{calc_clips} phân cảnh khác nhau** (mỗi cảnh đúng 5.0 giây).")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])
with col_opt2:
    raw_vol = st.slider("Âm lượng tiếng hiện trường (Gió/Động cơ/Sóng) (%):", min_value=40, max_value=180, value=110, step=10)

bgm_volume = st.slider("Âm lượng nhạc nền ngầm BGM (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ KỸ THUẬT AN TOÀN
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=25) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=32768):
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

def fetch_dynamic_pexels_clip(query: str, p_key: str, used_hashes: set) -> str:
    if not p_key:
        return None
    headers = {"Authorization": p_key.strip()}
    queries_to_try = [query, f"{query} action", f"{query} storm"]
    for q in queries_to_try:
        for page in [1, 2, 3]:
            try:
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

def fetch_dynamic_pixabay_clip(query: str, pb_key: str, used_hashes: set) -> str:
    if not pb_key:
        return None
    for page in [1, 2]:
        try:
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

def get_dynamic_clip(query: str, fallback_q: str, p_key: str, pb_key: str, used_hashes: set, dest_path: str) -> bool:
    url = fetch_dynamic_pexels_clip(query, p_key, used_hashes)
    if not url and pb_key:
        url = fetch_dynamic_pixabay_clip(query, pb_key, used_hashes)
    if url and download_file_safe(url, dest_path):
        return True

    url = fetch_dynamic_pexels_clip(fallback_q, p_key, used_hashes)
    if not url and pb_key:
        url = fetch_dynamic_pixabay_clip(fallback_q, pb_key, used_hashes)
    if url and download_file_safe(url, dest_path):
        return True

    generic_url = fetch_dynamic_pexels_clip("storm waves rough sea", p_key, used_hashes)
    if generic_url:
        return download_file_safe(generic_url, dest_path)
    return False

def render_scene_dynamic_sfx(raw_v: str, voice_mp3: str, subject_tag: str, out_p: str, is_port: bool, raw_vol_float: float, workdir: str, idx: int):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"

    cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_v]
    try:
        raw_dur = float(subprocess.run(cmd_dur, capture_output=True, text=True).stdout.strip() or 10.0)
    except Exception:
        raw_dur = 10.0

    start_sec = 0.5
    if raw_dur > (CLIP_DURATION + 2.0):
        start_sec = random.uniform(0.5, min(5.0, raw_dur - CLIP_DURATION - 0.5))

    temp_v = os.path.join(workdir, f"tmp_v_{idx:03d}.mp4")
    norm_env_wav = os.path.join(workdir, f"tmp_env_{idx:03d}.wav")
    norm_voice_wav = os.path.join(workdir, f"tmp_voice_{idx:03d}.wav")

    # 1. Cắt hình ảnh sạch sẽ (tách hoàn toàn audio)
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

    # 2. Xử lý âm thanh hiện trường có xung lực
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
        # Tải asset âm thanh MP3 tương ứng với thể loại cảnh
        sfx_type = "airplane" if any(w in subject_tag.lower() for w in ["plane", "jet", "flight", "air"]) else "ship"
        sfx_url = SFX_ASSETS.get(sfx_type, SFX_ASSETS["disaster"])
        sfx_file = os.path.join(workdir, f"sfx_cache_{sfx_type}.mp3")

        if not os.path.exists(sfx_file):
            download_file_safe(sfx_url, sfx_file)

        if os.path.exists(sfx_file) and os.path.getsize(sfx_file) > 10000:
            subprocess.run([
                FFMPEG_EXE, "-y",
                "-i", sfx_file,
                "-ss", f"{(idx * 3) % 15}",
                "-t", f"{CLIP_DURATION:.3f}",
                "-af", "bass=g=5:f=110,volume=1.2",
                "-ar", "44100", "-ac", "2",
                norm_env_wav
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            # Fallback nếu mạng tải file lỗi
            subprocess.run([
                FFMPEG_EXE, "-y",
                "-f", "lavfi", "-i", "anoisesrc=d=5:c=brown:r=44100:a=0.35",
                "-af", "lowpass=f=1100,bass=g=7:f=100,tremolo=f=1.0:d=0.7",
                "-t", f"{CLIP_DURATION:.3f}",
                "-ar", "44100", "-ac", "2",
                norm_env_wav
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Chuẩn hóa voice đọc sang WAV 44.1kHz stereo
    subprocess.run([
        FFMPEG_EXE, "-y",
        "-i", voice_mp3,
        "-t", f"{CLIP_DURATION:.3f}",
        "-ar", "44100", "-ac", "2",
        norm_voice_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. Hòa âm: Đẩy tiếng hiện trường rõ ràng + voice đọc
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
if st.button("🚀 Bắt Đầu Tạo Video Khớp Từ Khóa 100%", use_container_width=True, type="primary"):
    status = st.status(f"Đang phân tích kịch bản và phân rã các đối tượng thị giác...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_dynamic_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in voice_choice
    raw_vol_float = raw_vol / 100.0
    total_video_time = calc_clips * CLIP_DURATION

    try:
        client = Groq(api_key=groq_key.strip())

        # 1. AI phân rã từ khóa độc lập cho TỪNG CẢNH
        status.update(label=f"🧠 1/4: {LLM_MODEL} đang phân bổ đa dạng các đối tượng...")
        prompt = f"""You are a professional documentary video director for viral channels like 'Seconds Before Disaster'.
User topic: "{topic_text}".
Total scenes needed: Exactly {calc_clips} scenes (each scene is 5.0 seconds).
Language: {"English" if is_en else "Vietnamese"}.

STRICT VISUAL VARIETY RULES:
- If the topic mentions multiple subjects (e.g., airplanes and ships), ALTERNATE between them!
- Scene 1: An airplane in emergency / rough landing / turbulence.
- Scene 2: A large ship or fishing boat battling huge ocean storm waves.
- Scene 3: Cockpit or ship deck tension.
- Do NOT repeat the same visual query for all scenes!
- `query_en`: 2-3 specific English words (e.g., 'airplane rough landing', 'cargo ship storm waves', 'jet cockpit turbulence').
- `fallback_en`: 2 backup words (e.g., 'airplane storm', 'ship waves').
- `subject_type`: Either 'airplane' or 'ship' or 'disaster'.
- `speech_text`: One dramatic narrative sentence under 12 words (~3.2 seconds).

Return ONLY a valid JSON list of {calc_clips} objects:
[
  {{
    "scene": 1,
    "speech_text": "...",
    "query_en": "airplane storm landing",
    "fallback_en": "airplane emergency",
    "subject_type": "airplane"
  }},
  {{
    "scene": 2,
    "speech_text": "...",
    "query_en": "cargo ship heavy storm waves",
    "fallback_en": "ship rough sea",
    "subject_type": "ship"
  }}
]"""

        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        raw_text = resp.choices[0].message.content.strip()
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        parsed_scenes = json.loads(match.group(0)) if match else []

        # Dự phòng tự động nếu AI trả thiếu cảnh
        default_alternatives = [
            ("airplane rough landing crosswind", "airplane storm", "airplane", "A passenger jet battles dangerous crosswinds during emergency touchdown."),
            ("cargo ship huge storm waves crash", "ship rough sea", "ship", "Massive forty-foot waves slam into the hull of a struggling freighter."),
            ("cockpit pilots flight turbulence", "airplane cockpit", "airplane", "Inside the cockpit, pilots fight to regain altitude and control."),
            ("fishing boat extreme rough sea", "boat ocean waves", "ship", "Freezing arctic water floods the deck of an isolated fishing vessel.")
        ]
        while len(parsed_scenes) < calc_clips:
            idx = len(parsed_scenes)
            pick = default_alternatives[idx % len(default_alternatives)]
            parsed_scenes.append({
                "scene": idx + 1,
                "speech_text": pick[3] if is_en else f"Tình huống hiểm nguy khẩn cấp tiếp diễn ở phân cảnh thứ {idx + 1}.",
                "query_en": pick[0],
                "fallback_en": pick[1],
                "subject_type": pick[2]
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
                "fallback": item["fallback_en"],
                "subject_type": item.get("subject_type", "disaster"),
                "audio": v_file
            })

        # 3. Tải B-roll linh hoạt theo từng cảnh
        status.update(label="🎬 3/4: Đang cào video đa dạng (máy bay, tàu lớn, buồng lái)...")
        clips_txt = os.path.join(workdir, "clips.txt")

        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                raw_v = os.path.join(workdir, f"r_{idx:03d}.mp4")
                scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                ok = get_dynamic_clip(sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes, raw_v)
                if not ok:
                    get_dynamic_clip("storm waves rough ocean", "storm ocean", pexels_key, pixabay_key, used_hashes, raw_v)

                render_scene_dynamic_sfx(raw_v, sc["audio"], sc["subject_type"], scene_v, is_port, raw_vol_float, workdir, idx)

                if os.path.exists(raw_v):
                    os.remove(raw_v)

                f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

        # 4. Nối cảnh & Hòa âm BGM
        status.update(label="⚡ 4/4: Ghép nối Master thành phẩm...", state="running")
        temp_merged = os.path.join(workdir, "temp_merged.mp4")
        final_mp4 = os.path.join(workdir, "master_disaster_dynamic.mp4")

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
            file_name=f"disaster_dynamic_{calc_clips * 5}s_{int(time.time())}.mp4",
            mime="video/mp4",
            use_container_width=True
        )

    except Exception as e:
        status.update(label=f"❌ Thất bại: {str(e)}", state="error")
        st.error(f"Chi tiết lỗi: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
