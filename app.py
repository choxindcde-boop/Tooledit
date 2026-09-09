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

CINEMATIC_BGM_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4c/Scott_Buckley_-_Aurora.mp3"

SFX_ASSETS = {
    "airplane": "https://upload.wikimedia.org/wikipedia/commons/transcoded/5/5a/Jet_flyby.ogg/Jet_flyby.ogg.mp3",
    "ship": "https://upload.wikimedia.org/wikipedia/commons/transcoded/2/27/Thunderstorm_sound.ogg/Thunderstorm_sound.ogg.mp3",
    "disaster": "https://upload.wikimedia.org/wikipedia/commons/transcoded/2/27/Thunderstorm_sound.ogg/Thunderstorm_sound.ogg.mp3",
    "nature": "https://upload.wikimedia.org/wikipedia/commons/transcoded/e/ea/Bird_songs_in_forest.ogg/Bird_songs_in_forest.ogg.mp3",
    "car": "https://upload.wikimedia.org/wikipedia/commons/transcoded/5/5a/Jet_flyby.ogg/Jet_flyby.ogg.mp3"
}

try:
    groq_key = st.secrets["GROQ_API_KEY"]
    pexels_key = st.secrets.get("PEXELS_API_KEY", "")
    pixabay_key = st.secrets.get("PIXABAY_API_KEY", "")
except Exception:
    st.error("Chưa cấu hình API Key trong mục Secrets của Streamlit Cloud!")
    st.stop()

st.title("🎬 Studio POV Master Pro Max")
st.caption("Tai nạn/Bão biển cào kho mở Wikimedia & Archive • Động vật/Xe dùng Pexels • Cắt đúng ≤ 5.0s")

CATEGORY_SETTINGS = {
    "💥 Tổng hợp tai nạn, thảm họa, khoảnh khắc hiểm nghèo thực tế": {
        "engine": "open_archive_disaster",
        "default_topic": "Các vụ tai nạn máy bay hạ cánh khẩn cấp trong bão, tàu lớn chao đảo giữa sóng thần",
        "search_pool": [
            ("airplane emergency landing accident", "aircraft storm"),
            ("rough seas ship wave crash storm", "ship heavy weather"),
            ("airplane cockpit turbulence crosswind", "cockpit emergency"),
            ("rescue boat extreme storm waves", "boat storm ocean")
        ],
        "default_voice": "Tiếng Anh: Guy (Nam thời sự / Thảm họa Seconds Before Disaster)",
        "prompt_tone": "Khẩn cấp, dồn dập, nguy hiểm tột độ phong cách phóng sự Seconds Before Disaster"
    },
    "🐾 Thế giới Động vật / Thú cưng dễ thương": {
        "engine": "stock_only",
        "default_topic": "Những khoảnh khắc ngộ nghĩnh đáng yêu của thú cưng và muôn loài động vật hoang dã",
        "search_pool": [
            ("cute golden retriever puppy playing barking", "puppy dog"),
            ("baby panda climbing bamboo", "baby panda"),
            ("little kitten playing meowing", "kitten cat"),
            ("fluffy bunny rabbit eating carrot", "cute bunny"),
            ("playful sea otter floating water", "sea otter")
        ],
        "default_voice": "Tiếng Anh: Ana (Giọng hoạt hình / Vui tươi)",
        "prompt_tone": "Ngộ nghĩnh, tươi vui, tràn ngập năng lượng tích cực và đáng yêu"
    },
    "🏎️ Siêu xe / Tốc độ / Đua đêm Tokyo": {
        "engine": "stock_only",
        "default_topic": "Những màn drift nghẹt thở của dàn siêu xe triệu đô trên đường cao tốc đêm",
        "search_pool": [
            ("supercar drifting night city street loud exhaust", "drift car night"),
            ("sports car speeding highway exhaust flames", "sports car speed"),
            ("neon cyberpunk race car launch control", "supercar acceleration")
        ],
        "default_voice": "Tiếng Anh: Christopher (Trầm khàn / Phim tài liệu)",
        "prompt_tone": "Hồi hộp, uy lực, phấn khích với tốc độ và âm thanh động cơ gầm rú"
    },
    "🌌 Khám phá / Khoa học viễn tưởng / Vũ trụ": {
        "engine": "stock_only",
        "default_topic": "Hành trình khám phá hố đen tử thần và những tàn tích văn minh cổ đại bí ẩn",
        "search_pool": [
            ("deep space nebula galaxy stars", "space exploration"),
            ("ancient ruins temple drone cinematic", "ancient civilization"),
            ("astronaut walking on mars surface", "astronaut space")
        ],
        "default_voice": "Tiếng Anh: Christopher (Trầm khàn / Phim tài liệu)",
        "prompt_tone": "Hùng vĩ, bí ẩn, mang tính khám phá vũ trụ sâu sắc"
    }
}

