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

# Khởi tạo binary FFmpeg độc lập
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Studio POV Master Pro Engine", page_icon="🎙️", layout="centered")

FPS = 30
STT_MODEL = "whisper-large-v3-turbo"
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
NEWS_BGM_URL = "https://cdn.pixabay.com/download/audio/2022/11/06/audio_c9735d4928.mp3"
FONT_URL = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf"

# Nạp credentials từ secrets
try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Pro Engine")
st.caption("Khớp 100% ngữ cảnh B-roll, sửa triệt để lỗi cú pháp drawtext & tối ưu âm thanh Explainer")

# Lựa chọn định dạng sản xuất
app_mode = st.radio(
    "Chọn phương thức sản xuất video:",
    [
        "🎙️ Tự động tạo Voice Thuyết Minh + Subtitle (Explainer Pro)",
        "🎧 Dùng Voice Tự Tải Lên (Phân tích Whisper + Khớp B-roll)",
        "🐾 POV Thú Cưng Bựa / Hài Hước (The Thé + Sound Meme)"
    ],
    horizontal=False
)

# Cấu hình chi tiết theo từng chế độ
if app_mode == "🎙️ Tự động tạo Voice Thuyết Minh + Subtitle (Explainer Pro)":
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        voice_choice = st.selectbox(
            "Giọng đọc thuyết minh:",
            ["Nam miền Bắc chuẩn phát thanh viên (vi-VN-NamMinhNeural)", "Nữ miền Bắc truyền cảm (vi-VN-HoaiMyNeural)"]
        )
        selected_voice = "vi-VN-NamMinhNeural" if "NamMinh" in voice_choice else "vi-VN-HoaiMyNeural"
    with col_v2:
        speech_rate = st.select_slider("Tốc độ đọc:", options=["Chuẩn (1.0x)", "Nhanh vừa (1.1x)", "Tin tức dồn dập (1.2x)"], value="Nhanh vừa (1.1x)")
        rate_tag = "+0%" if "1.0x" in speech_rate else ("+10%" if "1.1x" in speech_rate else "+20%")
    
    pitch_scale = 1.0
    uploaded_audio = None
    content_script = st.text_area(
        "Kịch bản thuyết minh:",
        value="""Bảo hiểm sức khỏe là gì?
Bảo hiểm sức khỏe giúp giảm gánh nặng chi phí khám chữa bệnh, hỗ trợ tài chính khi gặp rủi ro sức khỏe và mang lại sự an tâm cho bạn và gia đình.
Nhờ bảo hiểm, bạn có thể tiếp cận dịch vụ y tế tốt hơn mà không lo chi phí quá cao, đồng thời bảo vệ tài chính trước những biến cố bất ngờ.
Ví dụ: khi bạn không may nhập viện, bảo hiểm sẽ chi trả phần lớn viện phí, thuốc men, phẫu thuật, giúp bạn yên tâm điều trị.""",
        height=140
    )

elif app_mode == "🎧 Dùng Voice Tự Tải Lên (Phân tích Whisper + Khớp B-roll)":
    uploaded_audio = st.file_uploader("Tải lên file Voice âm thanh:", type=["mp3", "wav", "m4a", "ogg"])
    content_script = st.text_area("Chủ đề bổ trợ (Tùy chọn):", placeholder="Nhập tóm tắt chủ đề kịch bản nếu cần...")
    selected_voice = None
    pitch_scale = 1.0
    rate_tag = "+0%"

else: # Thú cưng bựa
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        pet_choice = st.selectbox("Nhân vật chính:", ["Mèo (Cat POV)", "Chó (Dog POV)", "Thú cưng chung"])
    with col_p2:
        voice_pitch = st.select_slider("Tông giọng hoạt hình:", options=["Nhí nhảnh (1.18x)", "Chuẩn Hamham (1.28x)", "Chipmunk (1.40x)"], value="Chuẩn Hamham (1.28x)")
        pitch_scale = 1.28 if "1.28x" in voice_pitch else (1.18 if "1.18x" in voice_pitch else 1.40)
    
    selected_voice = "vi-VN-HoaiMyNeural"
    rate_tag = "+0%"
    uploaded_audio = None
    content_script = st.text_area("Mô tả hoạt cảnh hài hước:", value="Mèo vàng bị sen ngó lơ đi nựng mèo đen, mèo vàng lên kế hoạch giấu sổ đỏ")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình video:", ["portrait (Dọc 9:16 Shorts/TikTok)", "landscape (Ngang 16:9 YouTube)"])
with col_opt2:
    bgm_volume = st.slider("Âm lượng nhạc nền (%):", min_value=5, max_value=30, value=12, step=1)

# ==============================================================================
# HÀM XỬ LÝ KỸ THUẬT AN TOÀN
# ==============================================================================

def download_file(url: str, dest: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, headers=headers, stream=True, timeout=25) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)

def get_audio_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 4.0

