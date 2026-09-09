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

st.set_page_config(page_title="POV Disaster & Crash Engine v2", page_icon="💥", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
DRAMA_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

try:
    groq_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY trong Secrets của Streamlit Cloud!")
    st.stop()

st.title("💥 POV Compilation Engine v2: Action & Disaster")
st.caption("AI phân tích cú va chạm • Dò tìm Timestamp kịch tính trên YouTube • Cắt chuẩn 5s • Chống trùng sâu")

# ==============================================================================
# GIAO DIỆN CẤU HÌNH
# ==============================================================================
topic_genre = st.text_area(
    "Nhập chuỗi sự kiện / Tai nạn cần dựng (Compilation Story):",
    value="Tổng hợp các khoảnh khắc máy bay gặp sự cố hạ cánh khẩn cấp, gió tạt trượt khỏi đường băng và cú thoát hiểm trong gang tấc",
    height=80
)

col_t1, col_t2 = st.columns(2)
with col_t1:
    genre_mode = st.selectbox(
        "Chủ đề Compilation:",
        [
            "Tai nạn Hàng không (Airplane Crosswind / Emergency Landing / Crashes)",
            "Thảm họa Tàu biển (Ship Sinking / Rogue Wave / Storm Disaster)",
            "Động vật / Thú cưng ngộ nghĩnh (Funny Animals Caught on Camera)",
            "Siêu xe / Tai nạn đua xe (Race Car Drift & Crashes)"
        ]
    )
with col_t2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=300, value=25, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ săn tìm **{calc_clips} cú hích hành động 5s riêng biệt** (tổng thời lượng: {calc_clips * CLIP_DURATION:.0f} giây).")

col_v1, col_v2 = st.columns(2)
with col_v1:
    voice_choice = st.selectbox(
        "Giọng dẫn chuyện (Narrator):",
        [
            "Tiếng Anh: Christopher (Giọng tài liệu trầm khàn chuẩn Discovery)",
            "Tiếng Anh: Guy (Nam kịch tính, nhịp nhanh)",
            "Tiếng Việt: Nam Minh (Nam thời sự tài liệu)",
            "Tiếng Việt: Hoài My (Nữ truyền cảm)"
        ]
    )
with col_v2:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])

col_s1, col_s2 = st.columns(2)
with col_s1:
    ambient_volume = st.slider("Âm thanh thực tế hiện trường / Tiếng gầm rú (%):", min_value=10, max_value=80, value=50, step=5)
with col_s2:
    bgm_volume = st.slider("Âm lượng nhạc nền kịch tính BGM (%):", min_value=0, max_value=50, value=20, step=5)

# ==============================================================================
# HÀM XỬ LÝ KỸ THUẬT & DÒ TÌM TIMESTAMP THỰC TẾ
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=25) as r:
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
    elif "Nam Minh" in voice_option:
        v_code = "vi-VN-NamMinhNeural"
    else:
        v_code = "vi-VN-HoaiMyNeural"

    comm = edge_tts.Communicate(text, voice=v_code, rate="+4%")
    await comm.save(out_audio)

