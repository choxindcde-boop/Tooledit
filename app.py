import streamlit as st
import os
import json
import math
import subprocess
import requests
import re
import imageio_ffmpeg
from groq import Groq

st.set_page_config(page_title="AI Video Auto Maker", layout="centered")

st.title("🎬 Tool Tự Động Tạo Video")
st.caption("Groq AI + Stock Pexels + FFmpeg Portable")

# Lấy đường dẫn FFmpeg chuẩn tự động
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# 1. Tự động lấy Key từ Secrets
try:
    groq_api_key = st.secrets["GROQ_API_KEY"]
    pexels_api_key = st.secrets["PEXELS_API_KEY"]
except Exception:
    st.error("Chưa cấu hình API Key trong mục Secrets của Streamlit Cloud!")
    st.stop()

# Giao diện chính
topic = st.text_area("Chủ đề hoặc mô tả video:", placeholder="VD: Siêu xe đua trong thành phố mưa đêm, cyberpunk...")
col1, col2 = st.columns(2)
with col1:
    total_duration = st.number_input("Tổng thời lượng (giây):", min_value=5, max_value=120, value=15, step=5)
with col2:
    orientation = st.selectbox("Khung hình:", ["portrait (Dọc 9:16 Shorts/TikTok)", "landscape (Ngang 16:9)"])

# Hàm gọi Groq với danh sách model khả dụng
def get_keywords(client, user_topic, num_clips):
    prompt = f"""
    You are an AI video editor. The user wants a video about: "{user_topic}".
    Break down this concept into exactly {num_clips} visual search queries for stock video libraries (Pexels).
    Each query must be 1-3 simple English keywords describing a clear visual scene.
    Return ONLY a raw JSON array of strings, without any explanation or markdown formatting.
    Example output format:
    ["supercar speed", "city night rain", "neon light street"]
    """
    
    models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
    content = ""
    for model_name in models_to_try:
        try:
            res = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.6,
            )
            content = res.choices[0].message.content.strip()
            if content:
                break
        except Exception:
            continue

    if not content:
        raise RuntimeError("Không thể kết nối đến model Groq đã chỉ định.")

    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    return json.loads(content)

# Hàm tìm video Pexels
def get_pexels_url(api_key, kw, aspect):
    orient = "portrait" if "portrait" in aspect else "landscape"
    url = f"https://api.pexels.com/videos/search?query={kw}&per_page=3&orientation={orient}"
    res = requests.get(url, headers={"Authorization": api_key})
    if res.status_code != 200:
        return None
    data = res.json()
    videos = data.get("videos", [])
    if not videos:
        return None
    files = videos[0].get("video_files", [])
    hd_file = next((f.get("link") for f in files if f.get("quality") == "hd"), None)
    return hd_file or (files[0].get("link") if files else None)

def download_file(url, target_path):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(target_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

# Nút bắt đầu tạo
if st.button("🚀 Bắt đầu tạo Video", type="primary"):
    if not topic.strip():
        st.warning("Vui lòng nhập chủ đề video.")
    else:
        temp_dir = "temp_work"
        os.makedirs(temp_dir, exist_ok=True)
        status = st.empty()
        
        try:
            num_clips = math.ceil(total_duration / 5)
            status.info(f"🤖 Đang dùng Groq phân tích {num_clips} phân cảnh...")
            client = Groq(api_key=groq_api_key)
            keywords = get_keywords(client, topic, num_clips)
            st.write("Từ khóa AI chọn:", keywords)

            status.info("📥 Đang tải các đoạn video gốc từ Pexels...")
            downloaded = []
            for i, kw in enumerate(keywords):
                v_url = get_pexels_url(pexels_api_key, kw, orientation)
                if not v_url:
                    v_url = get_pexels_url(pexels_api_key, "cute animals", orientation)
                v_path = os.path.join(temp_dir, f"raw_{i}.mp4")
                download_file(v_url, v_path)
                downloaded.append(v_path)

            status.info("⚙️ FFmpeg đang cắt chuẩn 5s mỗi đoạn và ghép nối...")
            is_portrait = "portrait" in orientation
            res_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if is_portrait else "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
            
            norm_clips = []
            for i, p in enumerate(downloaded):
                out_p = os.path.join(temp_dir, f"norm_{i}.mp4")
                cmd = [
                    FFMPEG_EXE, "-y", "-ss", "0", "-t", "5",
                    "-i", p,
                    "-vf", f"{res_filter},fps=30",
                    "-c:v", "libx264", "-an", out_p
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                norm_clips.append(out_p)

            concat_txt = os.path.join(temp_dir, "concat.txt")
            with open(concat_txt, "w") as f:
                for c in norm_clips:
                    f.write(f"file '{os.path.abspath(c)}'\n")

            final_output = "final_output.mp4"
            concat_cmd = [
                FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
                "-i", concat_txt,
                "-c", "copy", final_output
            ]
            subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            status.success("🎉 Tạo video thành công!")
            st.video(final_output)

            with open(final_output, "rb") as f:
                st.download_button("Tải video về máy", f, file_name="final_video.mp4", mime="video/mp4")

        except Exception as e:
            status.error(f"Lỗi: {e}")
