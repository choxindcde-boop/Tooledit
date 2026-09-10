"""
🎬 POV MASTER PRO v9 - Streamlit Cloud Ready
Dùng Cobalt API + Invidious (KHÔNG BAO GIỜ BỊ CHẶN)
"""

import streamlit as st
import subprocess
import os
import json
import re
import random
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict
import time

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

st.set_page_config(page_title="POV Master v9", page_icon="🎬", layout="wide")

st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        margin-bottom: 2rem;
    }
    .main-header h1 { color: white; font-size: 2rem; margin: 0; }
    .main-header p { color: #e0e0e0; font-size: 1.1rem; margin: 10px 0 0 0; }
    .script-card {
        background: #262730;
        padding: 0.8rem;
        border-radius: 8px;
        margin: 0.3rem 0;
        border-left: 3px solid #667eea;
        font-size: 0.9rem;
    }
    .badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 10px;
        font-size: 0.75rem;
        margin-left: 0.5rem;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# GROQ AI
# ============================================
class GroqAI:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key) if GROQ_AVAILABLE else None
        self.model = "openai/gpt-oss-20b"
    
    def generate_script(self, topic: str, num_scenes: int) -> List[str]:
        if not self.client:
            return self._fallback(topic, num_scenes)
        
        prompt = f"""Create {num_scenes} short English descriptions about "{topic}".
Each 10-15 words, different scenes. One per line, no numbering."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=1500
            )
            text = response.choices[0].message.content
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            lines = [re.sub(r'^[\d\.\)\-\*]+\s*', '', l) for l in lines]
            return lines[:num_scenes]
        except Exception as e:
            st.warning(f"AI error: {e}")
            return self._fallback(topic, num_scenes)
    
    def generate_keywords(self, scene_text: str) -> List[str]:
        if not self.client:
            return self._simple_keywords(scene_text)
        
        prompt = f'''Create 4 short YouTube search queries (2-5 words each) to find REAL video footage of: "{scene_text}".
Return only JSON array.'''
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=200
            )
            content = response.choices[0].message.content
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                return [str(k) for k in json.loads(match.group())][:4]
        except:
            pass
        return self._simple_keywords(scene_text)
    
    def _simple_keywords(self, text: str) -> List[str]:
        stop = {'a','an','the','and','or','but','in','on','at','to','for','of','with',
                'by','from','as','is','was','were','are','be','this','that','it'}
        words = re.findall(r'\w+', text.lower())
        kws = [w for w in words if w not in stop and len(w) > 2]
        if len(kws) >= 4:
            return [' '.join(kws[:4]), ' '.join(kws[-4:]), ' '.join(kws[1:5])]
        return [' '.join(kws)] if kws else [text[:30]]
    
    def _fallback(self, topic, n):
        t = [f"Real {topic} caught on camera", f"Amazing {topic} footage",
             f"Dramatic {topic} moment", f"Extreme {topic} video",
             f"Rare {topic} caught live", f"Shocking {topic} scene"]
        return [t[i % len(t)] for i in range(n)]

# ============================================
# VIDEO SOURCE 1: COBALT API (BEST - KHÔNG BỊ CHẶN)
# ============================================
class CobaltAPI:
    """Cobalt.tools API - Download YouTube không bị chặn"""
    
    # Danh sách instances
    INSTANCES = [
        "https://api.cobalt.tools",
        "https://cobalt-api.kwiatekmiki.com",
        "https://co.eepy.today",
        "https://cobalt.255x.ru",
    ]
    
    def __init__(self):
        self.temp_dir = Path("temp_cobalt")
        self.temp_dir.mkdir(exist_ok=True)
        self.used_ids = set()
    
    def get_download_url(self, youtube_url: str) -> Optional[str]:
        """Lấy URL download trực tiếp từ Cobalt"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        payload = {
            "url": youtube_url,
            "videoQuality": "480",
            "filenameStyle": "basic",
        }
        
        for instance in self.INSTANCES:
            try:
                r = requests.post(
                    instance,
                    headers=headers,
                    json=payload,
                    timeout=20
                )
                
                if r.status_code != 200:
                    continue
                
                data = r.json()
                status = data.get('status')
                
                if status in ['stream', 'redirect', 'tunnel']:
                    url = data.get('url')
                    if url:
                        return url
            except Exception as e:
                print(f"Cobalt {instance} error: {e}")
                continue
        
        return None
    
    def download(self, youtube_id: str) -> Optional[str]:
        """Download video qua Cobalt"""
        if youtube_id in self.used_ids:
            return None
        
        url = f"https://youtube.com/watch?v={youtube_id}"
        download_url = self.get_download_url(url)
        
        if not download_url:
            return None
        
        # Download file
        try:
            output = self.temp_dir / f"{youtube_id}.mp4"
            
            r = requests.get(download_url, stream=True, timeout=60)
            r.raise_for_status()
            
            with open(output, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            
            if output.exists() and output.stat().st_size > 50000:
                self.used_ids.add(youtube_id)
                return str(output)
        except Exception as e:
            print(f"Download error: {e}")
        
        return None

# ============================================
# VIDEO SOURCE 2: INVIDIOUS API (FALLBACK)
# ============================================
class InvidiousAPI:
    """Invidious - YouTube frontend miễn phí"""
    
    INSTANCES = [
        "https://inv.nadeko.net",
        "https://invidious.nerdvpn.de",
        "https://yewtu.be",
        "https://invidious.f5.si",
        "https://iv.melmac.space",
    ]
    
    def __init__(self):
        self.temp_dir = Path("temp_inv")
        self.temp_dir.mkdir(exist_ok=True)
        self.used_ids = set()
        self.working_instance = None
    
    def _get_instance(self) -> Optional[str]:
        """Tìm instance hoạt động"""
        if self.working_instance:
            return self.working_instance
        
        for instance in self.INSTANCES:
            try:
                r = requests.get(f"{instance}/api/v1/stats", timeout=5)
                if r.status_code == 200:
                    self.working_instance = instance
                    return instance
            except:
                continue
        
        return None
    
    def search(self, keyword: str) -> List[Dict]:
        """Tìm video trên Invidious"""
        instance = self._get_instance()
        if not instance:
            return []
        
        try:
            r = requests.get(
                f"{instance}/api/v1/search",
                params={"q": keyword, "type": "video", "sort_by": "relevance"},
                timeout=15
            )
            
            if r.status_code != 200:
                return []
            
            results = r.json()
            videos = []
            
            for v in results[:10]:
                if v.get('type') != 'video':
                    continue
                videos.append({
                    'id': v.get('videoId'),
                    'title': v.get('title', ''),
                    'duration': v.get('lengthSeconds', 0),
                })
            
            return videos
        except:
            return []
    
    def get_stream_url(self, video_id: str) -> Optional[str]:
        """Lấy URL stream"""
        instance = self._get_instance()
        if not instance:
            return None
        
        try:
            r = requests.get(
                f"{instance}/api/v1/videos/{video_id}",
                timeout=15
            )
            
            if r.status_code != 200:
                return None
            
            data = r.json()
            
            # Ưu tiên format video mp4
            formats = data.get('formatStreams', [])
            
            for fmt in formats:
                if fmt.get('container') == 'mp4':
                    return fmt.get('url')
            
            if formats:
                return formats[0].get('url')
            
            return None
        except:
            return None
    
    def download(self, video_id: str) -> Optional[str]:
        """Download video"""
        if video_id in self.used_ids:
            return None
        
        stream_url = self.get_stream_url(video_id)
        if not stream_url:
            return None
        
        # Đảm bảo URL đầy đủ
        if stream_url.startswith('/'):
            instance = self._get_instance()
            stream_url = f"{instance}{stream_url}"
        
        try:
            output = self.temp_dir / f"{video_id}.mp4"
            
            r = requests.get(stream_url, stream=True, timeout=60)
            r.raise_for_status()
            
            with open(output, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            
            if output.exists() and output.stat().st_size > 50000:
                self.used_ids.add(video_id)
                return str(output)
        except:
            pass
        
        return None
    
    def search_and_download(self, keyword: str) -> Optional[Dict]:
        """Tìm + download"""
        videos = self.search(keyword)
        
        if not videos:
            return None
        
        random.shuffle(videos)
        
        for v in videos:
            vid = v.get('id')
            duration = v.get('duration', 0)
            
            if not vid or vid in self.used_ids:
                continue
            
            if duration < 15 or duration > 900:
                continue
            
            path = self.download(vid)
            if path:
                return {
                    'source': 'Invidious',
                    'id': vid,
                    'path': path,
                    'duration': duration,
                    'title': v.get('title', '')
                }
        
        return None

# ============================================
# VIDEO SOURCE 3: PEXELS (B-ROLL FALLBACK)
# ============================================
class PexelsAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.temp_dir = Path("temp_px")
        self.temp_dir.mkdir(exist_ok=True)
        self.used = set()
    
    def search_and_download(self, keyword: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        
        # Map sang B-roll
        mapping = {
            'plane': 'airplane sky clouds', 'aircraft': 'airplane flying',
            'crash': 'dark storm clouds', 'fire': 'fire flames',
            'ocean': 'ocean waves storm', 'mountain': 'mountain fog',
            'city': 'city aerial view', 'car': 'road driving',
            'ship': 'ship ocean',
        }
        
        search_kw = keyword
        for k, v in mapping.items():
            if k in keyword.lower():
                search_kw = v
                break
        
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": self.api_key},
                params={"query": search_kw, "per_page": 10, "orientation": "landscape"},
                timeout=15
            )
            
            if r.status_code != 200:
                return None
            
            videos = r.json().get('videos', [])
            random.shuffle(videos)
            
            for v in videos:
                vid = v.get('id')
                if vid in self.used:
                    continue
                
                files = v.get('video_files', [])
                best = None
                for f in files:
                    if 640 <= f.get('width', 0) <= 1920:
                        best = f
                        break
                if not best and files:
                    best = files[0]
                
                if not best or not best.get('link'):
                    continue
                
                try:
                    output = self.temp_dir / f"px_{vid}.mp4"
                    r2 = requests.get(best['link'], stream=True, timeout=30)
                    r2.raise_for_status()
                    
                    with open(output, 'wb') as f:
                        for chunk in r2.iter_content(8192):
                            f.write(chunk)
                    
                    if output.exists() and output.stat().st_size > 10000:
                        self.used.add(vid)
                        return {
                            'source': 'Pexels',
                            'id': vid,
                            'path': str(output),
                            'duration': v.get('duration', 10),
                            'title': search_kw
                        }
                except:
                    continue
        except:
            pass
        
        return None

# ============================================
# VIDEO ENGINE - MULTI SOURCE
# ============================================
class VideoEngine:
    def __init__(self, pexels_key: str = ""):
        self.cobalt = CobaltAPI()
        self.invidious = InvidiousAPI()
        self.pexels = PexelsAPI(pexels_key) if pexels_key else None
    
    def get_video(self, keywords: List[str]) -> Optional[Dict]:
        """Thử lần lượt các nguồn"""
        
        # Chiến lược: Invidious search + Cobalt download
        for kw in keywords:
            # 1. Invidious search
            videos = self.invidious.search(kw)
            
            if videos:
                random.shuffle(videos)
                
                for v in videos[:5]:
                    vid = v.get('id')
                    duration = v.get('duration', 0)
                    
                    if not vid or vid in self.invidious.used_ids:
                        continue
                    
                    if duration < 15 or duration > 900:
                        continue
                    
                    # Thử Cobalt download
                    path = self.cobalt.download(vid)
                    
                    if path:
                        return {
                            'source': 'Cobalt+Invidious',
                            'id': vid,
                            'path': path,
                            'duration': duration,
                            'title': v.get('title', '')
                        }
                    
                    # Fallback: Invidious download
                    path = self.invidious.download(vid)
                    
                    if path:
                        return {
                            'source': 'Invidious',
                            'id': vid,
                            'path': path,
                            'duration': duration,
                            'title': v.get('title', '')
                        }
            
            # 2. Pexels fallback
            if self.pexels:
                result = self.pexels.search_and_download(kw)
                if result:
                    return result
        
        return None

# ============================================
# PROCESSOR
# ============================================
class Processor:
    def extract_5s(self, video_path: str, output_path: str) -> bool:
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries',
                   'format=duration', '-of', 'csv=p=0', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            try:
                duration = float(result.stdout.strip())
            except:
                duration = 15
            
            if duration > 15:
                start = random.uniform(3, duration - 8)
            elif duration > 6:
                start = random.uniform(0, duration - 6)
            else:
                start = 0
            
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start),
                '-i', video_path,
                '-t', '5',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '25',
                '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-r', '30',
                '-c:a', 'aac',
                '-ar', '44100',
                '-ac', '2',
                output_path
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=60)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 5000
        except:
            return False