def detect_action_timestamps(video_path: str) -> float:
    """
    Sử dụng FFmpeg Scene Change Detection để tìm mốc thời gian có cú giật hình ảnh mạnh nhất
    (chuyển cảnh va chạm, góc quay máy bay rung lắc, sóng đập).
    """
    cmd = [
        FFMPEG_EXE, "-i", video_path,
        "-vf", "select='gt(scene,0.35)',metadata=print:file=-",
        "-f", "null", "-"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        # Bóc tách các mốc pts_time từ log
        matches = re.findall(r'pts_time:([0-9\.]+)', res.stderr)
        valid_points = [float(m) for m in matches if float(m) > 1.0]
        if valid_points:
            # Chọn mốc chuyển cảnh có chuyển động đầu tiên sau 2 giây intro
            return valid_points[0]
    except Exception:
        pass
    return 3.0

def fetch_and_extract_youtube_scene(keywords: list, avoid_words: list, used_segments: set, dest_path: str) -> bool:
    """
    1. Tìm video trên YouTube theo query sát nghĩa.
    2. Loại bỏ video chứa từ khóa negative (animation, simulator, etc).
    3. Tải đoạn demo 30s giữa video.
    4. Dò tìm điểm va chạm (Action Timestamp) và cắt lấy đúng 5.0 giây.
    """
    query_str = " ".join(keywords[:3])
    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best',
        'default_search': 'ytsearch15',
        'max_downloads': 1,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 15,
        # Chỉ tải đoạn từ giây 20 đến giây 50 để tránh intro/outro và giảm tối đa băng thông
        'download_ranges': yt_dlp.utils.download_range_func(None, [(20, 50)]),
        'force_keyframes_at_cuts': True,
        'outtmpl': dest_path
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_info = ydl.extract_info(f"ytsearch15:{query_str} caught on camera", download=False)
            if search_info and 'entries' in search_info:
                for entry in search_info['entries']:
                    if not entry:
                        continue
                    
                    title = entry.get('title', '').lower()
                    v_id = entry.get('id', '')
                    
                    # Bộ lọc loại bỏ video mô phỏng / hoạt hình
                    if any(aw.lower() in title for aw in avoid_words):
                        continue
                    
                    # Kiểm tra dấu vân tay ID chống trùng
                    if v_id in used_segments:
                        continue

                    dur = entry.get('duration', 0)
                    if 20 <= dur <= 1200:
                        ydl.download([entry['webpage_url']])
                        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 150000:
                            used_segments.add(v_id)
                            return True
    except Exception:
        pass
    return False

def process_single_scene_bulletproof(raw_v: str, voice_mp3: str, out_p: str, is_port: bool, amb_vol: float, workdir: str, idx: int):
    """
    Cắt chuẩn xác 5.0s tại mốc hành động kịch tính và đồng bộ Audio WAV PCM 44.1kHz (Khắc phục lỗi 254).
    """
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"
    
    # 1. Dò tìm mốc bắt đầu có chuyển động mạnh
    start_sec = detect_action_timestamps(raw_v)

    # 2. Cắt video thuần túy
    temp_v = os.path.join(workdir, f"tmp_v_{idx:03d}.mp4")
    cmd_v = [
        FFMPEG_EXE, "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", raw_v,
        "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f,
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        temp_v
    ]
    subprocess.run(cmd_v, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Chuẩn hóa Voice
    norm_voice_wav = os.path.join(workdir, f"norm_voice_{idx:03d}.wav")
    cmd_voice = [
        FFMPEG_EXE, "-y",
        "-i", voice_mp3,
        "-t", f"{CLIP_DURATION:.3f}",
        "-ar", "44100", "-ac", "2",
        norm_voice_wav
    ]
    subprocess.run(cmd_voice, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. Chuẩn hóa Ambient / Tiếng thực tế
    norm_amb_wav = os.path.join(workdir, f"norm_amb_{idx:03d}.wav")
    has_audio = check_video_has_audio(raw_v)

    if has_audio:
        cmd_amb = [
            FFMPEG_EXE, "-y",
            "-ss", f"{start_sec:.2f}",
            "-i", raw_v,
            "-t", f"{CLIP_DURATION:.3f}",
            "-ar", "44100", "-ac", "2",
            norm_amb_wav
        ]
    else:
        cmd_amb = [
            FFMPEG_EXE, "-y",
            "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:r=44100:a=0.15",
            "-af", "lowpass=f=1200",
            "-t", f"{CLIP_DURATION:.3f}",
            "-ar", "44100", "-ac", "2",
            norm_amb_wav
        ]
    subprocess.run(cmd_amb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 5. Mux phân cảnh
    cmd_mux = [
        FFMPEG_EXE, "-y",
        "-i", temp_v,
        "-i", norm_amb_wav,
        "-i", norm_voice_wav,
        "-filter_complex",
        f"[1:a]volume={amb_vol:.2f},afade=t=in:ss=0:d=0.2,afade=t=out:st=4.8:d=0.2[a0];[2:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{CLIP_DURATION:.3f}",
        out_p
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    for p in [temp_v, norm_voice_wav, norm_amb_wav]:
        if os.path.exists(p):
            os.remove(p)

# ==============================================================================
# PIPELINE SẢN XUẤT COMPILATION MASTER
# ==============================================================================
if st.button("🚀 Bắt Đầu Tạo Video Compilation Kịch Tính", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập bối cảnh kịch bản.")
    else:
        status = st.status(f"Đang bóc tách cú hích hành động cho {calc_clips} phân cảnh...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="compilation_run_")
        used_segments = set()
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in voice_choice
        total_duration_video = calc_clips * CLIP_DURATION

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. AI bóc tách Scene Semantics (Subject, Action, Event, Search Keywords, Avoid Words)
            status.update(label="🧠 1/4: AI phân tích sâu từng cảnh: Subject + Action + Event...")
            prompt = f"""You are an elite YouTube compilation producer like 'Seconds From Disaster' or 'Caught on Camera'.
Topic: "{topic_genre}".
Genre: "{genre_mode}".
Generate exactly {calc_clips} consecutive scenes.
Language: {"English" if is_en else "Vietnamese"}.

For EACH scene return:
- `speech_text`: Dramatic narration under 12 words (~3 seconds).
- `visual_keywords`: Array of 3-4 specific real-world search phrases targeting REAL caught-on-camera footage (e.g. ["airplane crosswind landing emergency", "plane slides off runway", "cockpit windstorm landing"]).
- `avoid_words`: Words to filter out fake/stock videos: ["simulator", "msfs", "animation", "game", "takeoff normal"].

Return ONLY a JSON object:
{{
  "scenes": [
    {{
      "speech_text": "The aircraft fights violent crosswinds as it touches down on the runway.",
      "visual_keywords": ["airplane crosswind landing extreme", "plane emergency landing storm"],
      "avoid_words": ["simulator", "game", "animation", "3d"]
    }}
  ]
}}"""

            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            raw_data = json.loads(resp.choices[0].message.content)
            parsed_scenes = raw_data.get("scenes", [])

            # Dự phòng đủ số lượng cảnh
            while len(parsed_scenes) < calc_clips:
                idx = len(parsed_scenes) + 1
                parsed_scenes.append({
                    "speech_text": f"Cú thoát hiểm thót tim và kịch tính ở phân cảnh {idx}.",
                    "visual_keywords": ["airplane crosswind landing emergency", "aircraft emergency landing storm"],
                    "avoid_words": ["simulator", "animation", "game"]
                })
            parsed_scenes = parsed_scenes[:calc_clips]

            # 2. Tạo Voice thuyết minh
            status.update(label="🎙️ 2/4: Tạo giọng đọc tài liệu sinh tồn...")
            scenes = []
            for idx, item in enumerate(parsed_scenes):
                v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
                asyncio.run(generate_voice(item["speech_text"], v_file, voice_choice))
                scenes.append({
                    "keywords": item.get("visual_keywords", ["aircraft emergency landing"]),
                    "avoid": item.get("avoid_words", ["simulator", "game"]),
                    "audio": v_file
                })

            # 3. Quét YouTube, dò Timestamp và cắt 5s
            status.update(label="🎬 3/4: Quét YouTube, dò mốc va chạm và cắt đúng 5s...")
            clips_txt = os.path.join(workdir, "clips.txt")
            amb_vol_float = ambient_volume / 100.0

            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    raw_v = os.path.join(workdir, f"raw_{idx:03d}.mp4")
                    scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                    got_clip = fetch_and_extract_youtube_scene(sc["keywords"], sc["avoid"], used_segments, raw_v)

                    # Dự phòng nếu YouTube từ khóa đó bị lọc hết
                    if not got_clip or not os.path.exists(raw_v):
                        fallback_kw = ["airplane emergency crosswind landing", "rough weather landing caught on camera"]
                        got_clip = fetch_and_extract_youtube_scene(fallback_kw, sc["avoid"], used_segments, raw_v)

                    # Nếu vẫn không có, sinh footage sóng biển / chấn động kỹ thuật số
                    if not got_clip or not os.path.exists(raw_v):
                        cmd_dummy = [
                            FFMPEG_EXE, "-y",
                            "-f", "lavfi", "-i", "color=c=0x0f172a:s=1280x720:d=5:r=30",
                            "-c:v", "libx264", raw_v
                        ]
                        subprocess.run(cmd_dummy, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                    process_single_scene_bulletproof(raw_v, sc["audio"], scene_v, is_port, amb_vol_float, workdir, idx)

                    if os.path.exists(raw_v):
                        os.remove(raw_v)

                    f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

            # 4. Xuất Master + Lồng BGM điện ảnh
            status.update(label="⚡ 4/4: Ghép nối Master thành phẩm và hòa âm...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "compilation_master_pro.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_raw = os.path.join(workdir, "bgm_raw.mp3")
            bgm_fitted = os.path.join(workdir, "bgm_fitted.wav")
            has_bgm = (bgm_volume > 0) and download_file_safe(DRAMA_BGM_URL, bgm_raw)

            if has_bgm:
                cmd_prep_bgm = [
                    FFMPEG_EXE, "-y",
                    "-stream_loop", "-1", "-i", bgm_raw,
                    "-t", f"{total_duration_video:.3f}",
                    "-ar", "44100", "-ac", "2",
                    bgm_fitted
                ]
                subprocess.run(cmd_prep_bgm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                vol_bgm_float = bgm_volume / 100.0
                cmd_mix = [
                    FFMPEG_EXE, "-y",
                    "-i", temp_merged,
                    "-i", bgm_fitted,
                    "-filter_complex",
                    f"[0:a]volume=1.0[a0];[1:a]volume={vol_bgm_float:.2f}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{total_duration_video:.3f}",
                    final_mp4
                ]
                subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                shutil.copy(temp_merged, final_mp4)

            status.update(label=f"🎉 Hoàn thành video Compilation {calc_clips * 5} giây xuất sắc!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
                data=v_bytes,
                file_name=f"compilation_{calc_clips * 5}s_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