selected_cat_name = st.selectbox("Chọn thể loại video chính:", list(CATEGORY_SETTINGS.keys()))
cat_config = CATEGORY_SETTINGS[selected_cat_name]

topic_text = st.text_area(
    "Mô tả chi tiết kịch bản / Tình huống:",
    value=cat_config["default_topic"],
    height=80
)

col1, col2 = st.columns(2)
with col1:
    voice_choice = st.selectbox(
        "Giọng đọc thuyết minh:",
        [
            cat_config["default_voice"],
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
st.info(f"💡 Hệ thống sẽ sản xuất **{calc_clips} phân cảnh chuẩn xác** (mỗi cảnh đúng 5.0 giây).")

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    orientation_opt = st.selectbox("Khung hình xuất bản:", ["landscape (Ngang 16:9 YouTube Chuẩn)", "portrait (Dọc 9:16 Shorts/TikTok)"])
with col_opt2:
    raw_vol = st.slider("Âm lượng tiếng hiện trường (Gió/Động cơ/Sóng) (%):", min_value=30, max_value=180, value=110, step=10)

bgm_volume = st.slider("Âm lượng nhạc nền ngầm BGM (%):", min_value=0, max_value=40, value=15, step=5)

# ==============================================================================
# HÀM CÀO VIDEO KHO MỞ (WIKIMEDIA & ARCHIVE.ORG)
# ==============================================================================

def download_file_safe(url: str, dest: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=25) as r:
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=32768):
                        f.write(chunk)
                return os.path.exists(dest) and os.path.getsize(dest) > 20000
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

def search_wikimedia_commons_video(query: str, used_hashes: set) -> str:
    """Tìm video tài liệu thật trên Wikimedia Commons qua API mở không bao giờ chặn bot"""
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": f"{query} filetype:video",
        "srnamespace": "6",
        "srlimit": "8"
    }
    headers = {"User-Agent": "POVStudioTool/2.0"}
    try:
        r = requests.get(api_url, params=params, headers=headers, timeout=8)
        if r.ok:
            results = r.json().get("query", {}).get("search", [])
            for item in results:
                title = item.get("title", "")
                if title not in used_hashes:
                    # Lấy link direct stream
                    info_params = {
                        "action": "query",
                        "format": "json",
                        "titles": title,
                        "prop": "imageinfo",
                        "iiprop": "url|mediatype"
                    }
                    info_r = requests.get(api_url, params=info_params, headers=headers, timeout=8)
                    pages = info_r.json().get("query", {}).get("pages", {})
                    for _, pdata in pages.items():
                        imageinfo = pdata.get("imageinfo", [])
                        if imageinfo:
                            media_url = imageinfo[0].get("url")
                            if media_url and media_url.endswith(('.webm', '.mp4', '.ogv')):
                                used_hashes.add(title)
                                return media_url
    except Exception:
        pass
    return None

