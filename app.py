# -*- coding: utf-8 -*-
import os
import re
import json
import math
import shutil
import random
import hashlib
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

# ==============================================================================
# CẤU HÌNH & KHỞI TẠO
# ==============================================================================
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFPROBE_EXE = shutil.which("ffprobe") or "ffprobe"

st.set_page_config(page_title="Cute Animals POV Studio Pro", page_icon="🐾", layout="centered")

FPS = 30
CLIP_DURATION = 5.0
LLM_MODEL = "openai/gpt-oss-120b"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
CUTE_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

VOICE_GAIN = 1.00
ORIGINAL_GAIN = 0.35
SFX_GAIN = 0.40

if "global_used_ids" not in st.session_state:
    st.session_state.global_used_ids = set()
if "global_used_content" not in st.session_state:
    st.session_state.global_used_content = set()

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets["PEXELS_API_KEY"]
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
    freesound_key = st.secrets.get("FREESOUND_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình GROQ_API_KEY hoặc PEXELS_API_KEY trong Streamlit Secrets!")
    st.stop()

st.title("🐾 Cute Animals POV Studio Pro")
st.caption("AI phân tích hành vi thú cưng • B-roll không trùng lặp • Hòa âm tiếng kêu thực tế + Voice + BGM")

# ==============================================================================
# GIAO DIỆN ĐIỀU KHIỂN
# ==============================================================================
topic_genre = st.text_area(
    "Nhập chủ đề về loài động vật muốn làm video:",
    value="Những chú mèo con và cún con tinh nghịch vui đùa đuổi bắt trong khu vườn đầy hoa nắng",
    height=80
)

col_t1, col_t2 = st.columns(2)
with col_t1:
    animal_focus = st.selectbox(
        "Nhóm thú cưng / Động vật ưu tiên:",
        [
            "Mèo con & Chó con (Puppies & Kittens)",
            "Động vật hoang dã đáng yêu (Gấu trúc, Rái cá, Koala)",
            "Thú nhỏ ngộ nghĩnh (Thỏ con, Chuột Hamster, Vịt con)",
            "Tự do (Theo mô tả nhập ở trên)"
        ]
    )
with col_t2:
    total_sec_input = st.number_input("Tổng thời lượng (giây):", min_value=10, max_value=300, value=25, step=5)

calc_clips = math.ceil(total_sec_input / CLIP_DURATION)
st.info(f"💡 Hệ thống sẽ sản xuất **{calc_clips} phân cảnh** × {CLIP_DURATION}s = **{calc_clips * CLIP_DURATION:.0f}s**.")

col_v1, col_v2 = st.columns(2)
with col_v1:
    voice_choice = st.selectbox(
        "Giọng đọc thuyết minh:",
        [
            "Tiếng Anh: Ana (Hoạt hình tươi vui, trẻ em thích)",
            "Tiếng Anh: Christopher (Tài liệu chuẩn mực Discovery)",
            "Tiếng Anh: Guy (Nam kể chuyện lôi cuốn)",
            "Tiếng Việt: Hoài My (Nữ truyền cảm, ấm áp)",
            "Tiếng Việt: Nam Minh (Nam thời sự tài liệu)"
        ]
    )
with col_v2:
    orientation_opt = st.selectbox(
        "Khung hình xuất bản:",
        ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"]
    )

col_a1, col_a2 = st.columns(2)
with col_a1:
    bgm_volume = st.slider("Âm lượng nhạc nền ngầm (%):", 0, 40, 15, 2)
with col_a2:
    keep_original_audio = st.checkbox("Giữ tiếng kêu gốc từ video tải về", value=True)

# ==============================================================================
# HÀM XỬ LÝ KỸ THUẬT & TRÁNH CRASH
# ==============================================================================
def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=20) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                return os.path.exists(dest) and os.path.getsize(dest) > 10000
    except Exception:
        pass
    return False

