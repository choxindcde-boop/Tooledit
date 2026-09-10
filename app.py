"""
🎬 POV MASTER ENGINE v5 - AI POWERED
Tạo video compilation với AI + Voice Over
Chạy trên Google Colab hoặc Streamlit Cloud
"""

import streamlit as st
import yt_dlp
import subprocess
import os
import hashlib
import json
import re
import random
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict
import time

# Groq AI
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Google TTS
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

st.set_page_config(page_title="POV Master v5", page_icon="🎬", layout="wide")

# ============================================
# CUSTOM CSS
# ============================================
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        margin-bottom: 2rem;
    }
    .main-header h1 {
        color: white;
        font-size: 2.5rem;
        margin: 0;
    }
    .main-header p {
        color: #e0e0e0;
        font-size: 1.2rem;
        margin: 10px 0 0 0;
    }
    .script-card {
        background: #262730;
        padding: 0.8rem;
        border-radius: 8px;
        margin: 0.3rem 0;
        border-left: 3px solid #667eea;
        font-size: 0.9rem;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        padding: 0.75rem 2rem;
        border-radius: 25px;
        border: none;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# GROQ AI ENGINE
# ============================================

class GroqAI:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key) if GROQ_AVAILABLE else None
        self.model = "openai/gpt-oss-20b"
    
    def generate_script(self, topic: str, num_scenes: int) -> List[str]:
        """AI viết kịch bản"""
        if not self.client:
            return self._fallback_script(topic, num_scenes)
        
        prompt = f"""
        Bạn là biên kịch video YouTube chuyên nghiệp.
        Tạo {num_scenes} câu mô tả ngắn về "{topic}".
        
        Yêu cầu:
        - Mỗi câu 10-15 từ tiếng Anh
        - Mô tả một cảnh cụ thể, khác nhau
        - Gây tò mò, kịch tính
        - Phù hợp để tìm video trên YouTube
        
        Format: Mỗi câu một dòng, không đánh số.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=1500
            )
            
            text = response.choices[0].message.content
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            lines = [re.sub(r'^\d+[\.\)]\s*', '', l) for l in lines]
            return lines[:num_scenes]
        except Exception as e:
            st.warning(f"Groq error: {e}")
            return self._fallback_script(topic, num_scenes)
    
    def generate_keywords(self, scene_text: str) -> List[str]:
        """AI tạo keywords"""
        if not self.client:
            return [scene_text]
        
        prompt = f"""
        Tạo 5 từ khóa YouTube để tìm video về:
        "{scene_text}"
        
        Trả về JSON array 5 phần tử.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            content = response.choices[0].message.content
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                keywords = json.loads(match.group())
                return keywords[:5]
            return [scene_text]
        except:
            return [scene_text]
    
    def _fallback_script(self, topic: str, num_scenes: int) -> List[str]:
        templates = [
            f"A massive {topic} accident caught on camera moments before disaster",
            f"Incredible {topic} footage that shocked everyone",
            f"Top {topic} moments you won't believe happened",
            f"Real {topic} disaster caught live on camera",
            f"Unbelievable {topic} compilation seconds before impact",
            f"Shocking {topic} footage goes viral worldwide",
            f"Most dangerous {topic} moments ever recorded",
            f"Extreme {topic} fails caught on tape",
            f"Rare {topic} footage you must see to believe",
            f"Dramatic {topic} moments frozen in time",
            f"Insane {topic} compilation that will shock you",
            f"Real {topic} accidents caught on camera",
            f"Top 10 {topic} moments caught live",
            f"Most terrifying {topic} footage ever",
            f"Unforgettable {topic} disasters on camera"
        ]
        return [templates[i % len(templates)] for i in range(num_scenes)]

# ============================================
# VOICE OVER ENGINE
# ============================================

class VoiceOverEngine:
    def __init__(self):
        self.voice_dir = Path("voiceovers")
        self.voice_dir.mkdir(exist_ok=True)
    
    def generate(self, text: str, index: int) -> Optional[str]:
        """Tạo voice over"""
        if not GTTS_AVAILABLE:
            return None
        
        try:
            output = self.voice_dir / f"voice_{index:03d}.mp3"
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save(str(output))
            return str(output)
        except Exception as e:
            print(f"TTS error: {e}")
            return None