async def generate_tts(text: str, out_audio: str, voice_name: str, rate_str: str, pitch_rate: float):
    raw_tts = out_audio + "_raw.mp3"
    comm = edge_tts.Communicate(text, voice=voice_name, rate=rate_str)
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

def get_pexels_video(query: str, p_key: str, orient: str, used_ids: set) -> str:
    try:
        url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=12&orientation={orient}"
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

def format_text_lines(text: str, words_per_line: int = 5) -> str:
    words = text.strip().split()
    lines = []
    for i in range(0, len(words), words_per_line):
        lines.append(" ".join(words[i:i + words_per_line]))
    return "\n".join(lines)

def cut_clip_with_safe_drawtext(raw_p: str, out_p: str, dur: float, is_port: bool, sub_text: str, font_path: str, workdir: str, clip_idx: int):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    
    # Nếu có phụ đề, lưu vào textfile trung gian để triệt tiêu lỗi ký tự đặc biệt
    if sub_text and sub_text.strip():
        txt_path = os.path.join(workdir, f"sub_{clip_idx:03d}.txt")
        formatted = format_text_lines(sub_text, words_per_line=5 if is_port else 8)
        with open(txt_path, "w", encoding="utf-8") as tf:
            tf.write(formatted)
        
        escaped_txt_path = txt_path.replace("\\", "/").replace(":", "\\:")
        escaped_font_path = font_path.replace("\\", "/").replace(":", "\\:")
        font_size = 48 if is_port else 34
        y_pos = "(h-text_h)/2+300" if is_port else "h-text_h-80"
        
        vf_filter = (
            f"{res_f},fps={FPS},"
            f"drawtext=fontfile='{escaped_font_path}':textfile='{escaped_txt_path}':"
            f"fontcolor=white:fontsize={font_size}:box=1:boxcolor=black@0.7:boxborderw=12:"
            f"x=(w-text_w)/2:y={y_pos}"
        )
    else:
        vf_filter = f"{res_f},fps={FPS}"

    cmd = [
        FFMPEG_EXE, "-y", "-ss", "0",
        "-i", raw_p, "-t", f"{dur:.3f}",
        "-vf", vf_filter,
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        out_p
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Sản Xuất Video Hoàn Chỉnh", use_container_width=True, type="primary"):
    if not uploaded_audio and not content_script.strip():
        st.error("Vui lòng nhập nội dung kịch bản hoặc tải lên file Voice âm thanh!")
    else:
        status = st.status("Khởi động dây chuyền sản xuất video...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="pro_engine_")
        used_ids = set()
        is_port = "portrait" in orientation_opt
        orient_tag = "portrait" if is_port else "landscape"

        try:
            client = Groq(api_key=groq_key.strip())
            
            # Chuẩn bị Font chữ an toàn
            status.update(label="🔤 Đang thiết lập bộ font chữ chống lỗi hiển thị...")
            font_path = os.path.join(workdir, "Roboto-Bold.ttf")
            download_file(FONT_URL, font_path)

            scenes = []
            audio_track_mode = "split" # split: từng phân đoạn có audio riêng; single: 1 file voice duy nhất

            # ----------------------------------------------------
            # 1. PHÂN TÍCH PHÂN CẢNH VÀ XỬ LÝ ÂM THANH
            # ----------------------------------------------------
            if uploaded_audio:
                status.update(label="🎙️ 1/4: Whisper phân tích mốc thời gian từ file voice tải lên...")
                audio_track_mode = "single"
                single_audio_path = os.path.join(workdir, "uploaded_voice.mp3")
                with open(single_audio_path, "wb") as f:
                    f.write(uploaded_audio.getbuffer())
                
                total_aud_dur = get_audio_duration(single_audio_path)
                compressed_audio = os.path.join(workdir, "whisper_temp.mp3")
                subprocess.run([
                    FFMPEG_EXE, "-y", "-i", single_audio_path,
                    "-vn", "-ar", "16000", "-ac", "1", "-b:a", "48k",
                    compressed_audio
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                with open(compressed_audio, "rb") as fh:
                    tr = client.audio.transcriptions.create(file=fh, model=STT_MODEL, response_format="verbose_json")
                r_segs = getattr(tr, "segments", []) or tr.get("segments", [])

                cur_text = ""
                cur_start = 0.0
                for s in r_segs:
                    txt = (s.get("text") if isinstance(s, dict) else s.text).strip()
                    s_st = float(s.get("start") if isinstance(s, dict) else s.start)
                    s_ed = float(s.get("end") if isinstance(s, dict) else s.end)

                    if not cur_text:
                        cur_start = s_st
                        cur_text = txt
                    else:
                        cur_text += " " + txt

                    if (s_ed - cur_start) >= 4.0:
                        scenes.append({"sentence": cur_text, "dur": s_ed - cur_start, "audio": None})
                        cur_text = ""
                if cur_text:
                    scenes.append({"sentence": cur_text, "dur": max(2.5, total_aud_dur - cur_start), "audio": None})
                if not scenes:
                    scenes.append({"sentence": "Tổng quan nội dung", "dur": total_aud_dur, "audio": None})

                # Gọi LLM sinh query cho từng câu bóc tách
                status.update(label="🧠 2/4: AI gắn từ khóa hình ảnh Pexels cho từng mốc thoại...")
                prompt = f"""Break down these segments into {len(scenes)} visual scene keywords for stock video search.
Keep queries to 2-3 English words describing physical objects or settings.
Segments: {[s['sentence'][:60] for s in scenes]}
Return ONLY JSON array of strings: ["keyword 1", "keyword 2"]"""
                resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.2)
                match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
                kws = json.loads(match.group(0)) if match else ["business finance"] * len(scenes)
                for idx in range(len(scenes)):
                    scenes[idx]["query"] = kws[idx] if idx < len(kws) else "cinematic footage"

            else:
                status.update(label="🧠 1/4: AI tối ưu hóa kịch bản, chia câu & gán bối cảnh B-roll...")
                prompt = f"""Bạn là đạo diễn video thuyết minh chuyên nghiệp.
Nội dung:
\"\"\"{content_script}\"\"\"

Chia kịch bản trên thành 3 đến 6 câu ngắn liền mạch. Gán cho mỗi câu 2-3 từ khóa tiếng Anh miêu tả đúng chủ thể/bối cảnh để tìm B-roll trên Pexels.
Trả về DUY NHẤT JSON array:
[
  {{"sentence": "Câu thoại ngắn...", "query_en": "doctor clinic consultation"}}
]"""
                resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.3)
                match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
                parsed = json.loads(match.group(0)) if match else []

                status.update(label="🎙️ 2/4: Đang tạo giọng đọc thuyết minh & đo đạc thời lượng chuẩn xác...")
                for i, sc in enumerate(parsed):
                    aud_p = os.path.join(workdir, f"v_{i:02d}.mp3")
                    asyncio.run(generate_tts(sc["sentence"], aud_p, selected_voice, rate_tag, pitch_scale))
                    dur = get_audio_duration(aud_p)
                    scenes.append({
                        "sentence": sc["sentence"],
                        "query": sc["query_en"],
                        "audio": aud_p,
                        "dur": max(2.5, dur + 0.3)
                    })

            # ----------------------------------------------------
            # 2. TẢI VIDEO B-ROLL VÀ RENDER SUBTITLE BẰNG TEXTFILE
            # ----------------------------------------------------
            status.update(label="🎬 3/4: Tải B-roll HD & in phụ đề không lỗi ký tự...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = get_pexels_video(sc["query"], pexels_key, orient_tag, used_ids)
                    if not v_url:
                        v_url = get_pexels_video("medical business technology", pexels_key, orient_tag, used_ids)

                    raw_v = os.path.join(workdir, f"r_{idx:02d}.mp4")
                    cut_v = os.path.join(workdir, f"c_{idx:02d}.mp4")
                    download_file(v_url, raw_v)

                    # Gọi hàm render an toàn tuyệt đối
                    cut_clip_with_safe_drawtext(raw_v, cut_v, sc["dur"], is_port, sc["sentence"], font_path, workdir, idx)
                    if os.path.exists(raw_v):
                        os.remove(raw_v)

                    if audio_track_mode == "split" and sc.get("audio"):
                        synced_v = os.path.join(workdir, f"synced_{idx:02d}.mp4")
                        cmd_sync = [
                            FFMPEG_EXE, "-y", "-i", cut_v, "-i", sc["audio"],
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                            "-shortest", synced_v
                        ]
                        subprocess.run(cmd_sync, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                        f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")
                    else:
                        f_cl.write(f"file '{os.path.abspath(cut_v)}'\n")

            # ----------------------------------------------------
            # 3. GHÉP MASTER + LỒNG BGM THEO ÂM LƯỢNG TÙY CHỈNH
            # ----------------------------------------------------
            status.update(label="⚡ 4/4: Đang ghép chuỗi cảnh & hòa âm BGM chuyên nghiệp...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "pro_explainer_master.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_path = os.path.join(workdir, "news_bgm.mp3")
            download_file(NEWS_BGM_URL, bgm_path)
            vol_float = bgm_volume / 100.0

            if audio_track_mode == "single":
                cmd_mix = [
                    FFMPEG_EXE, "-y",
                    "-i", temp_merged,
                    "-i", single_audio_path,
                    "-stream_loop", "-1", "-i", bgm_path,
                    "-filter_complex", f"[1:a]volume=1.0[a0];[2:a]volume={vol_float:.2f}[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    final_mp4
                ]
            else:
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
            status.update(label="✅ Video hoàn thành hoàn hảo, chuẩn phong cách Explainer!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label="⬇️ Tải Video Hoàn Chỉnh Về Máy",
                data=v_bytes,
                file_name=f"explainer_master_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