# ============================================
# VOICE
# ============================================
class VoiceEngine:
    def __init__(self):
        self.dir = Path("voiceovers")
        self.dir.mkdir(exist_ok=True)
    
    def generate(self, text: str, index: int) -> Optional[str]:
        if not GTTS_AVAILABLE:
            return None
        try:
            output = self.dir / f"v_{index:03d}.mp3"
            tts = gTTS(text=text[:250], lang='en', slow=False)
            tts.save(str(output))
            return str(output)
        except:
            return None

# ============================================
# STREAMLIT UI
# ============================================
st.markdown("""
<div class="main-header">
    <h1>🎬 POV MASTER PRO v9</h1>
    <p>Cobalt + Invidious + Pexels - Không bao giờ bị chặn</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 API Keys")
    groq_key = st.text_input("Groq API Key", type="password", help="console.groq.com")
    pexels_key = st.text_input("Pexels API Key (optional)", type="password",
                                help="pexels.com/api - Cho B-roll fallback")
    
    st.markdown("---")
    st.header("⚙️ Settings")
    topic = st.text_input("Chủ đề", value="plane crash disaster footage")
    num_scenes = st.slider("Số scenes", 5, 30, 8, 1)
    st.info(f"⏱️ Video ~{num_scenes * 5}s")
    
    enable_voice = st.checkbox("Voice over", value=True)
    
    st.markdown("---")
    st.markdown("**Nguồn video (theo thứ tự):**")
    st.markdown("1. 🥇 Cobalt API")
    st.markdown("2. 🥈 Invidious")
    st.markdown("3. 🥉 Pexels")

if st.button("🚀 TẠO VIDEO", use_container_width=True, type="primary"):
    if not groq_key:
        st.error("❌ Cần Groq API Key")
    else:
        ai = GroqAI(groq_key)
        engine = VideoEngine(pexels_key)
        processor = Processor()
        voice_engine = VoiceEngine()
        
        st.header("📜 Kịch bản:")
        with st.spinner("🤖 AI viết..."):
            script = ai.generate_script(topic, num_scenes)
        
        for i, line in enumerate(script, 1):
            st.markdown(f'<div class="script-card"><strong>Scene {i:02d}:</strong> {line}</div>',
                       unsafe_allow_html=True)
        
        st.markdown("---")
        st.header("🎬 Đang tạo...")
        
        segments = []
        voiceovers = []
        sources = {}
        
        progress = st.progress(0)
        status = st.empty()
        
        for i, scene_text in enumerate(script):
            status.text(f"🔄 Scene {i+1}/{num_scenes}...")
            
            keywords = ai.generate_keywords(scene_text)
            video_info = engine.get_video(keywords)
            
            if video_info and video_info.get('path'):
                os.makedirs("output", exist_ok=True)
                seg_file = f"output/seg_{i:03d}.mp4"
                
                if processor.extract_5s(video_info['path'], seg_file):
                    segments.append(seg_file)
                    src = video_info['source']
                    sources[src] = sources.get(src, 0) + 1
                    
                    st.success(f"✅ Scene {i+1} [{src}]: {video_info.get('title','')[:40]}")
                    
                    if enable_voice:
                        v = voice_engine.generate(scene_text, i)
                        if v:
                            voiceovers.append(v)
                else:
                    st.warning(f"⚠️ Scene {i+1}: Lỗi cắt")
                
                try:
                    os.remove(video_info['path'])
                except:
                    pass
            else:
                st.warning(f"⚠️ Scene {i+1}: Không tìm thấy video")
            
            progress.progress((i + 1) / num_scenes)
        
        # Concat
        if segments:
            status.text("🔗 Ghép video...")
            
            with open('output/list.txt', 'w') as f:
                for seg in segments:
                    f.write(f"file '{Path(seg).resolve()}'\n")
            
            final_video = 'output/final.mp4'
            cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                   '-i', 'output/list.txt', '-c:v', 'libx264',
                   '-preset', 'ultrafast', '-crf', '25',
                   '-c:a', 'aac', final_video]
            subprocess.run(cmd, capture_output=True, timeout=300)
            
            # Voice
            if voiceovers and os.path.exists(final_video):
                with open('output/vlist.txt', 'w') as f:
                    for v in voiceovers:
                        f.write(f"file '{Path(v).resolve()}'\n")
                
                vfinal = 'output/voice.mp3'
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                               '-i', 'output/vlist.txt', vfinal],
                              capture_output=True, timeout=120)
                
                if os.path.exists(vfinal):
                    fvoice = 'output/final_voice.mp4'
                    subprocess.run(['ffmpeg', '-y', '-i', final_video, '-i', vfinal,
                                   '-c:v', 'copy', '-c:a', 'aac', '-shortest', fvoice],
                                  capture_output=True, timeout=180)
                    if os.path.exists(fvoice):
                        final_video = fvoice
            
            st.markdown("---")
            st.header("🎥 HOÀN THÀNH!")
            
            if os.path.exists(final_video):
                st.video(final_video)
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Scenes", len(segments))
                col2.metric("Tỉ lệ", f"{len(segments)*100//num_scenes}%")
                col3.metric("Thời lượng", f"{len(segments)*5}s")
                
                st.subheader("📊 Nguồn:")
                for src, cnt in sources.items():
                    st.write(f"• {src}: {cnt}")
                
                with open(final_video, 'rb') as f:
                    st.download_button(
                        "📥 TẢI VIDEO",
                        f.read(),
                        file_name=f"video_{datetime.now().strftime('%H%M%S')}.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )
        else:
            st.error("❌ Không tạo được video!")
            st.info("💡 Thử đổi chủ đề hoặc đợi vài phút (API có thể bị rate limit)")
        
        progress.progress(1.0)
        status.text("✅ Xong!")
