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

st.set_page_config(page_title="Studio POV Story Master Pro", page_icon="⚡", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"

AMBIENT_SFX = {
    "storm": "https://upload.wikimedia.org/wikipedia/commons/2/27/Thunderstorm_sound.ogg",
    "nature": "https://upload.wikimedia.org/wikipedia/commons/e/ea/Bird_songs_in_forest.ogg",
    "bgm": "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"
}

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong Secrets của Streamlit Cloud!")
    st.stop()

st.title("⚡ Studio POV Story Master (Bản Sửa Triệt Để Lỗi 254)")
st.caption("Xử lý Stream tách biệt • Giữ trọn âm thanh gốc/môi trường • Không crash FFmpeg")

SUBJECT_POOLS = {
    "Thảm họa Tàu thuyền / Bão biển / Sóng thần": [
        ("cargo ship heavy storm waves", "ship storm"),
        ("massive ocean storm wave", "huge waves"),
        ("fishing boat dark rough sea", "boat sea"),
        ("lightning storm over dark ocean", "lightning ocean"),
        ("rough sea waves crashing", "storm waves"),
        ("ship navigating rough waters", "ship sea")
    ],
    "Động vật / Thú cưng dễ thương": [
        ("cute golden retriever puppy barking", "puppy dog"),
        ("baby panda climbing bamboo", "baby panda"),
        ("little kitten meowing playing", "kitten cat"),
        ("fluffy bunny rabbit eating", "cute bunny"),
        ("sea otter floating water", "sea otter"),
        ("cute duckling swimming", "duckling")
    ],
    "Siêu xe / Tốc độ / Phố đêm": [
        ("supercar drifting night city engine", "drift car"),
        ("sports car speeding highway", "sports car"),
        ("neon cyberpunk race car revving", "supercar night")
    ]
}

topic_genre = st.text_area(
    "Nhập chủ đề kịch bản chi tiết:",
    value="Một con tàu đánh cá gặp cơn bão lớn giữa đại dương đen kịt, sóng thần cuồn cuộn và cuộc chiến sinh tồn của các thủy thủ",
    height=80
)

col_t1, col_t2 = st.columns(2)
with col_t1:
    selected_category = st.selectbox(
        "Khóa nhóm chủ thể:",
        list(SUBJECT_POOLS.keys()) + ["Tự do phân tích theo chủ đề nhập ở trên"]
    )
with col_t2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=300, value=25, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ chia kịch bản thành **{calc_clips} phân cảnh** (mỗi cảnh đúng 5.0 giây).")

col_v1, col_v2 = st.columns(2)
with col_v1:
    voice_choice = st.selectbox(
        "Ngôn ngữ & Giọng đọc mục tiêu:",
        [
            "Tiếng Anh: Christopher (Giọng tài liệu trầm khàn chuẩn Tây)",
            "Tiếng Anh: Ana (Giọng hoạt hình / động vật vui vẻ)",
            "Tiếng Anh: Guy (Nam kể chuyện cuốn hút)",
            "Tiếng Việt: Nam Minh (Nam thời sự / tài liệu trầm)",
            "Tiếng Việt: Hoài My (Nữ truyền cảm)"
        ]
    )
with col_v2:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube)", "portrait (Dọc 9:16 Shorts/TikTok)"])

col_s1, col_s2 = st.columns(2)
with col_s1:
    ambient_volume = st.slider("Âm lượng tiếng gốc / Môi trường (%):", min_value=10, max_value=80, value=40, step=5)
with col_s2:
    bgm_volume = st.slider("Âm lượng nhạc nền ngầm (%):", min_value=0, max_value=40, value=15, step=5)

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
    elif "Ana" in voice_option:
        v_code = "en-US-AnaNeural"
    elif "Guy" in voice_option:
        v_code = "en-US-GuyNeural"
    elif "Nam Minh" in voice_option:
        v_code = "vi-VN-NamMinhNeural"
    else:
        v_code = "vi-VN-HoaiMyNeural"

    comm = edge_tts.Communicate(text, voice=v_code, rate="+4%")
    await comm.save(out_audio)

def fetch_from_pexels(query: str, p_key: str, used_hashes: set) -> str:
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
    if not pb_key or not pb_key.strip():
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

def get_broll_clip(query: str, fallback_query: str, p_key: str, pb_key: str, used_hashes: set) -> str:
    clip = fetch_from_pexels(query, p_key, used_hashes)
    if not clip and pb_key:
        clip = fetch_from_pixabay(query, pb_key, used_hashes)
    if not clip:
        clip = fetch_from_pexels(fallback_query, p_key, used_hashes)
    if not clip and pb_key:
        clip = fetch_from_pixabay(fallback_query, pb_key, used_hashes)
    return clip

