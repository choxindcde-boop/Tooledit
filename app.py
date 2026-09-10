Xem bản này chất k . # -*- coding: utf-8 -*-
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
# CẤU HÌNH
# ==============================================================================
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFPROBE_EXE = shutil.which("ffprobe") or "ffprobe"

st.set_page_config(page_title="Cute Animals POV Studio Pro", page_icon="🐾", layout="centered")

FPS = 30
MIN_SCENE_DUR = 2.5
MAX_SCENE_DUR = 10.0
VOICE_PAD = 0.55
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
CUTE_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

VOICE_GAIN = 1.00
ORIGINAL_GAIN = 0.30
SFX_GAIN = 0.40
TIMESCALE = 15360

# Danh sách model theo ảnh Groq Console của bạn
LLM_MODEL_OPTIONS = [
    ("openai/gpt-oss-120b",         "⭐ GPT-OSS 120B — Mạnh nhất, JSON chuẩn (khuyên dùng)"),
    ("llama-3.3-70b-versatile",     "Llama 3.3 70B Versatile — Đa năng, ổn định"),
    ("openai/gpt-oss-20b",          "GPT-OSS 20B — Nhẹ & nhanh hơn"),
    ("qwen/qwen3-32b",              "Qwen 3 32B — Thay thế tốt"),
    ("groq/compound",               "Groq Compound — Có tool/web"),
    ("groq/compound-mini",          "Groq Compound Mini — Nhẹ"),
    ("llama-3.1-8b-instant",        "Llama 3.1 8B Instant — Siêu nhanh"),
]

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
st.caption("Pipeline B-roll trước → AI đọc query thực tế → viết voice khớp hình → ghép master")

# ==============================================================================
# GIAO DIỆN
# ==============================================================================
model_labels = [m[1] for m in LLM_MODEL_OPTIONS]
model_label_map = {m[1]: m[0] for m in LLM_MODEL_OPTIONS}
selected_model_label = st.selectbox(
    "🧠 Model AI (Groq):", model_labels, index=0,
    help="Chọn model sinh query B-roll & viết narration"
)
LLM_MODEL = model_label_map[selected_model_label]

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
    total_sec_input = st.number_input("Tổng thời lượng mục tiêu (giây):", min_value=10, max_value=300, value=25, step=5)

approx_clips = max(3, math.ceil(total_sec_input / 4.5))
st.info(f"💡 Sẽ tải ~**{approx_clips} clip B-roll**, AI viết narration khớp hình, mỗi cảnh dài theo voice thực (2.5–10s).")

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
# HELPERS
# ==============================================================================
def download_file_safe(url: str, dest: str, min_size: int = 10000) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=25) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                return os.path.exists(dest) and os.path.getsize(dest) > min_size
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

def get_media_duration(path: str, default: float = 3.0) -> float:
    try:
        r = subprocess.run(
            [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=8
        )
        val = float((r.stdout or "").strip() or default)
        return val if val > 0 else default
    except Exception:
        return default

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

async def _generate_voice_async(text: str, out_audio: str, voice_option: str):
    if "Ana" in voice_option:
        v_code, rate = "en-US-AnaNeural", "+3%"
    elif "Christopher" in voice_option:
        v_code, rate = "en-US-ChristopherNeural", "+0%"
    elif "Guy" in voice_option:
        v_code, rate = "en-US-GuyNeural", "+2%"
    elif "Hoài My" in voice_option:
        v_code, rate = "vi-VN-HoaiMyNeural", "+4%"
    else:
        v_code, rate = "vi-VN-NamMinhNeural", "+4%"
    comm = edge_tts.Communicate(text, voice=v_code, rate=rate)
    await comm.save(out_audio)

def generate_voice(text: str, out_audio: str, voice_option: str):
    asyncio.run(_generate_voice_async(text, out_audio, voice_option))

def _safe_json_call(client, model, prompt, temperature=0.6, max_retries=2):
    """Gọi LLM trả về JSON, có fallback nếu model không hỗ trợ response_format."""
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            return json.loads(resp.choices[0].message.content.strip())
        except Exception:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You return ONLY valid JSON, no markdown fences."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                )
                txt = resp.choices[0].message.content.strip()
                txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.MULTILINE)
                return json.loads(txt)
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.0)
    return {}

