"""
🎬 POV MASTER ENGINE v6 - STREAMLIT CLOUD READY
Tạo video compilation với AI + Voice Over
Tối ưu chống block YouTube
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
import traceback

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

st.set_page_config(page_title="POV Master v6", page_icon="🎬", layout="wide")

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
        font-size: 2rem;
        margin: 0;
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
        if not self.client:
            return self._fallback_script(topic, num_scenes)
        
        prompt = f"""
        Tạo {num_scenes} câu mô tả ngắn về "{topic}".
        Mỗi câu 10-15 từ tiếng Anh, mô tả cảnh cụ thể.
        Mỗi câu một dòng, không đánh số.
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
        except:
            return self._fallback_script(topic, num_scenes)
    
    def generate_keywords(self, scene_text: str) -> List[str]:
        if not self.client:
            return [scene_text]
        
        prompt = f'Create 5 YouTube search keywords for: "{scene_text}". Return JSON array.'
        
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
                return json.loads(match.group())[:5]
            return [scene_text]
        except:
            return [scene_text]
    
    def _fallback_script(self, topic: str, num_scenes: int) -> List[str]:
        templates = [
            f"A massive {topic} caught on camera moments before disaster",
            f"Incredible {topic} footage that shocked everyone",
            f"Top {topic} moments you won't believe",
            f"Real {topic} caught live on camera",
            f"Unbelievable {topic} compilation",
            f"Shocking {topic} footage goes viral",
            f"Most dangerous {topic} moments ever",
            f"Extreme {topic} fails caught on tape",
            f"Rare {topic} footage you must see",
            f"Dramatic {topic} moments",
            f"Insane {topic} compilation",
            f"Real {topic} accidents on camera",
            f"Top 10 {topic} moments",
            f"Most terrifying {topic} footage",
            f"Unforgettable {topic} on camera"
        ]
        return [templates[i % len(templates)] for i in range(num_scenes)]

# ============================================
# VOICE OVER
# ============================================
class VoiceOverEngine:
    def __init__(self):
        self.voice_dir = Path("voiceovers")
        self.voice_dir.mkdir(exist_ok=True)
    
    def generate(self, text: str, index: int) -> Optional[str]:
        if not GTTS_AVAILABLE:
            return None
        try:
            output = self.voice_dir / f"voice_{index:03d}.mp3"
            tts = gTTS(text=text[:200], lang='en', slow=False)
            tts.save(str(output))
            return str(output)
        except:
            return None

# ============================================
# VIDEO PROCESSOR - ĐÃ TỐI ƯU CHỐNG BLOCK
# ============================================
class VideoProcessor:
    def __init__(self):
        self.temp_dir = Path("temp_videos")
        self.temp_dir.mkdir(exist_ok=True)
        self.used_video_ids = set()
    
    def _get_ydl_opts(self):
        """Cấu hình yt-dlp tối ưu"""
        return {
            'format': 'best[height<=480]/best',
            'outtmpl': str(self.temp_dir / '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': 3,
            'noplaylist': True,
            'ignoreerrors': True,
            'no_color': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
        }
    
    def search_download(self, keywords: List[str]) -> Optional[Dict]:
        """Tìm và download với nhiều fallback"""
        for kw in keywords:
            # Thử nhiều search query
            search_queries = [
                f"ytsearch5:{kw}",
                f"ytsearch5:{kw} video",
                f"ytsearch3:{kw} footage",
            ]
            
            for search_url in search_queries:
                try:
                    ydl_opts = self._get_ydl_opts()
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(search_url, download=False)
                        
                        if not info or 'entries' not in info:
                            continue
                        
                        for entry in info['entries']:
                            if not entry:
                                continue
                            
                            video_id = entry.get('id', '')
                            title = entry.get('title', '').lower()
                            duration = entry.get('duration', 0)
                            
                            if video_id in self.used_video_ids:
                                continue
                            
                            if duration < 20 or duration > 900:
                                continue
                            
                            # Download
                            try:
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
                            except Exception as e:
                                print(f"Download error: {e}")
                                continue
                except Exception as e:
                    print(f"Search error: {e}")
                    continue
        
        return None
    
    def extract_5s(self, video_path: str, output_path: str) -> bool:
        """Cắt 5 giây"""
        try:
            # Lấy duration
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            try:
                duration = float(result.stdout.strip())
            except:
                duration = 60
            
            # Chọn vị trí
            if duration > 30:
                start = random.randint(5, int(duration - 10))
            else:
                start = 3
            
            # Cắt bằng ffmpeg
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-ss', str(start),
                '-t', '5',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-c:a', 'aac',
                '-strict', 'experimental',
                output_path
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=30)
            return os.path.exists(output_path)
        except Exception as e:
            print(f"Extract error: {e}")
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
    <h1>🎬 POV MASTER ENGINE v6</h1>
    <p>AI Video Compilation - Streamlit Cloud Ready</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("🔑 API Keys")
    groq_key = st.text_input("Groq API Key", type="password", help="console.groq.com")
    
    st.markdown("---")
    st.header("⚙️ Settings")
    
    topic = st.text_input("Chủ đề", value="plane crashes and disasters")
    num_scenes = st.slider("Số scenes", 5, 60, 10, 5)
    st.info(f"⏱️ Video ~{num_scenes * 5} giây")
    
    st.markdown("---")
    enable_voice = st.checkbox("🎙️ Voice over", value=True)
    
    st.markdown("---")
    
    if st.button("🧪 Test API"):
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
                st.error(f"❌ {e}")
        else:
            st.warning("Nhập API key")