# ============================================
# VIDEO PROCESSOR
# ============================================

class VideoProcessor:
    def __init__(self):
        self.temp_dir = Path("temp_videos")
        self.temp_dir.mkdir(exist_ok=True)
        self.used_video_ids = set()
    
    def search_download(self, keywords: List[str]) -> Optional[Dict]:
        """Tìm và download video"""
        for kw in keywords:
            try:
                ydl_opts = {
                    'format': 'best[height<=720]',
                    'outtmpl': str(self.temp_dir / '%(id)s.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                    'socket_timeout': 20,
                    'retries': 1,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch3:{kw}", download=False)
                    
                    if not info or 'entries' not in info:
                        continue
                    
                    for entry in info['entries']:
                        video_id = entry.get('id', '')
                        title = entry.get('title', '').lower()
                        duration = entry.get('duration', 0)
                        
                        if video_id in self.used_video_ids:
                            continue
                        
                        if duration < 30 or duration > 600:
                            continue
                        
                        bad_words = ['animation', 'cartoon', 'game', 'tutorial', 'review', 'movie', 'trailer']
                        if any(w in title for w in bad_words):
                            continue
                        
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                            ydl2.download([f"https://youtube.com/watch?v={video_id}"])
                        
                        files = list(self.temp_dir.glob(f"{video_id}.*"))
                        if files:
                            self.used_video_ids.add(video_id)
                            return {
                                'id': video_id,
                                'title': title,
                                'path': str(files[0]),
                                'duration': duration
                            }
            except:
                continue
        
        return None
    
    def extract_5s(self, video_path: str, output_path: str) -> bool:
        """Cắt 5 giây"""
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            duration = float(result.stdout.strip()) if result.stdout.strip() else 60
            
            if duration > 30:
                start = random.randint(5, int(duration - 10))
            else:
                start = 3
            
            cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-ss', str(start), '-t', '5',
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-crf', '23', '-c:a', 'aac',
                output_path
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=30)
            return os.path.exists(output_path)
        except:
            return False
    
    def cleanup(self):
        for f in self.temp_dir.iterdir():
            try:
                f.unlink()
            except:
                pass

# ============================================
# STREAMLIT UI
# ============================================

st.markdown("""
<div class="main-header">
    <h1>🎬 POV MASTER ENGINE v5</h1>
    <p>AI-Powered Video Compilation với Voice Over & Kịch bản thông minh</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("🔑 API Keys")
    
    groq_key = st.text_input(
        "Groq API Key",
        type="password",
        help="Lấy miễn phí tại console.groq.com"
    )
    
    st.markdown("---")
    st.header("⚙️ Settings")
    
    topic = st.text_input(
        "Chủ đề video",
        value="plane crashes and aviation disasters",
        help="VD: plane crashes, car accidents, cute animals..."
    )
    
    num_scenes = st.slider(
        "Số scenes",
        min_value=5,
        max_value=60,
        value=15,
        step=5,
        help="Mỗi scene = 5 giây"
    )
    
    st.info(f"⏱️ Video ~{num_scenes * 5} giây ({num_scenes * 5 // 60} phút)")
    
    st.markdown("---")
    st.header("🎵 Audio")
    
    enable_voice = st.checkbox("🎙️ Voice over (AI đọc)", value=True)
    enable_music = st.checkbox("🎵 Nhạc nền", value=False)
    
    st.markdown("---")
    
    if st.button("🧪 Test API", use_container_width=True):
        if groq_key:
            try:
                client = Groq(api_key=groq_key)
                response = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[{"role": "user", "content": "Say OK"}],
                    max_tokens=10
                )
                st.success("✅ API hoạt động!")
            except Exception as e:
                st.error(f"❌ Lỗi: {e}")
        else:
            st.warning("Nhập API key trước")

# Main
if st.button("🚀 TẠO VIDEO VỚI AI", use_container_width=True, type="primary"):
    if not groq_key:
        st.error("❌ Nhập Groq API Key vào sidebar!")
        st.info("🔑 Lấy miễn phí tại: console.groq.com")
    elif not topic:
        st.error("❌ Nhập chủ đề!")
    else:
        ai = GroqAI(groq_key)
        voice_engine = VoiceOverEngine()
        processor = VideoProcessor()
        
        st.header("📜 Kịch bản AI tạo:")
        
        with st.spinner("🤖 AI đang viết kịch bản..."):
            script = ai.generate_script(topic, num_scenes)
        
        for i, line in enumerate(script, 1):
            st.markdown(f"""
            <div class="script-card">
                <strong>Scene {i:02d}:</strong> {line}
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        st.header("🎬 Đang xử lý...")
        
        segments = []
        voiceovers = []
        progress = st.progress(0)
        status = st.empty()
        
        for i, scene_text in enumerate(script):
            status.text(f"🔄 Scene {i+1}/{num_scenes}: {scene_text[:50]}...")
            
            keywords = ai.generate_keywords(scene_text)
            video_info = processor.search_download(keywords)
            
            if video_info:
                os.makedirs("output", exist_ok=True)
                seg_file = f"output/seg_{i:03d}.mp4"
                
                if processor.extract_5s(video_info['path'], seg_file):
                    segments.append(seg_file)
                    st.success(f"✅ Scene {i+1}: {video_info['title'][:50]}")
                    
                    if enable_voice:
                        voice_file = voice_engine.generate(scene_text, i)
                        if voice_file:
                            voiceovers.append(voice_file)
                else:
                    st.warning(f"⚠️ Scene {i+1}: Không cắt được")
                
                try:
                    os.remove(video_info['path'])
                except:
                    pass
            else:
                st.warning(f"⚠️ Scene {i+1}: Không tìm thấy video")
            
            progress.progress((i + 1) / num_scenes)
        
        if segments:
            status.text("🔗 Đang ghép video...")
            
            with open('output/list.txt', 'w') as f:
                for seg in segments:
                    f.write(f"file '{Path(seg).resolve()}'\n")
            
            final_video = 'output/final_video.mp4'
            cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', 'output/list.txt', '-c', 'copy', final_video
            ]
            subprocess.run(cmd, capture_output=True, timeout=120)
            
            if voiceovers and os.path.exists(final_video):
                status.text("🎙️ Đang thêm voice over...")
                
                with open('output/voice_list.txt', 'w') as f:
                    for v in voiceovers:
                        f.write(f"file '{Path(v).resolve()}'\n")
                
                voice_final = 'output/voice_final.mp3'
                cmd = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                    '-i', 'output/voice_list.txt', voice_final
                ]
                subprocess.run(cmd, capture_output=True)
                
                final_with_voice = 'output/final_with_voice.mp4'
                cmd = [
                    'ffmpeg', '-y',
                    '-i', final_video,
                    '-i', voice_final,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-af', 'volume=2.0',
                    '-shortest',
                    final_with_voice
                ]
                subprocess.run(cmd, capture_output=True, timeout=120)
                
                if os.path.exists(final_with_voice):
                    final_video = final_with_voice
            
            st.markdown("---")
            st.header("🎥 VIDEO HOÀN THÀNH!")
            st.video(final_video)
            
            with open(final_video, 'rb') as f:
                st.download_button(
                    "📥 TẢI VIDEO",
                    f.read(),
                    file_name=f"ai_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
                    mime="video/mp4",
                    use_container_width=True
                )
            
            file_size = os.path.getsize(final_video) / (1024 * 1024)
            st.success(f"📦 {file_size:.1f} MB | ⏱️ {len(segments) * 5}s | 🎬 {len(segments)} scenes")
        else:
            st.error("❌ Không tạo được video!")
        
        progress.progress(1.0)
        status.text("✅ Hoàn thành!")

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <p>🎬 POV Master Engine v5 - AI Powered</p>
    <p>🔑 Groq API miễn phí | 🎙️ Voice over tự động</p>
    <p>⚠️ Chỉ sử dụng footage bạn có quyền sử dụng</p>
</div>
""", unsafe_allow_html=True)