# ==============================================================================
# AI CALL #1: SINH QUERY B-ROLL (chưa có narration)
# ==============================================================================
def ai_generate_broll_queries(client, model, topic: str, focus_mode: str, n_queries: int):
    prompt = f"""You are a professional cute-pet & wildlife stock footage researcher.
Topic: "{topic}"
Animal focus: "{focus_mode}"

TASK: Generate EXACTLY {n_queries} DIVERSE stock-video search queries.
These will be used to download cute animal clips from Pexels/Pixabay.

RULES:
- 100% focus on CUTE ANIMALS (kittens, puppies, pandas, otters, bunnies, ducklings, hamsters).
- Each query = English, VERY specific: animal + action + setting. Example: "golden retriever puppy running grass sunset".
- Each query must be DIFFERENT from all others (different action, angle, or setting).
- Strictly AVOID landscape-only terms like "forest", "empty meadow", "autumn leaves".
- Provide `fallback` = 2-3 simple words identifying the animal.
- Provide `sfx` = short English sound keyword matching the animal ("kitten meow", "puppy bark", "duck quack").

Return ONLY valid JSON:
{{
  "queries": [
    {{"query": "...", "fallback": "...", "sfx": "..."}},
    ...
  ]
}}"""
    try:
        data = _safe_json_call(client, model, prompt, temperature=0.7)
        raw = data.get("queries", [])
        cleaned = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            q = str(item.get("query", "")).strip()
            fb = str(item.get("fallback", q)).strip() or q
            sfx = str(item.get("sfx", "")).strip() or "cute animal sound"
            if q:
                cleaned.append({"query": q, "fallback": fb, "sfx": sfx})
        if len(cleaned) >= 3:
            return cleaned[:n_queries]
    except Exception:
        pass

    defaults = [
        {"query": "cute kitten close up eyes", "fallback": "kitten cat", "sfx": "kitten meow"},
        {"query": "playful puppy dog running grass", "fallback": "cute puppy", "sfx": "puppy barking"},
        {"query": "baby panda eating bamboo", "fallback": "baby panda", "sfx": "panda sound"},
        {"query": "fluffy bunny rabbit eating grass", "fallback": "cute bunny", "sfx": "rabbit eating"},
        {"query": "cute sea otter swimming water", "fallback": "sea otter", "sfx": "water splash"},
        {"query": "ducklings walking together pond", "fallback": "ducklings", "sfx": "duck quack"},
        {"query": "hamster eating sunflower seed close up", "fallback": "hamster", "sfx": "hamster squeak"},
    ]
    while len(defaults) < n_queries:
        defaults = defaults + defaults
    return defaults[:n_queries]

# ==============================================================================
# AI CALL #2: VIẾT NARRATION CHO CÁC CLIP ĐÃ TẢI THỰC TẾ
# ==============================================================================
def ai_write_narration_for_clips(client, model, topic: str, clip_queries: list, lang: str):
    """
    clip_queries: list[{"query": "...", "fallback": "..."}] — ground truth của hình ảnh
    Trả về: list[{"speech": "...", "sfx": "..."}]
    """
    clip_list_txt = "\n".join(
        f'Scene {i+1}: VISUAL = "{c["query"]}"  (subject: {c["fallback"]})'
        for i, c in enumerate(clip_queries)
    )

    prompt = f"""You are a warm, charming pet documentary narrator.
Topic: "{topic}"
Narration language: {lang}
Total scenes: {len(clip_queries)}

Here is the EXACT visual content ALREADY edited into the video (in order). DO NOT change it, only describe it:
{clip_list_txt}

TASK: Write narration so that the SPEECH of each scene MATCHES its visual content above.
Also make ONE small continuous story: scene 1 = meet, middle = play/explore, end = cozy/rest.
Scene N must flow naturally into scene N+1.

STRICT RULES:
- The speech of scene N MUST refer to what is VISIBLE in scene N (based on the visual above).
- Do NOT invent visuals that are not in the list.
- Each speech: MAX 9 words, warm & adorable, ~2.5-4 seconds of speaking.
- Each SFX: short English keyword matching the animal sound (e.g. "kitten meow", "puppy barking").
- All speeches must be in {lang}.

Return ONLY valid JSON:
{{
  "scenes": [
    {{"speech": "...", "sfx": "..."}},
    ...
  ]
}}"""

    try:
        data = _safe_json_call(client, model, prompt, temperature=0.5)
        raw = data.get("scenes", [])
        cleaned = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            sp = str(item.get("speech", "")).strip()
            sfx = str(item.get("sfx", "")).strip() or "cute animal sound"
            if sp:
                cleaned.append({"speech": sp, "sfx": sfx})

        # Bù nếu thiếu
        while len(cleaned) < len(clip_queries):
            cleaned.append({
                "speech": f"Look at this little friend, scene {len(cleaned)+1}.",
                "sfx": "cute animal sound"
            })
        return cleaned[:len(clip_queries)]
    except Exception:
        # Fallback: speech generic cho từng scene
        return [
            {"speech": f"So cute! Little friend number {i+1}.", "sfx": "cute animal sound"}
            for i in range(len(clip_queries))
        ]