# Main
if st.button("🚀 TẠO VIDEO", use_container_width=True, type="primary"):
    if not groq_key:
        st.error("❌ Nhập Groq API Key!")
        st.info("🔑 Lấy tại: console.groq.com")
    elif not topic:
        st.error("❌ Nhập chủ đề!")
    else:
        ai = GroqAI(groq_key)
        voice_engine = VoiceOverEngine()
        processor = VideoProcessor()
        
        # 1. AI viết kịch bản
        st.header("📜 Kịch bản:")
        with st.spinner("🤖 AI đang viết..."):
            script = ai.generate_script(topic, num_scenes)
        
        for i, line in enumerate(script, 1):
            st.markdown(f'<div class="script-card"><strong>Scene {i:02d}:</strong> {line}</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 2. Xử lý
        segments = []
        voiceovers = []
        progress = st.progress(0)
        status = st.empty()
        
        for i, scene_text in enumerate(script):
            status.text(f"🔄 Scene {i+1}/{num_scenes}...")
            
            keywords = ai.generate_keywords(scene_text)
            video_info = processor.search_download(keywords)
            
            if video_info:
                os.makedirs("output", exist_ok=True)
                seg_file = f"output/seg_{i:03d}.mp4"
                
                if processor.extract_5s(video_info['path'], seg_file):
                    segments.append(seg_file)
                    st.success(f"✅ Scene {i+1}: {video_info['title'][:40]}")
                    
                    if enable_voice:
                        voice_file = voice_engine.generate(scene_text, i)
                        if voice_file:
                            voiceovers.append(voice_file)
                else:
                    st.warning(f"⚠️ Scene {i+1}: Lỗi cắt")
                
                try:
                    os.remove(video_info['path'])
                except:
                    pass
            else:
                st.warning(f"⚠️ Scene {i+1}: Không tìm thấy")
            
            progress.progress((i + 1) / num_scenes)
        
        # 3. Ghép
        if segments:
            status.text("🔗 Ghép video...")
            
            with open('output/list.txt', 'w') as f:
                for seg in segments:
                    f.write(f"file '{Path(seg).resolve()}'\n")
            
            final_video = 'output/final.mp4'
            cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'output/list.txt', '-c', 'copy', final_video]
            subprocess.run(cmd, capture_output=True, timeout=120)
            
            if voiceovers and os.path.exists(final_video):
                with open('output/voice_list.txt', 'w') as f:
                    for v in voiceovers:
                        f.write(f"file '{Path(v).resolve()}'\n")
                
                voice_final = 'output/voice_final.mp3'
                cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'output/voice_list.txt', voice_final]
                subprocess.run(cmd, capture_output=True)
                
                final_voice = 'output/final_voice.mp4'
                cmd = ['ffmpeg', '-y', '-i', final_video, '-i', voice_final, '-c:v', 'copy', '-c:a', 'aac', '-shortest', final_voice]
                subprocess.run(cmd, capture_output=True, timeout=120)
                
                if os.path.exists(final_voice):
                    final_video = final_voice
            
            st.markdown("---")
            st.header("🎥 HOÀN THÀNH!")
            st.video(final_video)
            
            with open(final_video, 'rb') as f:
                st.download_button("📥 TẢI VIDEO", f.read(), file_name=f"video_{datetime.now().strftime('%H%M%S')}.mp4", mime="video/mp4")
        else:
            st.error("❌ Không tạo được video - thử lại với chủ đề khác")
        
        progress.progress(1.0)
        status.text("✅ Xong!")
