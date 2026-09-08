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

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Studio Video Master Pro", page_icon="🎙️", layout="centered")

FPS = 30
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"

# Nhạc nền tài chính / tin tức / công nghệ chuẩn phong cách Explainer
NEWS_BGM_URL = "https://cdn.pixabay.com/download/audio/2022/11/06/audio_c9735d4928.mp3"

# Sound Effect chuyển cảnh chuyên nghiệp (Whoosh / Ting)
TRANSITION_SFX_URL = "https://www.myinstants.com/media/sounds/swoosh-sound-effect.mp3"

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎙️ Tool Tạo Video Thuyết Minh & Kiến Thức Chuyên Nghiệp")
st.caption("Giọng Nam Minh Báo Đài + BGM Tin tức + B-roll Pexels + Hiệu ứng chuyển cảnh Whoosh")

# Lựa chọn giọng đọc
voice_choice = st.selectbox(
    "Chọn giọng đọc thuyết minh:",
    [
        "Nam miền Bắc trầm ấm / Báo đài (vi-VN-NamMinhNeural)",
        "Nữ miền Bắc truyền cảm / Tin tức (vi-VN-HoaiMyNeural)"
    ]
)
selected_voice = "vi-VN-NamMinhNeural" if "NamMinh" in voice_choice else "vi-VN-HoaiMyNeural"

col1, col2 = st.columns(2)
with col1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["portrait (Dọc 9:16 Shorts/TikTok/Reels)", "landscape (Ngang 16:9 YouTube)"])
with col2:
    speech_rate = st.select_slider("Tốc độ đọc giọng:", options=["Bình thường (1.0x)", "Nhanh vừa (1.1x)", "Cuốn hút / Tin tức nhanh (1.2x)"], value="Nhanh vừa (1.1x)")

rate_tag = "+0%" if "1.0x" in speech_rate else ("+10%" if "1.1x" in speech_rate else "+20%")

content_script = st.text_area(
    "Nội dung kịch bản / Kiến thức thuyết minh:",
    value="""Bảo hiểm sức khỏe là gì?
Bảo hiểm sức khỏe giúp giảm gánh nặng chi phí khám chữa bệnh, hỗ trợ tài chính khi gặp rủi ro sức khỏe và mang lại sự an tâm cho bạn và gia đình.
Nhờ bảo hiểm, bạn có thể tiếp cận dịch vụ y tế tốt hơn mà không lo chi phí quá cao, đồng thời bảo vệ tài chính trước những biến cố bất ngờ.
Ví dụ: khi bạn không may nhập viện, bảo hiểm sẽ chi trả phần lớn viện phí, thuốc men, phẫu thuật, giúp bạn yên tâm điều trị.""",
    height=160
)

# ==============================================================================
# CÁC HÀM XỬ LÝ KỸ THUẬT
# ==============================================================================

async def generate_pro_voice(text: str, out_audio: str, voice_name: str, rate_str: str):
    comm = edge_tts.Communicate(text, voice=voice_name, rate=rate_str)
    await comm.save(out_audio)

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