# ==============================================================================
# CÀO B-ROLL & SFX
# ==============================================================================
def fetch_from_pexels(query: str, p_key: str, used_ids: set):
    headers = {"Authorization": p_key.strip()}
    for page in [random.randint(1, 4), random.randint(1, 2)]:
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
    fb = scene_query.get("fallback", "cute animal")
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
                if preview and download_file_safe(preview, dest, min_size=3000):
                    return True
    except Exception:
        pass
    return False

# ==============================================================================
# VIDEO: CẮT / LOOP ĐÚNG DURATION ĐỘNG
# ==============================================================================
def cut_clip_to_duration(raw_p: str, out_p: str, duration: float, is_port: bool, keep_audio: bool) -> bool:
    res_f = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,fps=30"
        if is_port else
        "scale=1280:720:force_original_aspect_ratio=increase,"
        "crop=1280:720,setsar=1,fps=30"
    )
    raw_dur = get_media_duration(raw_p, default=10.0)

    if raw_dur < duration + 0.6:
        cmd = [
            FFMPEG_EXE, "-y",
            "-stream_loop", "-1",
            "-i", raw_p,
            "-t", f"{duration:.3f}",
            "-vf", res_f,
        ]
    else:
        start_sec = random.uniform(0.3, max(0.4, raw_dur - duration - 0.4))
        cmd = [
            FFMPEG_EXE, "-y",
            "-ss", f"{start_sec:.2f}",
            "-i", raw_p,
            "-t", f"{duration:.3f}",
            "-vf", res_f,
        ]

    src_has_audio = has_audio_stream(raw_p)
    if keep_audio and src_has_audio:
        fade_out = max(0.1, duration - 0.35)
        cmd += [
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-video_track_timescale", str(TIMESCALE),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-af", f"afade=t=in:d=0.15,afade=t=out:st={fade_out:.2f}:d=0.35",
            out_p
        ]
    else:
        cmd += [
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-video_track_timescale", str(TIMESCALE),
            out_p
        ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return has_audio_stream(out_p) if keep_audio else False

# ==============================================================================
# MIX AUDIO SCENE (DURATION ĐỘNG)
# ==============================================================================
def build_scene_audio(voice_path: str, orig_clip: str, sfx_path: str, out_audio: str, scene_duration: float):
    inputs = ["-i", voice_path]
    filters = [f"[0:a]aresample=44100,volume={VOICE_GAIN},apad=pad_dur={scene_duration:.3f}[v]"]
    amix_inputs = ["[v]"]
    idx = 1

    if orig_clip and os.path.exists(orig_clip) and has_audio_stream(orig_clip):
        inputs += ["-i", orig_clip]
        filters.append(
            f"[{idx}:a]aresample=44100,volume={ORIGINAL_GAIN},"
            f"apad=pad_dur={scene_duration:.3f}[o]"
        )
        amix_inputs.append("[o]")
        idx += 1

    if sfx_path and os.path.exists(sfx_path):
        inputs += ["-i", sfx_path]
        filters.append(
            f"[{idx}:a]aresample=44100,volume={SFX_GAIN},adelay=200|200,"
            f"afade=t=in:d=0.15,apad=pad_dur={scene_duration:.3f}[s]"
        )
        amix_inputs.append("[s]")
        idx += 1

    filter_complex = (
        ";".join(filters) + ";" +
        "".join(amix_inputs) +
        f"amix=inputs={len(amix_inputs)}:duration=longest:dropout_transition=0,"
        f"atrim=0:{scene_duration:.3f},asetpts=N/SR/TB,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    cmd = [FFMPEG_EXE, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        out_audio
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==============================================================================
# PIPELINE v3: B-roll TRƯỚC → VOICE SAU
# ==============================================================================
if st.button("🚀 Bắt Đầu Tạo Video Động Vật Dễ Thương", use_container_width=True, type="primary"):
    if not topic_genre.strip():
        st.warning("Vui lòng nhập chủ đề động vật.")
    else:
        status = st.status(f"Khởi động với model: {LLM_MODEL}", expanded=True)
        workdir = tempfile.mkdtemp(prefix="cute_animals_")
        is_port = "portrait" in orientation_opt
        is_en = "Tiếng Anh" in voice_choice
        lang = "English" if is_en else "Vietnamese"

        used_ids = st.session_state.global_used_ids
        used_content = st.session_state.global_used_content

        try:
            client = Groq(api_key=groq_key.strip())

            # ============================
            # 1. AI SINH QUERY B-ROLL
            # ============================
            status.update(label=f"🧠 1/6: AI sinh {approx_clips} query B-roll (model: {LLM_MODEL.split('/')[-1]})...")
            queries = ai_generate_broll_queries(client, LLM_MODEL, topic_genre.strip(), animal_focus, approx_clips)
            status.update(label=f"🧠 1/6: Đã có {len(queries)} query B-roll. Bắt đầu tải...")

            # ============================
            # 2. TẢI B-ROLL (giữ raw, chưa cắt)
            # ============================
            status.update(label="🎬 2/6: Tải B-roll động vật dễ thương & lọc trùng...")
            scenes = []
            for idx, q in enumerate(queries):
                v_url = get_broll_clip(q, pexels_key, pixabay_key, used_ids)
                if not v_url:
                    v_url = get_broll_clip(
                        {"query": "cute pet kitten puppy", "fallback": "cute animal"},
                        pexels_key, pixabay_key, used_ids
                    )
                raw_v = os.path.join(workdir, f"raw_{idx:03d}.mp4")
                ok = v_url and download_file_safe(v_url, raw_v)

                # Chống trùng khung hình
                if ok:
                    ch = video_content_hash(raw_v)
                    if ch in used_content:
                        os.remove(raw_v)
                        v_url2 = get_broll_clip(
                            {"query": "playful cute animals", "fallback": "cute pets"},
                            pexels_key, pixabay_key, used_ids
                        )
                        if v_url2 and download_file_safe(v_url2, raw_v):
                            ch = video_content_hash(raw_v)
                    used_content.add(ch)

                if not ok or not os.path.exists(raw_v):
                    # Fallback: clip pastel
                    color_v = os.path.join(workdir, f"raw_{idx:03d}.mp4")
                    subprocess.run([
                        FFMPEG_EXE, "-y", "-f", "lavfi",
                        "-i", f"color=c=0xFFD1DC:s={'1080x1920' if is_port else '1280x720'}:d=5:r=30",
                        "-pix_fmt", "yuv420p", "-video_track_timescale", str(TIMESCALE),
                        color_v
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    raw_v = color_v

                scenes.append({
                    "query": q["query"],
                    "fallback": q["fallback"],
                    "sfx_query_hint": q["sfx"],
                    "raw": raw_v,
                    "raw_dur": get_media_duration(raw_v, default=5.0),
                })

            # ============================
            # 3. AI VIẾT NARRATION KHỚP CLIP THỰC TẾ
            # ============================
            status.update(label="📝 3/6: AI đọc query thực tế → viết narration khớp từng clip...")
            narrations = ai_write_narration_for_clips(
                client, LLM_MODEL, topic_genre.strip(),
                [{"query": s["query"], "fallback": s["fallback"]} for s in scenes],
                lang
            )

            for sc, narr in zip(scenes, narrations):
                sc["speech"] = narr["speech"]
                sc["sfx_query"] = narr["sfx"] or sc["sfx_query_hint"]

            # ============================
            # 4. SINH VOICE + ĐO DURATION
            # ============================
            status.update(label="🎙️ 4/6: Sinh voice & đo duration để cắt clip khớp chính xác...")
            for idx, sc in enumerate(scenes):
                v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
                generate_voice(sc["speech"], v_file, voice_choice)
                v_dur = get_media_duration(v_file, default=3.0)
                scene_dur = min(v_dur + VOICE_PAD, MAX_SCENE_DUR)
                scene_dur = max(scene_dur, MIN_SCENE_DUR)
                sc["voice"] = v_file
                sc["voice_dur"] = v_dur
                sc["duration"] = round(scene_dur, 3)

            total_video_sec = sum(sc["duration"] for sc in scenes)
            status.update(label=f"🎙️ 4/6: Xong {len(scenes)} voice, tổng video {total_video_sec:.1f}s")

            # ============================
            # 5. CẮT CLIP THEO DURATION ĐỘNG + TẢI SFX
            # ============================
            status.update(label="✂️ 5/6: Cắt clip khớp duration voice + tải tiếng kêu...")
            for idx, sc in enumerate(scenes):
                cut_v = os.path.join(workdir, f"cut_{idx:03d}.mp4")
                has_orig = cut_clip_to_duration(
                    sc["raw"], cut_v, sc["duration"], is_port, keep_original_audio
                )
                sc["clip"] = cut_v
                sc["has_orig"] = has_orig
                try:
                    if sc["raw"] != cut_v and os.path.exists(sc["raw"]):
                        os.remove(sc["raw"])
                except Exception:
                    pass

                sfx_path = os.path.join(workdir, f"sfx_{idx:03d}.mp3")
                if freesound_key:
                    fetch_animal_sfx(sc["sfx_query"], freesound_key, sfx_path)
                sc["sfx"] = sfx_path if os.path.exists(sfx_path) else None

            # ============================
            # 6. MIX AUDIO + MUX + CONCAT + BGM MASTER
            # ============================
            status.update(label="🎚️ 6/6: Hòa âm & nối master...")
            clips_txt = os.path.join(workdir, "clips.txt")
            with open(clips_txt, "w", encoding="utf-8") as f_cl:
                for idx, sc in enumerate(scenes):
                    scene_audio = os.path.join(workdir, f"a_{idx:03d}.m4a")
                    build_scene_audio(
                        sc["voice"],
                        sc["clip"] if sc["has_orig"] else None,
                        sc["sfx"],
                        scene_audio,
                        sc["duration"]
                    )
                    synced_v = os.path.join(workdir, f"s_{idx:03d}.mp4")
                    subprocess.run([
                        FFMPEG_EXE, "-y",
                        "-i", sc["clip"], "-i", scene_audio,
                        "-t", f"{sc['duration']:.3f}",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                        "-video_track_timescale", str(TIMESCALE),
                        "-avoid_negative_ts", "make_zero",
                        "-fflags", "+genpts",
                        "-vsync", "cfr",
                        synced_v
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    f_cl.write(f"file '{os.path.abspath(synced_v)}'\n")

            temp_merged = os.path.join(workdir, "temp_merged.mp4")
            final_mp4 = os.path.join(workdir, "cute_animals_master.mp4")

            subprocess.run([
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", clips_txt, "-c", "copy", temp_merged
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            bgm_raw = os.path.join(workdir, "bgm.mp3")
            has_bgm = (bgm_volume > 0) and download_file_safe(CUTE_BGM_URL, bgm_raw, min_size=50000)

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
                    "-movflags", "+faststart",
                    "-shortest", final_mp4
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                subprocess.run([
                    FFMPEG_EXE, "-y", "-i", temp_merged,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    final_mp4
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            out_dur = get_media_duration(final_mp4, default=0)
            status.update(label=f"🎉 Hoàn thành! Tổng {out_dur:.1f}s — voice viết theo hình thực tế.", state="complete")

            with open(final_mp4, "rb") as f:
                v_bytes = f.read()

            st.video(v_bytes)
            st.download_button(
                label=f"⬇️ Tải Video Hoàn Chỉnh ({out_dur:.1f}s)",
                data=v_bytes,
                file_name=f"cute_animals_{int(out_dur)}s_{int(time.time())}.mp4",
                mime="video/mp4",
                use_container_width=True
            )

        except Exception as e:
            status.update(label=f"❌ Thất bại: {str(e)}", state="error")
            st.error(f"Chi tiết lỗi: {e}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