def has_audio_stream(filepath: str) -> bool:
    try:
        r = subprocess.run(
            [FFPROBE_EXE, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=10
        )
        return "audio" in r.stdout.strip()
    except Exception:
        return False

def video_content_hash(filepath: str, num_frames: int = 6) -> str:
    hasher = hashlib.md5()
    try:
        cmd = [
            FFMPEG_EXE, "-i", filepath,
            "-vf", f"select='lt(n,{num_frames})',scale=64:36",
            "-vsync", "vfr", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out, _ = proc.communicate(timeout=10)
        hasher.update(out or b"")
    except Exception:
        hasher.update(str(random.random()).encode())
    return hasher.hexdigest()

def get_video_duration(path: str) -> float:
    try:
        r = subprocess.run(
            [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=8
        )
        return float(r.stdout.strip() or 10.0)
    except Exception:
        return 10.0

async def generate_voice(text: str, out_audio: str, voice_option: str):
    if "Ana" in voice_option:
        v_code, rate = "en-US-AnaNeural", "+2%"
    elif "Christopher" in voice_option:
        v_code, rate = "en-US-ChristopherNeural", "+0%"
    elif "Guy" in voice_option:
        v_code, rate = "en-US-GuyNeural", "+2%"
    elif "Hoài My" in voice_option:
        v_code, rate = "vi-VN-HoaiMyNeural", "+2%"
    else:
        v_code, rate = "vi-VN-NamMinhNeural", "+2%"
    comm = edge_tts.Communicate(text, voice=v_code, rate=rate)
    await comm.save(out_audio)

# ==============================================================================
# AI GENERATION: ĐỘC QUYỀN ĐỘNG VẬT & JSON OBJECT AN TOÀN
# ==============================================================================
def ai_generate_animal_queries(client, topic: str, focus_mode: str, n_queries: int):
    prompt = f"""You are a professional wildlife and cute pet documentary footage researcher.
Topic: "{topic}".
Animal Focus: "{focus_mode}".

TASK: Generate exactly {n_queries} UNIQUE, distinct visual queries for searching stock video clips of cute animals on Pexels/Pixabay.

RULES:
- Focus 100% on CUTE ANIMALS (cats, kittens, dogs, puppies, pandas, otters, bunnies, ducklings).
- Strictly AVOID landscape-only words like "forest", "empty meadow", "sunset", "autumn leaves".
- Each query must have specific actions: "eating bamboo", "playing with ball", "running happily", "close up big eyes", "sleeping curled up".
- Provide `fallback` (2 simple words identifying the animal).
- Provide `sfx` (sound keyword: "kitten meow", "puppy bark", "duck quack", "cat purr").

RETURN ONLY A VALID JSON OBJECT WITH A "queries" KEY:
{{
  "queries": [
    {{"query": "cute kitten playing with ball", "fallback": "cute kitten", "sfx": "kitten meow"}},
    {{"query": "golden retriever puppy running grass", "fallback": "cute puppy", "sfx": "puppy barking"}},
    {{"query": "baby panda eating bamboo close up", "fallback": "baby panda", "sfx": "animal eating"}}
  ]
}}"""

    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        data = json.loads(resp.choices[0].message.content.strip())
        query_list = data.get("queries", [])

        cleaned = []
        for item in query_list:
            if not isinstance(item, dict):
                continue
            q = str(item.get("query", "")).strip()
            fb = str(item.get("fallback", q)).strip() or q
            sfx = str(item.get("sfx", "")).strip() or "cute animal sound"
            if q:
                cleaned.append({"query": q, "fallback": fb, "sfx": sfx})
        if cleaned:
            return cleaned
    except Exception:
        pass

    fallback_defaults = [
        {"query": "cute kitten close up eyes", "fallback": "kitten cat", "sfx": "kitten meow"},
        {"query": "playful puppy dog running", "fallback": "cute puppy", "sfx": "puppy barking"},
        {"query": "baby panda playing bamboo", "fallback": "baby panda", "sfx": "panda sound"},
        {"query": "fluffy bunny rabbit eating grass", "fallback": "cute bunny", "sfx": "rabbit eating"},
        {"query": "cute sea otter swimming water", "fallback": "sea otter", "sfx": "water splash"}
    ]
    return fallback_defaults

# ==============================================================================
# CÀO B-ROLL & ÂM THANH SFX
# ==============================================================================
def fetch_from_pexels(query: str, p_key: str, used_ids: set):
    headers = {"Authorization": p_key.strip()}
    pages = [random.randint(1, 4), random.randint(1, 2)]
    for page in pages:
        try:
            url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=15&page={page}"
            r = requests.get(url, headers=headers, timeout=8)
            if not (r.ok and r.json().get("videos")):
                continue
            videos = r.json()["videos"]
            random.shuffle(videos)
            for v in videos:
                v_id = f"pexels_{v.get('id')}"
                if v_id in used_ids:
                    continue
                files = v.get("video_files", [])
                hd = [f for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"]
                target = hd[0].get("link") if hd else (files[0].get("link") if files else None)
                if target:
                    used_ids.add(v_id)
                    return target
        except Exception:
            continue
    return None

def fetch_from_pixabay(query: str, pb_key: str, used_ids: set):
    if not pb_key or not pb_key.strip():
        return None
    for page in [random.randint(1, 3), 1]:
        try:
            url = f"{PIXABAY_VIDEO_URL}?key={pb_key.strip()}&q={urllib.parse.quote(query)}&per_page=15&page={page}&safesearch=true"
            r = requests.get(url, timeout=8)
            if not (r.ok and r.json().get("hits")):
                continue
            hits = r.json()["hits"]
            random.shuffle(hits)
            for v in hits:
                v_id = f"pixabay_{v.get('id')}"
                if v_id in used_ids:
                    continue
                vf = v.get("videos", {})
                target = vf.get("large") or vf.get("medium") or vf.get("small")
                if target and target.get("url"):
                    used_ids.add(v_id)
                    return target["url"]
        except Exception:
            continue
    return None

def get_broll_clip(scene_query: dict, p_key: str, pb_key: str, used_ids: set):
    q = scene_query["query"]
    fb = scene_query["fallback"]

    for attempt in [q, f"cute {fb}", fb]:
        url = fetch_from_pexels(attempt, p_key, used_ids)
        if url:
            return url
        if pb_key:
            url = fetch_from_pixabay(attempt, pb_key, used_ids)
            if url:
                return url
    return None

def fetch_animal_sfx(sfx_query: str, f_key: str, dest: str) -> bool:
    if not f_key or not f_key.strip() or not sfx_query:
        return False
    try:
        params = {
            "query": sfx_query,
            "token": f_key.strip(),
            "fields": "id,name,previews,duration",
            "filter": "duration:[0.5 TO 5.0]",
            "page_size": 4
        }
        r = requests.get(FREESOUND_SEARCH_URL, params=params, timeout=8)
        if r.ok and r.json().get("results"):
            results = r.json()["results"]
            random.shuffle(results)
            for s in results:
                preview = s.get("previews", {}).get("preview-hq-mp3")
                if preview and download_file_safe(preview, dest):
                    return True
    except Exception:
        pass
    return False

# ==============================================================================
# QUY TRÌNH DỰNG CẢNH 5s & HÒA ÂM CHUẨN XÁC
# ==============================================================================
def cut_clip_exact_5s(raw_p: str, out_p: str, is_port: bool, keep_audio: bool):
    res_f = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30"
        if is_port else
        "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30"
    )
    raw_dur = get_video_duration(raw_p)
    start_sec = 0.5
    if raw_dur > (CLIP_DURATION + 2.0):
        start_sec = random.uniform(1.0, min(3.5, raw_dur - CLIP_DURATION - 0.5))

    base_cmd = [
        FFMPEG_EXE, "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", raw_p,
        "-t", f"{CLIP_DURATION:.3f}",
        "-vf", res_f
    ]

    has_audio = has_audio_stream(raw_p)
    if keep_audio and has_audio:
        base_cmd += [
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-af", "afade=t=in:d=0.2,afade=t=out:st=4.8:d=0.2",
            out_p
        ]
    else:
        base_cmd += ["-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", out_p]

    subprocess.run(base_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return has_audio_stream(out_p) if keep_audio else False

def build_scene_audio(voice_path: str, orig_clip: str, sfx_path: str, out_audio: str):
    inputs = ["-i", voice_path]
    filters = [f"[0:a]volume={VOICE_GAIN},apad=pad_dur={CLIP_DURATION}[v]"]
    amix_inputs = ["[v]"]
    idx = 1

    if orig_clip and os.path.exists(orig_clip) and has_audio_stream(orig_clip):
        inputs += ["-i", orig_clip]
        filters.append(f"[{idx}:a]volume={ORIGINAL_GAIN},apad=pad_dur={CLIP_DURATION}[o]")
        amix_inputs.append("[o]")
        idx += 1

    if sfx_path and os.path.exists(sfx_path):
        inputs += ["-i", sfx_path]
        filters.append(
            f"[{idx}:a]volume={SFX_GAIN},adelay=200|200,"
            f"afade=t=in:d=0.2,afade=t=out:st=4.6:d=0.4,"
            f"apad=pad_dur={CLIP_DURATION}[s]"
        )
        amix_inputs.append("[s]")
        idx += 1

    filter_complex = (
        ";".join(filters) + ";" +
        "".join(amix_inputs) +
        f"amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=0,"
        f"atrim=0:{CLIP_DURATION},loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )

    cmd = [
        FFMPEG_EXE, "-y"
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        out_audio
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE SẢN XUẤT CHÍNH
# ==============================================================================
if st.button("🚀 Bắt Đầu Tạo Video Động Vật Dễ Thương", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập chủ đề động vật.")
    else:
        status = st.status(f"Đang tiến hành dựng video {calc_clips} phân cảnh...", expanded=True)
        workdir = tempfile.mkdtemp(prefix="cute_animals_")
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in voice_choice
        total_duration_video = calc_clips * CLIP_DURATION

        used_ids = st.session_state.global_used_ids
        used_content = st.session_state.global_used_content

        try:
            client = Groq(api_key=groq_key.strip())

            # 1. AI sinh kịch bản câu chuyện & Query B-roll chuyên biệt
            status.update(label="🧠 1/5: AI phân tích hành vi đáng yêu & sinh query B-roll...")
            n_queries_needed = max(calc_clips * 2, 10)
            dynamic_queries = ai_generate_animal_queries(client, topic_genre.strip(), animal_focus, n_queries_needed)
            random.shuffle(dynamic_queries)

            # AI viết kịch bản dẫn chuyện từng cảnh
            BATCH_SIZE = 6
            total_batches = math.ceil(calc_clips / BATCH_SIZE)
            parsed_lines = []

            for _ in range(total_batches):
                needed = min(BATCH_SIZE, calc_clips - len(parsed_lines))
                lang = "English" if is_en else "Vietnamese"
                prompt = f"""You are a warm, charming pet documentary narrator.
Topic: "{topic_genre}".
Language: {lang}.
Task: Write {needed} consecutive, adorable story sentences about these animals.
Each sentence must be short, under 11 words (~3 seconds read).
Return ONLY a JSON object:
{{"story": ["Sentence 1...", "Sentence 2..."]}}"""

                resp = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    response_format={"type": "json_object"}
                )
                try:
                    res_data = json.loads(resp.choices[0].message.content.strip())
                    batch = res_data.get("story", [])
                except Exception:
                    batch = []

                if not batch:
                    batch = [f"Khoảnh khắc đáng yêu ngập tràn niềm vui ở phân cảnh thứ {len(parsed_lines) + i + 1}." for i in range(needed)]

                for line in batch:
                    parsed_lines.append(str(line).strip())
                    if len(parsed_lines) >= calc_clips:
                        break

            scenes = []
            for idx in range(calc_clips):
                q = dynamic_queries[idx % len(dynamic_queries)]
                scenes.append({
                    "speech_text": parsed_lines[idx],
                    "query": q["query"],
                    "fallback": q["fallback"],
                    "sfx_query": q["sfx"]
                })

            # 2. Sinh giọng đọc Edge-TTS
            status.update(label="🎙️ 2/5: Tạo giọng đọc thuyết minh ấm áp...")
            for idx, sc in enumerate(scenes):
                v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
                asyncio.run(generate_voice(sc["speech_text"], v_file, voice_choice))
                sc["voice"] = v_file

            # 3. Tải Footage & Bù đắp SFX tiếng kêu
            status.update(label="🎬 3/5: Tải hình ảnh động vật dễ thương & lọc trùng...")
            for idx, sc in enumerate(scenes):
                v_url = get_broll_clip(sc, pexels_key, pixabay_key, used_ids)
                if not v_url:
                    fallback_q = {"query": "cute pet kitten puppy", "fallback": "cute animal"}
                    v_url = get_broll_clip(fallback_q, pexels_key, pixabay_key, used_ids)

                raw_v = os.path.join(workdir, f"raw_{idx:03d}.mp4")
                cut_v = os.path.join(workdir, f"cut_{idx:03d}.mp4")

                download_file_safe(v_url, raw_v)

                # Chống trùng lặp khung hình
                ch = video_content_hash(raw_v)
                if ch in used_content:
                    os.remove(raw_v)
                    v_url2 = get_broll_clip({"query": "playful cute animals", "fallback": "cute pets"}, pexels_key, pixabay_key, used_ids)
                    if v_url2:
                        download_file_safe(v_url2, raw_v)
                        ch = video_content_hash(raw_v)
                used_content.add(ch)

                has_orig = cut_clip_exact_5s(raw_v, cut_v, is_port, keep_original_audio)
                sc["clip"] = cut_v
                sc["has_orig"] = has_orig
                if os.path.exists(raw_v):
                    os.remove(raw_v)

                # Tải hiệu ứng tiếng kêu từ Freesound
                sfx_path = os.path.join(workdir, f"sfx_{idx:03d}.mp3")
                if freesound_key:
                    fetch_animal_sfx(sc["sfx_query"], freesound_key, sfx_path)
                sc["sfx"] = sfx_path if os.path.exists(sfx_path) else None

            # 4. Trộn Audio 3 lớp & Đóng gói từng cảnh 5s
            status.update(label="🎚️ 4/5: Hòa âm tiếng kêu + Voice + khử lệch timebase...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    scene_audio = os.path.join(workdir, f"a_{idx:03d}.m4a")
                    build_scene_audio(
                        sc["voice"],
                        sc["clip"] if sc["has_orig"] else None,
                        sc["sfx"],
                        scene_audio
                    )
                    synced_v = os.path.join(workdir, f"s_{idx:03d}.mp4")
                    # Thêm cờ chống lệch Timebase PTS khi nối file
                    subprocess.run([
                        FFMPEG_EXE, "-y",
                        "-i", sc["clip"], "-i", scene_audio,
                        "-t", f"{CLIP_DURATION:.3f}",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-avoid_negative_ts", "make_zero", "-fflags", "+genpts",
                        synced_v
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")

            # 5. Nối chuỗi & Master Nhạc Nền EBU R128
            status.update(label="⚡ 5/5: Nối Master và cân bằng chuẩn âm thanh EBU R128...", state="running")
            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "cute_animals_master.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_raw = os.path.join(workdir, "bgm.mp3")
            has_bgm = (bgm_volume > 0) and download_file_safe(CUTE_BGM_URL, bgm_raw)

            if has_bgm:
                bgm_gain = bgm_volume / 100.0
                subprocess.run([
                    FFMPEG_EXE, "-y",
                    "-i", temp_merged,
                    "-stream_loop", "-1", "-i", bgm_raw,
                    "-filter_complex",
                    f"[0:a]volume=1.0[a0];[1:a]volume={bgm_gain:.3f}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2,"
                    f"loudnorm=I=-14:TP=-1.5:LRA=11[aout]",
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", final_mp4
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                subprocess.run([
                    FFMPEG_EXE, "-y", "-i", temp_merged,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    final_mp4
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            status.update(label=f"🎉 Hoàn thành video động vật dễ thương {calc_clips * 5}s!", state="complete")

            with open(final_mp4, "rb") as f:
                v_bytes = f.read()

            st.video(v_bytes)
            st.download_button(
                label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
                data=v_bytes,
                file_name=f"cute_animals_{calc_clips * 5}s_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