def cut_clip_with_pro_sub(raw_p: str, out_p: str, dur: float, is_port: bool, subtitle_text: str = ""):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    
    clean_sub = subtitle_text.replace("'", "").replace('"', '').replace(":", " -")
    words = clean_sub.split()
    lines = []
    chunk_size = 5 if is_port else 8
    for i in range(0, len(words), chunk_size):
        lines.append(" ".join(words[i:i+chunk_size]))
    formatted_sub = "\\n".join(lines)

    font_size = 46 if is_port else 34
    draw_filter = f"{res_f},fps={FPS},drawtext=text='{formatted_sub}':fontcolor=white:fontsize={font_size}:box=1:boxcolor=black@0.7:boxborderw=14:x=(w-text_w)/2:y=(h-text_h)/2+300"

    cmd = [
        FFMPEG_EXE, "-y", "-ss", "0",
        "-i", raw_p, "-t", f"{dur:.3f}",
        "-vf", draw_filter,
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        out_p
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("⚡ Bắt Đầu Tạo Video Thuyết Minh Chuyên Nghiệp", use_container_width=True, type="primary"):
    if not content_script.strip():
        st.warning("Vui lòng nhập nội dung thuyết minh.")
    else:
        status = st.status("Đang sản xuất video thuyết minh kiến thức...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="pro_explainer_")
        used_ids = set()
        is_port = "portrait" in orientation_opt
        orient_tag = "portrait" if is_port else "landscape"

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. AI chia kịch bản thành từng phân đoạn ngắn & gán từ khóa B-roll Pexels chính xác
            status.update(label="🧠 1/4: AI phân tích kịch bản và gán bối cảnh B-roll tương ứng...")
            prompt = f"""Bạn là đạo diễn video kiến thức / tin tức chuyên nghiệp (dạng Explainer Video).
Nội dung bài đọc:
\"\"\"{content_script}\"\"\"

Nhiệm vụ:
Chia đoạn văn trên thành 4 đến 6 câu ngắn gọn liền mạch. Với mỗi câu, gán 2-3 từ khóa tiếng Anh miêu tả đúng nội dung thực tế để tìm video stock trên Pexels (ví dụ: hospital, doctor, family finance, insurance, money...).

Trả về DUY NHẤT JSON hợp lệ dạng danh sách:
[
  {{"sentence": "Bảo hiểm sức khỏe là gì?", "query_en": "doctor consultation clinic"}},
  {{"sentence": "Bảo hiểm sức khỏe giúp giảm gánh nặng chi phí khám chữa bệnh...", "query_en": "hospital patient medical care"}}
]"""
            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else []

            # 2. Tạo giọng đọc Nam Minh / Hoài My cho từng câu
            status.update(label="🎙️ 2/4: Tạo giọng đọc phát thanh viên chuẩn đài truyền hình...")
            scenes = []
            for i, sc in enumerate(parsed):
                aud_p = os.path.join(workdir, f"v_{i:02d}.mp3")
                asyncio.run(generate_pro_voice(sc["sentence"], aud_p, selected_voice, rate_tag))
                dur = get_audio_duration(aud_p)
                scenes.append({
                    "sentence": sc["sentence"],
                    "query": sc["query_en"],
                    "audio": aud_p,
                    "dur": max(2.5, dur + 0.3)
                })

            # Tải âm thanh chuyển cảnh Whoosh
            whoosh_sfx = os.path.join(workdir, "whoosh.mp3")
            try:
                download_file(TRANSITION_SFX_URL, whoosh_sfx)
            except Exception:
                whoosh_sfx = None

            # 3. Tải B-roll và ghép từng phân đoạn kèm phụ đề
            status.update(label="🎬 3/4: Tải B-roll HD & in phụ đề chuẩn phong cách báo đài...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = get_pexels_video(sc["query"], pexels_key, orient_tag, used_ids)
                    if not v_url:
                        v_url = get_pexels_video("medical technology finance", pexels_key, orient_tag, used_ids)

                    raw_v = os.path.join(workdir, f"r_{idx:02d}.mp4")
                    cut_v = os.path.join(workdir, f"c_{idx:02d}.mp4")
                    download_file(v_url, raw_v)

                    cut_clip_with_pro_sub(raw_v, cut_v, sc["dur"], is_port, sc["sentence"])
                    if os.path.exists(raw_v):
                        os.remove(raw_v)

                    # Ghép tiếng đọc vào video
                    synced_v = os.path.join(workdir, f"synced_{idx:02d}.mp4")
                    cmd_sync = [
                        FFMPEG_EXE, "-y", "-i", cut_v, "-i", sc["audio"],
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", synced_v
                    ]
                    subprocess.run(cmd_sync, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")

            # 4. Ghép toàn bộ phân cảnh + Lồng BGM Tin tức / Corporate ngầm
            status.update(label="⚡ 4/4: Đang hòa âm BGM tin tức & xuất file Master...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "pro_explainer_master.mp4")

            cmd_f = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", clips_txt, "-c", "copy", temp_merged]
            subprocess.run(cmd_f, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            # Mix nhạc nền tin tức ở mức 12-15%
            bgm_path = os.path.join(workdir, "news_bgm.mp3")
            try:
                download_file(NEWS_BGM_URL, bgm_path)
                cmd_mix = [
                    FFMPEG_EXE, "-y",
                    "-i", temp_merged,
                    "-stream_loop", "-1", "-i", bgm_path,
                    "-filter_complex", "[0:a]volume=1.0[a0];[1:a]volume=0.14[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    final_mp4
                ]
                subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception:
                shutil.copy(temp_merged, final_mp4)

            status.update(label="🎉 Video thuyết minh chuyên nghiệp đã hoàn tất!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label="⬇️ Tải Video Thuyết Minh HD Về Máy",
                data=v_bytes,
                file_name=f"explainer_video_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