def search_internet_archive_video(query: str, used_hashes: set) -> str:
    """Tìm video tài liệu thảm họa trên Archive.org qua API mở"""
    api_url = "https://archive.org/advancedsearch.php"
    params = {
        "q": f"{query} AND mediatype:(movies)",
        "fl[]": "identifier",
        "rows": "6",
        "page": "1",
        "output": "json"
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(api_url, params=params, headers=headers, timeout=8)
        if r.ok:
            docs = r.json().get("response", {}).get("docs", [])
            for doc in docs:
                ident = doc.get("identifier")
                if ident and ident not in used_hashes:
                    meta_url = f"https://archive.org/metadata/{ident}"
                    meta_r = requests.get(meta_url, headers=headers, timeout=8)
                    if meta_r.ok:
                        files = meta_r.json().get("files", [])
                        for f in files:
                            name = f.get("name", "")
                            if name.endswith(".mp4") and "512kb" not in name:
                                used_hashes.add(ident)
                                return f"https://archive.org/download/{ident}/{name}"
    except Exception:
        pass
    return None

def fetch_stock_clip(query: str, p_key: str, pb_key: str, used_hashes: set, dest_path: str) -> bool:
    """Chỉ dùng cho Động vật & Siêu xe"""
    headers = {"Authorization": p_key.strip()} if p_key else {}
    if p_key:
        for page in [1, 2]:
            try:
                url = f"{PEXELS_VIDEO_URL}?query={urllib.parse.quote(query)}&per_page=12&page={page}"
                r = requests.get(url, headers=headers, timeout=8)
                if r.ok and r.json().get("videos"):
                    for v in r.json()["videos"]:
                        v_id = f"pexels_{v.get('id')}"
                        if v_id not in used_hashes:
                            files = v.get("video_files", [])
                            hd = next((f["link"] for f in files if f.get("quality") == "hd" and f.get("file_type") == "video/mp4"), None)
                            if not hd and files:
                                hd = files[0].get("link")
                            if hd and download_file_safe(hd, dest_path):
                                used_hashes.add(v_id)
                                return True
            except Exception:
                continue

    if pb_key:
        try:
            url = f"{PIXABAY_VIDEO_URL}?key={pb_key.strip()}&q={urllib.parse.quote(query)}&per_page=12"
            r = requests.get(url, timeout=8)
            if r.ok and r.json().get("hits"):
                for v in r.json()["hits"]:
                    v_id = f"pixabay_{v.get('id')}"
                    if v_id not in used_hashes:
                        target = v.get("videos", {}).get("large") or v.get("videos", {}).get("medium")
                        if target and target.get("url") and download_file_safe(target["url"], dest_path):
                            used_hashes.add(v_id)
                            return True
        except Exception:
            pass
    return False

def get_broll_smart_routed(engine_mode: str, query: str, fallback_q: str, p_key: str, pb_key: str, used_hashes: set, dest_path: str) -> bool:
    if engine_mode == "open_archive_disaster":
        # Tuyệt đối không dùng Pexels cho máy bay/tàu thảm họa
        v_url = search_wikimedia_commons_video(query, used_hashes)
        if not v_url:
            v_url = search_internet_archive_video(query, used_hashes)
        if not v_url:
            v_url = search_wikimedia_commons_video(fallback_q, used_hashes)
        if not v_url:
            v_url = search_internet_archive_video(fallback_q, used_hashes)
        if v_url and download_file_safe(v_url, dest_path):
            return True
        # Backup trường hợp rớt mạng: clip bão biển mở
        backup_url = "https://upload.wikimedia.org/wikipedia/commons/transcoded/8/87/Rough_seas_aboard_the_RRS_James_Clark_Ross.webm/Rough_seas_aboard_the_RRS_James_Clark_Ross.webm.720p.vp9.webm"
        return download_file_safe(backup_url, dest_path)

    # Động vật & Siêu xe: Dùng Pexels / Pixabay
    ok = fetch_stock_clip(query, p_key, pb_key, used_hashes, dest_path)
    if not ok:
        ok = fetch_stock_clip(fallback_q, p_key, pb_key, used_hashes, dest_path)
    return ok

# ==============================================================================
# HÀM XỬ LÝ ÂM THANH & RENDER 5.0S
# ==============================================================================

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

def render_scene_safe(raw_v: str, voice_mp3: str, cat_tag: str, query_text: str, out_p: str, is_port: bool, raw_vol_float: float, workdir: str, idx: int):
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

    # 1. Cắt hình ảnh độc lập (bỏ hoàn toàn cờ audio)
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

    # 2. Xử lý âm thanh hiện trường
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
        if cat_tag == "disaster":
            sfx_url = SFX_ASSETS["airplane"] if any(w in query_text.lower() for w in ["plane", "jet", "air", "cockpit"]) else SFX_ASSETS["ship"]
        elif cat_tag == "animal":
            sfx_url = SFX_ASSETS["nature"]
        else:
            sfx_url = SFX_ASSETS["car"]

        sfx_cache = os.path.join(workdir, f"sfx_{idx:03d}.mp3")
        download_file_safe(sfx_url, sfx_cache)

        if os.path.exists(sfx_cache) and os.path.getsize(sfx_cache) > 10000:
            subprocess.run([
                FFMPEG_EXE, "-y",
                "-i", sfx_cache,
                "-ss", f"{(idx * 3) % 15}",
                "-t", f"{CLIP_DURATION:.3f}",
                "-af", "bass=g=5:f=110,volume=1.2",
                "-ar", "44100", "-ac", "2",
                norm_env_wav
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            subprocess.run([
                FFMPEG_EXE, "-y",
                "-f", "lavfi", "-i", "anoisesrc=d=5:c=brown:r=44100:a=0.35",
                "-af", "lowpass=f=1100,tremolo=f=1.0:d=0.7",
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

    # 4. Hòa âm
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
if st.button("🚀 Bắt Đầu Sản Xuất Master Pro Max", use_container_width=True, type="primary"):
    status = st.status(f"Hệ thống đang sản xuất {calc_clips} phân cảnh...", expanded=True)
    workdir = tempfile.mkdtemp(prefix="master_routed_")
    used_hashes = set()
    is_port = "portrait" in orientation_opt
    is_en = "Tiếng Anh" in voice_choice
    raw_vol_float = raw_vol / 100.0
    total_video_time = calc_clips * CLIP_DURATION

    try:
        client = Groq(api_key=groq_key.strip())

        # 1. AI phân tích kịch bản
        status.update(label=f"🧠 1/4: {LLM_MODEL} đang xây dựng kịch bản...")
        pool = cat_config["search_pool"]
        engine_mode = cat_config["engine"]
        cat_tag = "disaster" if "disaster" in engine_mode else ("animal" if "Động vật" in selected_cat_name else "car")

        prompt = f"""You are a professional documentary video director.
Category: "{selected_cat_name}".
User prompt: "{topic_text}".
Total scenes: Exactly {calc_clips} scenes (5.0s each).
Language: {"English" if is_en else "Vietnamese"}.

STRICT DYNAMIC SEARCH RULES:
- If the topic mentions multiple objects (e.g. airplanes and ships), ALTERNATE between them!
- Scene 1: An intense airplane event (e.g. airplane emergency landing, cockpit turbulence).
- Scene 2: A violent maritime event (e.g. rough sea storm wave ship, boat extreme waves).
- Scene 3: High-tension angle (e.g. cockpit alarm, huge ocean storm).
- `query_en`: 2-3 specific English words for documentary archive search.
- `fallback_en`: 2 simple backup words.
- `speech_text`: One dramatic sentence under 12 words (~3.2 seconds).

Return ONLY a JSON list of {calc_clips} objects:
[
  {{"scene": 1, "speech_text": "...", "query_en": "airplane emergency landing", "fallback_en": "aircraft storm"}},
  {{"scene": 2, "speech_text": "...", "query_en": "rough seas ship wave crash", "fallback_en": "ship storm"}}
]"""

        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        raw_text = resp.choices[0].message.content.strip()
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        parsed_scenes = json.loads(match.group(0)) if match else []

        while len(parsed_scenes) < calc_clips:
            idx = len(parsed_scenes)
            pick = pool[idx % len(pool)]
            parsed_scenes.append({
                "scene": idx + 1,
                "speech_text": f"Tình huống nguy cấp căng thẳng ở phân cảnh {idx + 1}.",
                "query_en": pick[0],
                "fallback_en": pick[1]
            })
        parsed_scenes = parsed_scenes[:calc_clips]

        # 2. Tạo Voice
        status.update(label="🎙️ 2/4: Đang tạo giọng đọc thuyết minh...")
        scenes = []
        for idx, item in enumerate(parsed_scenes):
            v_file = os.path.join(workdir, f"v_{idx:03d}.mp3")
            asyncio.run(generate_voice(item["speech_text"], v_file, voice_choice))
            scenes.append({
                "query": item["query_en"],
                "fallback": item.get("fallback_en", item["query_en"]),
                "audio": v_file
            })

        # 3. Tải B-roll và render từng cảnh
        status.update(label=f"🎬 3/4: Đang trích xuất B-roll từ ({engine_mode})...")
        clips_txt = os.path.join(workdir, "clips.txt")

        with open(clips_txt, "w", encoding="utf-8") as f_cl:
            for idx, sc in enumerate(scenes):
                raw_v = os.path.join(workdir, f"r_{idx:03d}.mp4")
                scene_v = os.path.join(workdir, f"scene_{idx:03d}.mp4")

                ok = get_broll_smart_routed(engine_mode, sc["query"], sc["fallback"], pexels_key, pixabay_key, used_hashes, raw_v)
                if not ok:
                    fallback_base = pool[idx % len(pool)][0]
                    get_broll_smart_routed(engine_mode, fallback_base, fallback_base, pexels_key, pixabay_key, used_hashes, raw_v)

                render_scene_safe(raw_v, sc["audio"], cat_tag, sc["query"], scene_v, is_port, raw_vol_float, workdir, idx)

                if os.path.exists(raw_v):
                    os.remove(raw_v)

                f_cl.write(f"file '{os.path.abspath(scene_v)}'\n")

        # 4. Nối cảnh & Ép hòa âm BGM
        status.update(label="⚡ 4/4: Ghép Master và hoàn tất hòa âm...", state="running")
        temp_merged = os.path.join(workdir, "temp_merged.mp4")
        final_mp4 = os.path.join(workdir, "master_final_pro.mp4")

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

        status.update(label=f"🎉 Hoàn thành video {calc_clips * 5} giây hoàn hảo!", state="complete")

        with open(final_mp4, "rb") as out_f:
            v_bytes = out_f.read()

        st.video(v_bytes)
        st.download_button(
            label=f"⬇️ Tải Video Hoàn Chỉnh ({calc_clips * 5} Giây)",
            data=v_bytes,
            file_name=f"master_{calc_clips * 5}s_{int(time.time())}.mp4",
            mime="video/mp4",
            use_container_width=True
        )

    except Exception as e:
        status.update(label=f"❌ Thất bại: {str(e)}", state="error")
        st.error(f"Chi tiết lỗi: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
