# -*- coding: utf-8 -*-
import os
import re
import json
import math
import shutil
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

# Lấy đường dẫn FFmpeg độc lập
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Studio POV Master All-In-One", page_icon="🎬", layout="centered")

FPS = 30
STT_MODEL = "whisper-large-v3-turbo"
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"

# Tự động lấy key từ Secrets
try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Engine")
st.caption("Phiên bản All-In-One: Tích hợp POV Đời thực & Lồng tiếng Thú cưng bựa")

# CHỌN CHẾ ĐỘ VIDEO
app_mode = st.radio(
    "Chọn định dạng sản xuất:",
    ["🐾 Lồng tiếng Thú cưng bựa (Tự sinh thoại & Giọng hoạt hình)", 
     "🎥 POV Điện ảnh / Đời sống thực tế (Bản nguyên bản)"],
    horizontal=True
)

if app_mode == "🐾 Lồng tiếng Thú cưng bựa (Tự sinh thoại & Giọng hoạt hình)":
    voice_pitch = st.select_slider(
        "Tông giọng lồng tiếng:",
        options=["Hơi nhí nhảnh (1.18x)", "Chuẩn Hamham lầy lội (1.28x)", "Sóc chuột Chipmunk (1.40x)"],
        value="Chuẩn Hamham lầy lội (1.28x)"
    )
    pitch_scale = 1.28 if "1.28x" in voice_pitch else (1.18 if "1.18x" in voice_pitch else 1.40)
    topic_input = st.text_area("Bối cảnh / Màn kịch bựa:", value="Mèo vàng bị sen ngó lơ đi nựng mèo đen, mèo vàng lên kế hoạch giấu sổ đỏ")
    uploaded_audio = None
    genre_style = "Funny Pets POV"
else:
    genre_style = st.selectbox(
        "Chọn phong cách & Tone màu chủ đạo của Video:",
        [
            "Đời sống thường nhật & Bụi bặm (Street Life / Realistic)",
            "Tâm lý / Góc khuất & U tối (Dark Moody POV)",
            "Nghề nghiệp / Tươi sáng & Động lực (Bright Career)",
            "Tài chính / Khởi nghiệp & Kịch tính (Corporate / Hustle)"
        ]
    )
    uploaded_audio = st.file_uploader("Tải lên file Voice của bạn (Nếu có):", type=["mp3", "wav", "m4a", "ogg"])
    topic_input = st.text_area("Chủ đề kịch bản (Khi không có file voice tải lên):", placeholder="VD: Khung cảnh thành phố mưa đêm, ánh đèn neon...")
    pitch_scale = 1.0

col1, col2 = st.columns(2)
with col1:
    orientation_opt = st.selectbox("Khung hình:", ["portrait (Dọc 9:16 Shorts/TikTok)", "landscape (Ngang 16:9 YouTube)"])
with col2:
    manual_dur = st.number_input("Thời lượng ước tính (giây):", min_value=5, max_value=120, value=15, step=5)

# ==============================================================================
# HÀM XỬ LÝ KỸ THUẬT
# ==============================================================================

async def generate_tts(text: str, out_audio: str, pitch_rate: float):
    raw_tts = out_audio + "_raw.mp3"
    comm = edge_tts.Communicate(text, voice="vi-VN-HoaiMyNeural")
    await comm.save(raw_tts)
    
    if pitch_rate != 1.0:
        in_rate = 24000
        out_rate = int(in_rate * pitch_rate)
        tempo_adj = 1.0 / pitch_rate
        cmd = [
            FFMPEG_EXE, "-y", "-i", raw_tts,
            "-af", f"asetrate={out_rate},atempo={tempo_adj:.3f}",
            out_audio
        ]
    else:
        cmd = [FFMPEG_EXE, "-y", "-i", raw_tts, "-c", "copy", out_audio]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(raw_tts):
        os.remove(raw_tts)

def get_audio_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 4.0

