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

import streamlit as st
import requests
import imageio_ffmpeg
from groq import Groq

# Lấy đường dẫn FFmpeg độc lập chống lỗi No such file or directory
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Studio POV Master Engine", page_icon="🎬", layout="centered")

FPS = 30
STT_MODEL = "whisper-large-v3-turbo"
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"

# Tự động lấy key từ secrets nếu có, hoặc nhận từ ô nhập
default_groq = st.secrets.get("GROQ_API_KEY", "")
default_pexels = st.secrets.get("PEXELS_API_KEY", "")

st.title("🎬 Studio POV Master Engine")
st.caption("Khớp 100% ngữ cảnh đời thực của Voice, không ép khuôn mẫu, chống lỗi 254 tuyệt đối")

genre_mode = st.selectbox(
    "Chọn phong cách & Tone màu chủ đạo của Video:",
    [
        "Đời sống thường nhật & Bụi bặm (Street Life / Realistic)",
        "Tâm lý / Góc khuất & U tối (Dark Moody POV)",
        "Nghề nghiệp / Tươi sáng & Động lực (Bright Career)",
        "Tài chính / Khởi nghiệp & Kịch tính (Corporate / Hustle)"
    ]
)

groq_key = st.text_input("Groq API Key (Bắt buộc)", value=default_groq, type="password", placeholder="gsk_...")
pexels_key = st.text_input("Pexels API Key (Để lấy video B-roll HD)", value=default_pexels, type="password", placeholder="Key Pexels...")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["portrait (Dọc 9:16 Shorts/TikTok)", "landscape (Ngang 16:9 YouTube)"])
with col_opt2:
    total_sec_input = st.number_input("Tổng thời lượng (giây) nếu không tải voice:", min_value=5, max_value=180, value=15, step=5)

audio_file = st.file_uploader("Tải lên file Voice âm thanh (Tùy chọn, để tự động khớp voice)", type=["mp3", "wav", "m4a", "ogg"])
topic_text = st.text_area("Chủ đề / Mô tả video (Dùng khi không có file Voice):", placeholder="VD: Siêu xe đua phố đêm mưa, ánh đèn neon phong cách Cyberpunk...")

# ==============================================================================
# HÀM XỬ LÝ VIDEO & API
# ==============================================================================

