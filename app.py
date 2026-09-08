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

# Binary FFmpeg độc lập
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

st.set_page_config(page_title="Pet POV Dubbing Pro", page_icon="😼", layout="centered")

FPS = 30
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
# Nhạc nền kịch tính / căng thẳng nhẹ từ Wikimedia (Không dính 403 Forbidden)
DRAMA_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

# Lấy Key từ Secrets
try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("😼 Tool Lồng Tiếng Động Vật 'Chửi Nhau' / Đối Thoại Bựa")
st.caption("Khớp hành cảnh video mèo + Voice Nam Minh thời sự nghiêm túc cực hài")

topic_input = st.text_area(
    "Mô tả cuộc đối đầu / chửi nhau:",
    value="2 con mèo cam và mèo đen gườm nhau chửi bới tranh giành tô pate, mèo cam cà khịa trước còn mèo đen đốp chát lại"
)

col1, col2 = st.columns(2)
with col1:
    orientation_opt = st.selectbox("Khung hình video:", ["portrait (Dọc 9:16 Shorts/TikTok)", "landscape (Ngang 16:9 YouTube)"])
with col2:
    bgm_volume = st.slider("Âm lượng nhạc nền (%):", min_value=0, max_value=30, value=10, step=1)

# ==============================================================================
# HÀM XỬ LÝ
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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

def get_audio_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 3.5

async def generate_voice_nam(text: str, out_audio: str):
    # Dùng đúng giọng nam trầm Nam Minh, tốc độ chuẩn 1.0x không bóp méo
    comm = edge_tts.Communicate(text, voice="vi-VN-NamMinhNeural", rate="+5%")
    await comm.save(out_audio)

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

def cut_clip_clean(raw_p: str, out_p: str, dur: float, is_port: bool):
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"
    cmd = [
        FFMPEG_EXE, "-y", "-ss", "0",
        "-i", raw_p, "-t", f"{dur:.3f}",
        "-vf", res_f,
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        out_p
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT
# ==============================================================================
if st.button("🚀 Bắt Đầu Tạo Cuộc Đối Thoại Mèo Bựa", use_container_width=True, type="primary"):
    if not topic_input.strip():
        st.warning("Vui lòng nhập bối cảnh đối đầu.")
    else:
        status = st.status("Đang lên kịch bản đối thoại và tìm bối cảnh...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="cat_beef_")
        used_ids = set()
        is_port = "portrait" in orientation_opt
        orient_tag = "portrait" if is_port else "landscape"

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. AI viết kịch bản chửi nhau qua lại và gán hành vi cụ thể
            status.update(label="🧠 1/4: AI viết thoại chửi nhau đối lập và tìm hành vi mèo...")
            prompt = f"""Bạn là biên kịch video hài TikTok dạng lồng tiếng mèo đối đầu / chửi nhau / cà khịa tranh ăn gay cấn.
Bối cảnh: "{topic_input}".

YÊU CẦU:
- Viết 3 đến 4 lượt đối thoại qua lại.
- Giọng văn: Đanh đá, xấc láo, tấu hài, chửi xéo kiểu giang hồ thôn xóm nhưng lồng bằng giọng nghiêm túc.
- Gán đúng từ khóa tiếng Anh tìm video hành động thực tế của mèo trên Pexels (ví dụ: `cat angry hissing`, `cat staring close up`, `cats fighting face to face`, `cat opening mouth meowing`).

Trả về DUY NHẤT một JSON hợp lệ dạng danh sách:
[
  {{"speaker": "Mèo A", "line": "Mày nhìn cái gì? Mày ngon bước qua vạch này coi tao có cào rách mặt mày không?", "query_en": "angry cat staring face to face"}},
  {{"speaker": "Mèo B", "line": "Bớt sủa lại đi con mèo mướp! Tô pate này là của tao, động vào một miếng là biết tay!", "query_en": "cat opening mouth hissing angry"}},
  {{"speaker": "Mèo A", "line": "Được lắm, hôm nay một mất một còn với mày luôn!", "query_en": "two cats fighting close up"}}
]"""

            resp = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.6)
            match = re.search(r'\[.*\]', resp.choices[0].message.content, re.DOTALL)
            dialogues = json.loads(match.group(0)) if match else []

            if not dialogues:
                dialogues = [
                    {"speaker": "Mèo 1", "line": "Mày nhìn cái giống gì? Thích ăn cào không?", "query_en": "angry cat staring close up"},
                    {"speaker": "Mèo 2", "line": "Ngon nhào vô, tao sợ mày chắc?", "query_en": "cat hissing fighting"}
                ]

            # 2. Tạo Voice Nam Minh trầm nghiêm túc cho từng câu
            status.update(label="🎙️ 2/4: Tạo giọng đọc Nam Minh nghiêm túc cho cuộc cãi vã...")
            scenes = []
            for i, item in enumerate(dialogues):
                aud_p = os.path.join(workdir, f"v_{i:02d}.mp3")
                asyncio.run(generate_voice_nam(item["line"], aud_p))
                dur = get_audio_duration(aud_p)
                scenes.append({
                    "line": item["line"],
                    "query": item["query_en"],
                    "audio": aud_p,
                    "dur": max(2.5, dur + 0.4) # Đệm thêm 0.4s để nhịp cãi nhau kịch tính
                })

            # 3. Tải Video đúng hành vi mèo và ghép tiếng
            status.update(label="🎬 3/4: Tải video mèo gườm nhau / xù lông và khớp voice...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = get_pexels_video(sc["query"], pexels_key, orient_tag, used_ids)
                    if not v_url:
                        v_url = get_pexels_video("angry cat face fighting", pexels_key, orient_tag, used_ids)

                    raw_v = os.path.join(workdir, f"r_{idx:02d}.mp4")
                    cut_v = os.path.join(workdir, f"c_{idx:02d}.mp4")
                    download_file_safe(v_url, raw_v)

                    # Cắt clip chuẩn kích thước, không chèn chữ drawtext
                    cut_clip_clean(raw_v, cut_v, sc["dur"], is_port)
                    if os.path.exists(raw_v):
                        os.remove(raw_v)

                    # Ghép thoại vào clip
                    synced_v = os.path.join(workdir, f"synced_{idx:02d}.mp4")
                    cmd_sync = [
                        FFMPEG_EXE, "-y", "-i", cut_v, "-i", sc["audio"],
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", synced_v
                    ]
                    subprocess.run(cmd_sync, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")

            # 4. Ghép hoàn thiện + Lồng nhạc nền kịch tính
            status.update(label="⚡ 4/4: Đang hòa âm và xuất file Master...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "cat_battle_master.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_path = os.path.join(workdir, "drama_bgm.mp3")
            has_bgm = (bgm_volume > 0) and download_file_safe(DRAMA_BGM_URL, bgm_path)
            vol_float = bgm_volume / 100.0

            if has_bgm:
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
            else:
                shutil.copy(temp_merged, final_mp4)

            status.update(label="🎉 Video lồng tiếng đối đầu đã hoàn thành!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label="⬇️ Tải Video Hoàn Chỉnh Về Máy",
                data=v_bytes,
                file_name=f"cat_beef_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