def get_pexels_video(query: str, p_key: str, orient: str, used_ids: set) -> str:
    try:
        url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=10&orientation={orient}"
        r = requests.get(url, headers={"Authorization": p_key.strip()}, timeout=8)
        if r.ok and r.json().get("videos"):
            for v in r.json()["videos"]:
                v_id = v.get("id")
                if v_id and v_id not in used_ids:
                    files = v.get("video_files", [])
                    hd = next((f["link"] for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"), None)
                    if not hd and files:
                        hd = files[0].get("link")
                    if hd:
                        used_ids.add(v_id)
                        return hd
    except Exception:
        pass
    return None

def download_file(url: str, dest: str):
    with requests.get(url, stream=True, timeout=20) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)

def cut_clip(raw_p: str, out_p: str, dur: float, is_port: bool):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    cmd = [
        FFMPEG_EXE, "-y", "-ss", "0",
        "-i", raw_p, "-t", f"{dur:.3f}",
        "-vf", f"{res_f},fps={FPS}",
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        out_p
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("⚡ Bắt Đầu Sản Xuất Video Hoàn Chỉnh", use_container_width=True, type="primary"):
    status = st.status("Đang chuẩn bị sản xuất...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_all_")
    used_ids = set()
    is_port = "portrait" in orientation_opt
    orient_tag = "portrait" if is_port else "landscape"

    try:
        client = Groq(api_key=groq_key.strip())
        scenes = []

        # ----------------------------------------------------
        # KỊCH BẢN 1: CHẾ ĐỘ THÚ CƯNG BỰA
        # ----------------------------------------------------
        if "Thú cưng" in app_mode:
            status.update(label="🧠 1/4: AI viết kịch bản độc thoại lầy lội & gán từ khóa...")
            prompt = f"""Bạn là biên kịch video hài TikTok dạng thú cưng độc thoại (phong cách Hamham).
Bối cảnh: "{topic_input}".
Hãy tạo từ 3 đến 4 cảnh ngắn. Mỗi cảnh gồm:
- `voice_line`: Câu thoại tiếng Việt ngắn (dưới 12 từ), cà khịa, lầy lội hoặc than vãn.
- `query_en`: 2-3 từ khóa tiếng Anh miêu tả đúng con vật và hành vi đó trên Pexels.

Trả về DUY NHẤT một JSON hợp lệ:
[
  {{"voice_line": "Hạnh phúc quá ha! Tối nay khỏi tìm sổ đỏ luôn nha!", "query_en": "orange cat glaring"}},
  {{"voice_line": "Ủa cái gì ngon vậy, không chia miếng là tao cắn!", "query_en": "funny hungry puppy"}}
]"""
            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.7)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else []

            status.update(label="🎙️ 2/4: Đang tạo voice the thé ngộ nghĩnh...")
            for i, sc in enumerate(parsed):
                aud_p = os.path.join(workdir, f"v_{i:02d}.mp3")
                asyncio.run(generate_tts(sc["voice_line"], aud_p, pitch_scale))
                sc_dur = get_audio_duration(aud_p)
                scenes.append({"query": sc["query_en"], "dur": max(3.0, sc_dur + 0.5), "audio": aud_p})

        # ----------------------------------------------------
        # KỊCH BẢN 2: CHẾ ĐỘ ĐIỆN ẢNH / VOICE RIÊNG
        # ----------------------------------------------------
        else:
            if uploaded_audio:
                status.update(label="🎙️ 1/4: Whisper phân tích audio của bạn...")
                main_aud = os.path.join(workdir, "voice_input.mp3")
                with open(main_aud, "wb") as f:
                    f.write(uploaded_audio.getbuffer())
                total_aud_dur = get_audio_duration(main_aud)

                with open(main_aud, "rb") as fh:
                    tr = client.audio.transcriptions.create(file=fh, model=STT_MODEL, response_format="verbose_json")
                r_segs = getattr(tr, "segments", []) or tr.get("segments", [])
                
                c_text = ""
                c_start = 0.0
                for s in r_segs:
                    txt = s.get("text", "").strip() if isinstance(s, dict) else s.text.strip()
                    s_st = s.get("start", 0.0) if isinstance(s, dict) else s.start
                    s_ed = s.get("end", 0.0) if isinstance(s, dict) else s.end

                    if not c_text:
                        c_start = s_st
                        c_text = txt
                    else:
                        c_text += " " + txt

                    if (s_ed - c_start) >= 4.5:
                        scenes.append({"dur": s_ed - c_start, "text": c_text})
                        c_text = ""
                if c_text:
                    scenes.append({"dur": max(3.0, total_aud_dur - c_start), "text": c_text})
            else:
                num_c = math.ceil(manual_dur / 5.0)
                scenes = [{"dur": 5.0, "text": topic_input} for _ in range(num_c)]

            status.update(label=f"🧠 2/4: Phân tích cảnh điện ảnh tone {genre_style}...")
            prompt = f"""Break down this into {len(scenes)} visual scene keywords for Pexels. Tone: "{genre_style}".
Text: {[s['text'][:70] for s in scenes]}
Return ONLY a JSON array of strings: ["keyword 1", "keyword 2"]"""
            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            kws = json.loads(match.group(0)) if match else [genre_style] * len(scenes)
            for i in range(len(scenes)):
                scenes[i]["query"] = kws[i] if i < len(kws) else "cinematic reality"
                scenes[i]["audio"] = None

        # ----------------------------------------------------
        # RENDER CÁC ĐOẠN VIDEO
        # ----------------------------------------------------
        status.update(label="🎬 3/4: Đang tải B-roll khớp từng cảnh & chuẩn hóa...")
        clips_txt = os.path.join(workdir, "clips.txt")
        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                v_url = get_pexels_video(sc["query"], pexels_key, orient_tag, used_ids)
                if not v_url:
                    v_url = get_pexels_video("cinematic realistic" if "Điện ảnh" in app_mode else "funny pets", pexels_key, orient_tag, used_ids)

                raw_v = os.path.join(workdir, f"r_{idx:02d}.mp4")
                cut_v = os.path.join(workdir, f"c_{idx:02d}.mp4")
                download_file(v_url, raw_v)
                cut_clip(raw_v, cut_v, sc["dur"], is_port)
                if os.path.exists(raw_v):
                    os.remove(raw_v)

                # Nếu có voice từng câu (chế độ bựa) -> Ghép trực tiếp vào clip
                if sc.get("audio"):
                    sync_v = os.path.join(workdir, f"synced_{idx:02d}.mp4")
                    cmd_m = [
                        FFMPEG_EXE, "-y", "-i", cut_v, "-i", sc["audio"],
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", sync_v
                    ]
                    subprocess.run(cmd_m, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    f_cl.write(f"file '{os.path.abspath(sync_v)}'\n")
                else:
                    f_cl.write(f"file '{os.path.abspath(cut_v)}'\n")

        # ----------------------------------------------------
        # GHÉP MASTER HOÀN THIỆN
        # ----------------------------------------------------
        status.update(label="⚡ 4/4: Đang xuất file Master...", state="running")
        final_mp4 = os.path.join(workdir, "master_final.mp4")

        if uploaded_audio and "Điện ảnh" in app_mode:
            cmd_f = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", clips_txt,
                "-i", main_aud, "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", final_mp4
            ]
        else:
            cmd_f = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", clips_txt, "-c", "copy", final_mp4]

        subprocess.run(cmd_f, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        status.update(label="🎉 Video đã hoàn thành xuất sắc!", state="complete")

        with open(final_mp4, "rb") as out_f:
            v_bytes = out_f.read()

        st.video(v_bytes)
        st.download_button(
            label="⬇️ Tải Video Hoàn Chỉnh Về Máy",
            data=v_bytes,
            file_name=f"pov_master_{int(time.time())}.mp4",
            mime="video/mp4",
            use_container_width=True
        )

    except Exception as e:
        status.update(label=f"❌ Thất bại: {str(e)}", state="error")
        st.error(f"Chi tiết lỗi: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