def process_single_scene_bulletproof(raw_v: str, voice_a: str, amb_a: str, out_p: str, is_port: bool, amb_vol: float):
    """
    Quy trình xử lý phân cảnh độc lập 100% không bao giờ dính lỗi 254:
    1. Cắt video sang file tạm (chỉ thuần hình ảnh, scale/crop, fps 30).
    2. Chuẩn hóa audio: lấy tiếng gốc nếu có, hoặc lấy tiếng môi trường ambient.
    3. Hòa âm Voice + Ambient thành 1 luồng duy nhất đúng 5.0 giây.
    4. Ghép Video + Audio thành file cảnh hoàn chỉnh.
    """
    res_f = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" if is_port else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"
    
    # 1. Cắt video thuần túy
    tmp_dir = os.path.dirname(out_p)
    temp_v = os.path.join(tmp_dir, f"tmp_v_{os.path.basename(out_p)}")
    cmd_v = [
        FFMPEG_EXE, "-y",
        "-i", raw_v,
        "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f,
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        temp_v
    ]
    subprocess.run(cmd_v, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 2. Xác định nguồn âm thanh môi trường
    has_audio = check_video_has_audio(raw_v)
    source_ambient = raw_v if has_audio else amb_a

    # 3. Hòa âm (Voice 1.0 + Môi trường/Tiếng gốc amb_vol) đúng 5s
    temp_a = os.path.join(tmp_dir, f"tmp_a_{os.path.basename(out_p)}.aac")
    cmd_a = [
        FFMPEG_EXE, "-y",
        "-i", source_ambient,
        "-i", voice_a,
        "-filter_complex",
        f"[0:a]volume={amb_vol:.2f},afade=t=in:ss=0:d=0.2,afade=t=out:st=4.8:d=0.2[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
        "-map", "[aout]",
        "-t", f"{CLIP_DURATION:.3f}",
        "-c:a", "aac", "-b:a", "192k",
        temp_a
    ]
    subprocess.run(cmd_a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. Đóng gói thành phẩm 1 cảnh
    cmd_mux = [
        FFMPEG_EXE, "-y",
        "-i", temp_v,
        "-i", temp_a,
        "-c", "copy",
        out_p
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Dọn file đệm
    for p in [temp_v, temp_a]:
        if os.path.exists(p):
            os.remove(p)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Sản Xuất Master Hoàn Hảo", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập chủ đề kịch bản.")
    else:
        status = st.status(f"Đang chuẩn bị sản xuất {calc_clips} phân cảnh...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="master_safe_")
        used_hashes = set()
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in voice_choice

        try:
            client = Groq(api_key=groq_key.strip())

            # Chuẩn bị track âm thanh môi trường
            ambient_file = os.path.join(workdir, "ambient.ogg")
            amb_url = AMBIENT_SFX["storm"] if any(w in topic_genre.lower() for w in ["bão", "tàu", "sóng", "ocean", "sea", "storm"]) else AMBIENT_SFX["nature"]
            download_file_safe(amb_url, ambient_file)

            # 1. Sinh kịch bản Batch
            status.update(label=f"🧠 1/4: {LLM_MODEL} đang sinh kịch bản...")
            if selected_category in SUBJECT_POOLS:
                pool = SUBJECT_POOLS[selected_category]
            else:
                pool = [
                    (f"{topic_genre} action shot", topic_genre),
                    (f"{topic_genre} close up", topic_genre)
                ]

            parsed_scenes = []
            BATCH_SIZE = 6
            total_batches = math.ceil(calc_clips / BATCH_SIZE)

            for b in range(total_batches):
                needed = min(BATCH_SIZE, calc_clips - len(parsed_scenes))
                prompt = f"""You are a documentary scriptwriter.
Topic: "{topic_genre}".
Language: {"English" if is_en else "Vietnamese"}.
Task: Write {needed} consecutive story sentences. Each sentence must be under 12 words.

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
                    batch_lines = [f"Khoảnh khắc chân thực đầy kịch tính ở phân cảnh {len(parsed_scenes) + i + 1}." for i in range(needed)]

                for line in batch_lines:
                    idx = len(parsed_scenes)
                    q_tuple = pool[idx % len(pool)]
                    parsed_scenes.append({
                        "speech_text": str(line).strip(),
                        "query_en": q_tuple[0],
                        "fallback_en": q_tuple[1]
                    })
                    if len(parsed_scenes) >= calc_clips:
                        break

            # 2. Tạo Voice
            status.update(label="🎙️ 2/4: Tạo giọng đọc thuyết minh...")
            scenes = []
            for idx, item in enumerate(parsed_scenes):
                v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
                asyncio.run(generate_voice(item["speech_text"], v_file, voice_choice))
                scenes.append({
                    "query": item["query_en"],
                    "fallback": item["fallback_en"],
                    "audio": v_file,
                    "dur": CLIP_DURATION
                })

            # 3. Tải B-roll và xử lý từng cảnh an toàn tuyệt đối
            status.update(label="🎬 3/4: Tải B-roll & đóng gói phân cảnh...")
            clips_txt = os.path.join(workdir, "clips.txt")
            amb_vol_float = ambient_volume / 100.0

            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    v_url = get_broll_clip(sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes)
                    if not v_url:
                        v_url = get_broll_clip(pool[0][0], pool[0][1], pexels_key, pixabay_key, used_hashes)

                    raw_v = os.path.join(workdir, f"r_{idx:03d}.mp4")
                    scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")
                    download_file_safe(v_url, raw_v)

                    process_single_scene_bulletproof(raw_v, sc["audio"], ambient_file, scene_v, is_port, amb_vol_float)
                    
                    if os.path.exists(raw_v):
                        os.remove(raw_v)

                    f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

            # 4. Xuất Master + Lồng BGM
            status.update(label="⚡ 4/4: Nối các phân cảnh và hoàn tất Master...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "master_story_pro.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_path = os.path.join(workdir, "bgm.mp3")
            has_bgm = (bgm_volume > 0) and download_file_safe(AMBIENT_SFX["bgm"], bgm_path)
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

            status.update(label=f"🎉 Hoàn thành video {calc_clips * 5} giây hoàn hảo!", state="complete")

            with open(final_mp4, "rb") as out_f:
                v_bytes = out_f.read()

            st.video(v_bytes)
            st.download_button(
                label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
                data=v_bytes,
                file_name=f"story_{calc_clips * 5}s_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