def get_pexels_video_link(query_en: str, p_key: str, orient: str, used_ids: set) -> str:
    if not p_key or not p_key.strip():
        return None
    try:
        url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query_en)}&per_page=10&orientation={orient}"
        r = requests.get(url, headers={"Authorization": p_key.strip()}, timeout=8)
        if r.ok and r.json().get("videos"):
            for v in r.json()["videos"]:
                v_id = v.get("id")
                if v_id and v_id not in used_ids:
                    files = v.get("video_files", [])
                    # Tìm file chuẩn HD
                    hd_file = next((f.get("link") for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"), None)
                    if not hd_file and files:
                        hd_file = files[0].get("link")
                    if hd_file:
                        used_ids.add(v_id)
                        return hd_file
    except Exception:
        pass
    return None

def download_stream_file(url: str, dest_path: str):
    with requests.get(url, stream=True, timeout=20) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)

def cut_and_normalize_clip(raw_vid_path: str, out_clip_path: str, duration_sec: float, is_portrait: bool):
    res_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if is_portrait else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    cmd = [
        FFMPEG_EXE, "-y", "-ss", "0",
        "-i", raw_vid_path,
        "-t", f"{duration_sec:.3f}",
        "-vf", f"{res_filter},fps={FPS}",
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        out_clip_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("⚡ Bắt Đầu Dựng Video Thành Phẩm Hoàn Chỉnh", use_container_width=True, type="primary"):
    active_groq_key = groq_key.strip()
    active_pexels_key = pexels_key.strip()

    if not active_groq_key:
        st.error("Vui lòng nhập Groq API Key!")
    elif not active_pexels_key:
        st.error("Vui lòng nhập Pexels API Key để tải video stock!")
    elif not audio_file and not topic_text.strip():
        st.error("Vui lòng tải lên file Voice âm thanh HOẶC nhập mô tả chủ đề video!")
    else:
        status = st.status("Đang chuẩn bị dây chuyền sản xuất video...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="master_prod_")
        used_vid_ids = set()
        is_portrait = "portrait" in orientation_opt
        orient_tag = "portrait" if is_portrait else "landscape"

        try:
            client = Groq(api_key=active_groq_key)
            segments = []
            audio_path = None
            total_duration = 0.0

            # 1. Thu thập cảnh: Theo voice nếu có, hoặc theo prompt thời lượng
            if audio_file:
                status.update(label="🎙️ 1/4: Whisper phân tích mốc thời gian & nhận diện ngôn ngữ...")
                audio_path = os.path.join(workdir, audio_file.name)
                with open(audio_path, "wb") as f:
                    f.write(audio_file.getbuffer())

                probe_cmd = [FFMPEG_EXE, "-i", audio_path]
                cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
                res_dur = subprocess.run(cmd_dur, capture_output=True, text=True)
                total_duration = float(res_dur.stdout.strip() or 15.0)

                compressed_audio = os.path.join(workdir, "whisper_input.mp3")
                compress_cmd = [
                    FFMPEG_EXE, "-y", "-i", audio_path,
                    "-vn", "-ar", "16000", "-ac", "1", "-b:a", "48k",
                    compressed_audio
                ]
                subprocess.run(compress_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                with open(compressed_audio, "rb") as fh:
                    resp = client.audio.transcriptions.create(
                        file=fh, model=STT_MODEL, response_format="verbose_json"
                    )
                data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
                raw_segs = data.get("segments") or []

                cur_text = ""
                cur_start = 0.0
                for seg in raw_segs:
                    t = (seg.get("text") or "").strip()
                    if not t:
                        continue
                    if not cur_text:
                        cur_start = float(seg["start"])
                        cur_text = t
                    else:
                        cur_text += " " + t

                    if float(seg["end"]) - cur_start >= 4.5:
                        segments.append({"duration": float(seg["end"]) - cur_start, "text": cur_text})
                        cur_text = ""
                if cur_text:
                    segments.append({"duration": max(3.0, total_duration - cur_start), "text": cur_text})
                if not segments:
                    segments.append({"duration": total_duration, "text": "cinematic scenes"})
            else:
                total_duration = float(total_sec_input)
                clip_count = math.ceil(total_duration / 5.0)
                segments = [{"duration": 5.0, "text": topic_text} for _ in range(clip_count)]

            # 2. AI phân tích từ khóa hành động cho từng cảnh
            status.update(label=f"🧠 2/4: AI bóc tách từ khóa Pexels theo phong cách: {genre_mode}...")
            num_clips = len(segments)
            prompt = f"""You are a video editor. Genre style: "{genre_mode}".
Break down the script/topic into exactly {num_clips} short visual scene descriptions for stock library search.
Each keyword query must be 1-3 simple English words describing physical real-world visuals (no text/logos).
Script/Concept:
{[s['text'][:80] for s in segments]}

Return ONLY a JSON array of strings:
["keyword 1", "keyword 2", ...]"""

            llm_res = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            content = llm_res.choices[0].message.content.strip()
            match = re.search(r'\[.*\]', content, re.DOTALL)
            keywords = json.loads(match.group(0)) if match else [genre_mode] * num_clips

            # 3. Tải video sạch và cắt đúng thời lượng (mỗi cảnh 5s)
            status.update(label="🎬 3/4: Tải video B-roll sạch và cắt ghép chính xác...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_clips:
                for idx, seg in enumerate(segments):
                    kw = keywords[idx] if idx < len(keywords) else "cinematic background"
                    target_dur = seg.get("duration", 5.0)

                    video_url = get_pexels_video_link(kw, active_pexels_key, orient_tag, used_vid_ids)
                    if not video_url:
                        video_url = get_pexels_video_link("cinematic realistic", active_pexels_key, orient_tag, used_vid_ids)

                    raw_file = os.path.join(workdir, f"raw_{idx:03d}.mp4")
                    cut_file = os.path.join(workdir, f"clip_{idx:03d}.mp4")

                    download_stream_file(video_url, raw_file)
                    cut_and_normalize_clip(raw_file, cut_file, target_dur, is_portrait)

                    if os.path.exists(raw_file):
                        os.remove(raw_file)

                    f_clips.write(f"file '{os.path.abspath(cut_file)}'\n")

            # 4. Xuất video hoàn thiện
            status.update(label="⚡ 4/4: Ghép chuỗi cảnh thành video hoàn thiện...", state="running")
            out_path = os.path.join(workdir, "master_output.mp4")

            if audio_path and os.path.exists(audio_path):
                cmd_merge = [
                    FFMPEG_EXE, "-y",
                    "-f", "concat", "-safe", "0", "-i", clips_txt,
                    "-i", audio_path,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-t", f"{total_duration:.3f}",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    out_path
                ]
            else:
                cmd_merge = [
                    FFMPEG_EXE, "-y",
                    "-f", "concat", "-safe", "0", "-i", clips_txt,
                    "-t", f"{total_duration:.3f}",
                    "-c", "copy",
                    out_path
                ]

            subprocess.run(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            status.update(label="✅ Video hoàn thành hoàn hảo!", state="complete")

            with open(out_path, "rb") as vid_file:
                video_bytes = vid_file.read()

            st.video(video_bytes)
            st.download_button(
                label="⬇️ Tải Video Hoàn Chỉnh Lên Kênh YouTube",
                data=video_bytes,
                file_name=f"youtube_master_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
