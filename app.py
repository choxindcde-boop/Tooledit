"""
🎬 POV Master Engine v3 - Không giới hạn YouTube API
Hỗ trợ: Động vật cute, từ khóa tùy chỉnh, chống trùng thông minh
"""

import streamlit as st
import os
import json
import time
import hashlib
import subprocess
import tempfile
import shutil
import base64
import re
import random
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, asdict

# Core libraries
import numpy as np
import cv2
import requests
from PIL import Image
import yt_dlp

# AI libraries
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# ============================================
# CONFIGURATION
# ============================================

st.set_page_config(
    page_title="POV Master Engine v3",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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
    .topic-card {
        background: #262730;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s;
        border: 2px solid transparent;
    }
    .topic-card:hover {
        border-color: #667eea;
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.3);
    }
    .topic-emoji {
        font-size: 3rem;
        margin-bottom: 0.5rem;
    }
    .topic-name {
        font-weight: bold;
        font-size: 1.1rem;
    }
    .scene-card {
        background: #262730;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
    }
    .metric-card {
        background: #262730;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #667eea;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #888;
        margin-top: 0.5rem;
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
    .keyword-tag {
        display: inline-block;
        background: #333;
        color: #fff;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        margin: 0.2rem;
        font-size: 0.9rem;
    }
    .avoid-tag {
        display: inline-block;
        background: #4a1a1a;
        color: #ff6b6b;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        margin: 0.2rem;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# DATA CLASSES
# ============================================

@dataclass
class SceneConfig:
    """Cấu hình cho một scene"""
    scene_id: int
    keywords: List[str]  # Keywords để tìm video
    avoid_keywords: List[str]  # Keywords để tránh
    description: str  # Mô tả cảnh
    
@dataclass
class VideoCandidate:
    """Video ứng viên"""
    video_id: str
    title: str
    duration: int
    url: str
    relevance_score: float = 0.0
    
@dataclass
class ExtractedSegment:
    """Segment đã cắt"""
    scene_id: int
    source_video_id: str
    source_title: str
    start_time: float
    end_time: float
    file_path: str
    fingerprint: str
    confidence_score: float

# ============================================
# VIDEO FINDER (Không dùng YouTube API)
# ============================================

class VideoFinder:
    """Tìm video YouTube không cần API - dùng yt-dlp trực tiếp"""
    
    def __init__(self, temp_dir: str = "temp_videos"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Cấu hình yt-dlp
        self.ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': str(self.temp_dir / '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': 2,
            'noplaylist': True,
            'max_downloads': 1,
        }
    
    def search_and_download(self, keywords: List[str], avoid_keywords: List[str] = None, max_duration: int = 600) -> Optional[Dict]:
        """
        Tìm và download video trực tiếp từ YouTube
        Không cần API key, không giới hạn quota
        """
        avoid_keywords = avoid_keywords or []
        
        # Thử từng keyword
        for keyword in keywords:
            print(f"🔍 Searching: {keyword}")
            
            try:
                # Dùng yt-dlp để search
                search_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'force_generic_extractor': False,
                }
                
                # Search YouTube
                search_url = f"ytsearch5:{keyword}"
                
                with yt_dlp.YoutubeDL(search_opts) as ydl:
                    info = ydl.extract_info(search_url, download=False)
                    
                    if not info or 'entries' not in info:
                        continue
                    
                    # Lọc videos
                    for entry in info['entries']:
                        if not entry:
                            continue
                        
                        video_id = entry.get('id', '')
                        title = entry.get('title', '').lower()
                        duration = entry.get('duration', 0)
                        
                        # Kiểm tra duration
                        if duration > max_duration or duration < 30:
                            continue
                        
                        # Kiểm tra avoid keywords
                        if any(kw.lower() in title for kw in avoid_keywords):
                            continue
                        
                        # Kiểm tra relevance
                        relevance = self._calculate_relevance(title, keywords, avoid_keywords)
                        
                        if relevance < 0.3:
                            continue
                        
                        # Download video
                        video_path = self._download_video(video_id)
                        
                        if video_path:
                            return {
                                'video_id': video_id,
                                'title': title,
                                'duration': duration,
                                'path': video_path,
                                'relevance': relevance
                            }
                        
            except Exception as e:
                print(f"⚠️ Search error for '{keyword}': {e}")
                continue
        
        return None
    
    def _download_video(self, video_id: str) -> Optional[str]:
        """Download video"""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                ydl.download([f"https://youtube.com/watch?v={video_id}"])
                
                video_files = list(self.temp_dir.glob(f"{video_id}.*"))
                if video_files:
                    return str(video_files[0])
                    
        except Exception as e:
            print(f"⚠️ Download error: {e}")
        
        return None
    
    def _calculate_relevance(self, title: str, keywords: List[str], avoid_keywords: List[str]) -> float:
        """Tính relevance score"""
        score = 0.0
        
        # Check keywords
        for keyword in keywords:
            keyword_words = keyword.lower().split()
            matches = sum(1 for word in keyword_words if word in title)
            score += matches * 0.3
        
        # Check avoid keywords
        for avoid in avoid_keywords:
            if avoid.lower() in title:
                score -= 0.5
        
        return max(score, 0.0)
    
    def cleanup(self):
        """Xóa files tạm"""
        for file in self.temp_dir.iterdir():
            try:
                file.unlink()
            except:
                pass

# ============================================
# VIDEO ANALYZER
# ============================================

class VideoAnalyzer:
    """Phân tích video để tìm segments tốt"""
    
    def analyze_video(self, video_path: str, num_segments: int = 5) -> List[Dict]:
        """Phân tích video"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # Sample mỗi 2 giây
        sample_times = []
        current_time = 0
        
        while current_time < duration - 5:
            sample_times.append(current_time)
            current_time += 2
        
        segments = []
        
        for time_point in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, time_point * 1000)
            ret, frame = cap.read()
            
            if ret:
                motion = self._calculate_motion(frame)
                complexity = self._calculate_complexity(frame)
                brightness = self._calculate_brightness(frame)
                
                # Score tổng hợp
                score = (motion * 0.4 + complexity * 0.3 + brightness * 0.3)
                
                segments.append({
                    'start_time': time_point,
                    'end_time': min(time_point + 5, duration),
                    'motion': motion,
                    'complexity': complexity,
                    'brightness': brightness,
                    'score': score
                })
        
        cap.release()
        
        # Sort theo score
        segments.sort(key=lambda x: x['score'], reverse=True)
        
        return segments[:num_segments]
    
    def _calculate_motion(self, frame: np.ndarray) -> float:
        """Tính motion"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            magnitude = np.sqrt(sobelx**2 + sobely**2)
            return min(np.mean(magnitude) / 100, 1.0)
        except:
            return 0.5
    
    def _calculate_complexity(self, frame: np.ndarray) -> float:
        """Tính complexity"""
        try:
            small = cv2.resize(frame, (64, 64))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            return min(np.mean(edges) / 100, 1.0)
        except:
            return 0.5
    
    def _calculate_brightness(self, frame: np.ndarray) -> float:
        """Tính brightness"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            # Tối ưu: không quá tối, không quá sáng
            if brightness < 30 or brightness > 225:
                return 0.3
            elif brightness < 60 or brightness > 200:
                return 0.7
            else:
                return 1.0
        except:
            return 0.7
    
    def extract_segment(self, video_path: str, start_time: float, duration: float, output_path: str) -> Optional[str]:
        """Cắt segment"""
        try:
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-c:a', 'aac',
                '-strict', 'experimental',
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            
            if os.path.exists(output_path):
                return output_path
                
        except Exception as e:
            print(f"⚠️ FFmpeg error: {e}")
            
            # Fallback OpenCV
            try:
                cap = cv2.VideoCapture(video_path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
                
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(output_path, fourcc, fps, (int(cap.get(3)), int(cap.get(4))))
                
                frames_to_write = int(duration * fps)
                for _ in range(frames_to_write):
                    ret, frame = cap.read()
                    if not ret:
                        break
                    out.write(frame)
                
                cap.release()
                out.release()
                
                if os.path.exists(output_path):
                    return output_path
                    
            except Exception as e2:
                print(f"⚠️ OpenCV error: {e2}")
        
        return None
    
    def calculate_fingerprint(self, video_path: str) -> str:
        """Tính fingerprint"""
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            frame_indices = np.linspace(0, total_frames - 1, min(3, total_frames), dtype=int)
            frame_hashes = []
            
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    small = cv2.resize(frame, (32, 32))
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    frame_hash = hashlib.md5(gray.tobytes()).hexdigest()[:16]
                    frame_hashes.append(frame_hash)
            
            cap.release()
            return hashlib.md5(''.join(frame_hashes).encode()).hexdigest()
        except:
            return hashlib.md5(str(time.time()).encode()).hexdigest()

# ============================================
# DEDUPLICATION SYSTEM
# ============================================

class DeduplicationSystem:
    """Chống trùng lặp nâng cao"""
    
    def __init__(self):
        self.used_video_ids = set()
        self.used_fingerprints = set()
        self.used_segments = []
        self.used_titles = set()
    
    def is_video_used(self, video_id: str) -> bool:
        return video_id in self.used_video_ids
    
    def is_fingerprint_used(self, fingerprint: str) -> bool:
        return fingerprint in self.used_fingerprints
    
    def is_title_similar(self, title: str) -> bool:
        """Kiểm tra title có giống video đã dùng"""
        title_lower = title.lower()
        title_words = set(title_lower.split())
        
        for used_title in self.used_titles:
            used_words = set(used_title.lower().split())
            overlap = len(title_words & used_words) / len(title_words)
            if overlap > 0.7:  # 70% giống nhau
                return True
        
        return False
    
    def is_segment_overlapping(self, video_id: str, start_time: float, end_time: float) -> bool:
        for segment in self.used_segments:
            if segment['video_id'] == video_id:
                if not (end_time <= segment['start_time'] or start_time >= segment['end_time']):
                    return True
        return False
    
    def add_segment(self, video_id: str, title: str, start_time: float, end_time: float, fingerprint: str):
        self.used_segments.append({
            'video_id': video_id,
            'start_time': start_time,
            'end_time': end_time,
            'fingerprint': fingerprint
        })
        self.used_video_ids.add(video_id)
        self.used_fingerprints.add(fingerprint)
        self.used_titles.add(title)

# ============================================
# MAIN ENGINE
# ============================================

class POVMasterEngineV3:
    """Main engine - Không cần YouTube API"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.video_finder = VideoFinder()
        self.video_analyzer = VideoAnalyzer()
        self.deduplicator = DeduplicationSystem()
        
        self.segments: List[ExtractedSegment] = []
    
    def process_scene(self, scene: SceneConfig) -> Optional[ExtractedSegment]:
        """Xử lý một scene"""
        print(f"\n🎬 Processing scene {scene.scene_id}: {scene.description}")
        
        # Tìm và download video
        video_info = self.video_finder.search_and_download(
            scene.keywords,
            scene.avoid_keywords
        )
        
        if not video_info:
            return None
        
        video_id = video_info['video_id']
        video_title = video_info['title']
        video_path = video_info['path']
        
        # Kiểm tra trùng
        if self.deduplicator.is_video_used(video_id):
            os.remove(video_path)
            return None
        
        if self.deduplicator.is_title_similar(video_title):
            os.remove(video_path)
            return None
        
        # Phân tích video
        segments = self.video_analyzer.analyze_video(video_path)
        
        if not segments:
            os.remove(video_path)
            return None
        
        # Thử từng segment
        for segment_info in segments:
            start = segment_info['start_time']
            end = segment_info['end_time']
            
            # Kiểm tra overlap
            if self.deduplicator.is_segment_overlapping(video_id, start, end):
                continue
            
            # Cắt segment
            output_filename = f"scene_{scene.scene_id:03d}.mp4"
            output_path = self.output_dir / output_filename
            
            segment_path = self.video_analyzer.extract_segment(
                video_path, start, 5.0, str(output_path)
            )
            
            if segment_path:
                fingerprint = self.video_analyzer.calculate_fingerprint(segment_path)
                
                if self.deduplicator.is_fingerprint_used(fingerprint):
                    os.remove(segment_path)
                    continue
                
                segment = ExtractedSegment(
                    scene_id=scene.scene_id,
                    source_video_id=video_id,
                    source_title=video_title,
                    start_time=start,
                    end_time=end,
                    file_path=segment_path,
                    fingerprint=fingerprint,
                    confidence_score=segment_info['score']
                )
                
                self.deduplicator.add_segment(video_id, video_title, start, end, fingerprint)
                self.segments.append(segment)
                
                # Cleanup
                try:
                    os.remove(video_path)
                except:
                    pass
                
                return segment
        
        # Cleanup
        try:
            os.remove(video_path)
        except:
            pass
        
        return None
    
    def concatenate_segments(self, output_filename: str = "final_video.mp4") -> str:
        """Ghép segments"""
        if not self.segments:
            return ""
        
        output_path = self.output_dir / output_filename
        
        # Tạo list file
        list_file = self.output_dir / "segments_list.txt"
        
        with open(list_file, 'w') as f:
            for segment in self.segments:
                f.write(f"file '{Path(segment.file_path).resolve()}'\n")
        
        # FFmpeg concat
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(list_file),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'aac',
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            if output_path.exists():
                return str(output_path)
        except:
            pass
        
        return ""

# ============================================
# TOPIC TEMPLATES
# ============================================

TOPIC_TEMPLATES = {
    "✈️ Plane Crashes": {
        "keywords": [
            "airplane crash", "plane accident", "aircraft crash landing",
            "plane crash caught on camera", "airplane accident footage",
            "plane crash compilation", "aircraft emergency landing"
        ],
        "avoid": [
            "animation", "simulation", "game", "tutorial", "review",
            "documentary", "movie", "trailer", "music"
        ],
        "description": "Plane crashes and aviation accidents"
    },
    "🚗 Car Accidents": {
        "keywords": [
            "car crash", "car accident", "vehicle collision",
            "car crash caught on camera", "car accident compilation",
            "dashcam crash", "road accident footage"
        ],
        "avoid": [
            "animation", "simulation", "game", "tutorial", "review",
            "documentary", "movie", "trailer", "music"
        ],
        "description": "Car crashes and road accidents"
    },
    "🐱 Cute Animals": {
        "keywords": [
            "cute animals", "funny animal videos", "adorable pets",
            "cute cats and dogs", "baby animals playing",
            "funny pet compilation", "cute animal moments"
        ],
        "avoid": [
            "animation", "cartoon", "drawing", "tutorial", "review",
            "documentary", "sad", "rescue", "abuse"
        ],
        "description": "Cute and funny animal moments"
    },
    "🐶 Funny Pets": {
        "keywords": [
            "funny dogs", "funny cats", "pet fails",
            "funny pet videos", "dogs being silly",
            "cats being funny", "pet compilation"
        ],
        "avoid": [
            "animation", "cartoon", "drawing", "tutorial", "review",
            "documentary", "sad", "rescue", "abuse"
        ],
        "description": "Funny pet moments"
    },
    "🐼 Baby Animals": {
        "keywords": [
            "baby animals", "cute baby animals", "puppy videos",
            "kitten videos", "baby panda", "baby elephant",
            "adorable baby animals"
        ],
        "avoid": [
            "animation", "cartoon", "drawing", "tutorial", "review",
            "documentary", "sad", "rescue", "abuse"
        ],
        "description": "Adorable baby animals"
    },
    "🦁 Wildlife": {
        "keywords": [
            "wildlife moments", "amazing animals", "wild animals",
            "safari footage", "animal attack", "predator hunting",
            "wildlife compilation"
        ],
        "avoid": [
            "animation", "cartoon", "drawing", "tutorial", "review",
            "documentary", "movie", "trailer"
        ],
        "description": "Wildlife and nature moments"
    },
    "🚢 Ship Accidents": {
        "keywords": [
            "ship sinking", "boat accident", "ship crash",
            "maritime disaster", "ship accident caught on camera",
            "boat sinking footage", "ship collision"
        ],
        "avoid": [
            "animation", "simulation", "game", "tutorial", "review",
            "documentary", "movie", "trailer", "music"
        ],
        "description": "Ship and maritime accidents"
    },
    "🚂 Train Accidents": {
        "keywords": [
            "train crash", "train accident", "railway accident",
            "train derailment", "train collision",
            "railway disaster", "train accident caught on camera"
        ],
        "avoid": [
            "animation", "simulation", "game", "tutorial", "review",
            "documentary", "movie", "trailer", "music"
        ],
        "description": "Train crashes and railway accidents"
    },
    "🌊 Natural Disasters": {
        "keywords": [
            "earthquake footage", "tsunami waves", "natural disaster",
            "flood caught on camera", "hurricane footage",
            "volcano eruption", "disaster compilation"
        ],
        "avoid": [
            "animation", "simulation", "game", "tutorial", "review",
            "documentary", "movie", "trailer", "music"
        ],
        "description": "Natural disasters and extreme weather"
    },
    "🏍️ Extreme Sports": {
        "keywords": [
            "extreme sports fails", "skateboard crash", "snowboard accident",
            "surfing wipeout", "motocross crash", "extreme sports compilation",
            "sports fails caught on camera"
        ],
        "avoid": [
            "animation", "simulation", "game", "tutorial", "review",
            "documentary", "movie", "trailer", "music"
        ],
        "description": "Extreme sports fails and accidents"
    }
}

# ============================================
# STREAMLIT UI
# ============================================

# Initialize session state
if 'segments' not in st.session_state:
    st.session_state.segments = []
if 'final_video' not in st.session_state:
    st.session_state.final_video = None
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'progress' not in st.session_state:
    st.session_state.progress = {}
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'custom_keywords' not in st.session_state:
    st.session_state.custom_keywords = []
if 'custom_avoid' not in st.session_state:
    st.session_state.custom_avoid = []
if 'selected_topic' not in st.session_state:
    st.session_state.selected_topic = "🐱 Cute Animals"

# Header
st.markdown("""
<div class="main-header">
    <h1>🎬 POV Master Engine v3</h1>
    <p>AI-Powered Video Compilation - Không giới hạn YouTube API</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Số scenes
    num_scenes = st.slider(
        "Number of Scenes",
        min_value=10,
        max_value=120,
        value=20,
        step=5,
        help="10 scenes = 50 giây, 120 scenes = 10 phút"
    )
    
    # Hiển thị thời gian ước tính
    estimated_time = num_scenes * 5
    st.info(f"⏱️ Final video: ~{estimated_time} seconds ({estimated_time//60}:{estimated_time%60:02d})")
    
    # Thời gian xử lý ước tính
    processing_time = num_scenes * 15  # ~15 giây mỗi scene
    st.warning(f"⚡ Processing time: ~{processing_time//60} phút")
    
    st.markdown("---")
    
    # Chất lượng video
    video_quality = st.selectbox(
        "Video Quality",
        options=["480p (nhanh)", "720p (cân bằng)", "1080p (chậm)"],
        index=1
    )
    
    # Toggle chống trùng
    enable_dedup = st.checkbox("Chống trùng lặp", value=True)
    
    st.markdown("---")
    st.header("📊 Stats")
    
    if st.session_state.segments:
        st.metric("Segments tìm được", len(st.session_state.segments))
    else:
        st.metric("Segments tìm được", 0)

# Main content
# Topic selection
st.header("🎯 Chọn Chủ đề")

# Grid layout cho topics
col1, col2, col3, col4, col5 = st.columns(5)

topic_list = list(TOPIC_TEMPLATES.keys())

# Hiển thị topics trong grid
for i, topic_name in enumerate(topic_list[:10]):  # Hiển thị 10 topics đầu
    col = [col1, col2, col3, col4, col5][i % 5]
    
    with col:
        emoji = topic_name.split()[0]
        name = ' '.join(topic_name.split()[1:])
        
        is_selected = st.session_state.selected_topic == topic_name
        
        if st.button(
            f"{emoji}\n{name}",
            key=f"topic_{i}",
            use_container_width=True,
            type="primary" if is_selected else "secondary"
        ):
            st.session_state.selected_topic = topic_name
            st.rerun()

st.markdown("---")

# Hiển thị topic đã chọn
selected_topic = st.session_state.selected_topic
topic_config = TOPIC_TEMPLATES.get(selected_topic, TOPIC_TEMPLATES["🐱 Cute Animals"])

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"Chủ đề: {selected_topic}")
    st.write(f"**Mô tả:** {topic_config['description']}")
    
    # Hiển thị keywords
    st.write("**Keywords tìm kiếm:**")
    for kw in topic_config['keywords'][:5]:
        st.markdown(f'<span class="keyword-tag">🔍 {kw}</span>', unsafe_allow_html=True)
    
    # Hiển thị avoid keywords
    st.write("**Tránh:**")
    for kw in topic_config['avoid'][:5]:
        st.markdown(f'<span class="avoid-tag">🚫 {kw}</span>', unsafe_allow_html=True)

with col2:
    st.subheader("🎨 Tùy chỉnh")
    
    # Thêm keywords tùy chỉnh
    custom_keyword = st.text_input(
        "Thêm keyword tìm kiếm",
        placeholder="e.g., funny animal fails"
    )
    
    if st.button("➕ Thêm keyword", use_container_width=True):
        if custom_keyword and custom_keyword not in st.session_state.custom_keywords:
            st.session_state.custom_keywords.append(custom_keyword)
            st.success(f"✅ Đã thêm: {custom_keyword}")
    
    # Thêm avoid keywords
    custom_avoid = st.text_input(
        "Thêm keyword tránh",
        placeholder="e.g., sad, rescue"
    )
    
    if st.button("🚫 Thêm keyword tránh", use_container_width=True):
        if custom_avoid and custom_avoid not in st.session_state.custom_avoid:
            st.session_state.custom_avoid.append(custom_avoid)
            st.success(f"✅ Đã thêm: {custom_avoid}")
    
    # Xóa keywords
    if st.session_state.custom_keywords:
        st.write("**Keywords đã thêm:**")
        for kw in st.session_state.custom_keywords:
            st.markdown(f'<span class="keyword-tag">🔍 {kw}</span>', unsafe_allow_html=True)
        
        if st.button("🗑️ Xóa tất cả keywords tùy chỉnh", use_container_width=True):
            st.session_state.custom_keywords = []
            st.rerun()
    
    if st.session_state.custom_avoid:
        st.write("**Tránh đã thêm:**")
        for kw in st.session_state.custom_avoid:
            st.markdown(f'<span class="avoid-tag">🚫 {kw}</span>', unsafe_allow_html=True)
        
        if st.button("🗑️ Xóa tất cả tránh tùy chỉnh", use_container_width=True):
            st.session_state.custom_avoid = []
            st.rerun()

st.markdown("---")

# Generate button
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    if st.button("🚀 TẠO VIDEO NGAY", use_container_width=True, type="primary"):
        st.session_state.processing = True
        st.session_state.segments = []
        st.session_state.final_video = None
        st.session_state.logs = []
        st.session_state.progress = {}
        
        # Kết hợp keywords
        all_keywords = topic_config['keywords'] + st.session_state.custom_keywords
        all_avoid = topic_config['avoid'] + st.session_state.custom_avoid
        
        # Khởi tạo engine
        engine = POVMasterEngineV3()
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Tạo scenes
        scenes = []
        for i in range(num_scenes):
            # Tạo variation của keywords
            if i >= len(all_keywords):
                # Reuse keywords với variation
                base_kw = all_keywords[i % len(all_keywords)]
                keywords = [f"{base_kw} {i//len(all_keywords) + 1}", base_kw]
            else:
                keywords = [all_keywords[i], all_keywords[i % len(all_keywords)]]
            
            scene = SceneConfig(
                scene_id=i + 1,
                keywords=keywords,
                avoid_keywords=all_avoid,
                description=f"{selected_topic} - Scene {i+1}"
            )
            scenes.append(scene)
        
        # Xử lý từng scene
        for i, scene in enumerate(scenes):
            status_text.text(f"🔄 Đang xử lý scene {i+1}/{num_scenes}...")
            st.session_state.progress[i] = {
                'scene_id': i + 1,
                'status': 'processing'
            }
            
            segment = engine.process_scene(scene)
            
            if segment:
                st.session_state.segments.append(segment)
                st.session_state.progress[i]['status'] = 'complete'
                st.session_state.logs.append(f"✅ Scene {i+1}: Tìm thấy segment")
            else:
                st.session_state.progress[i]['status'] = 'error'
                st.session_state.logs.append(f"⚠️ Scene {i+1}: Không tìm thấy")
            
            progress_bar.progress((i + 1) / num_scenes)
        
        # Ghép segments
        if st.session_state.segments:
            status_text.text("🔗 Đang ghép video...")
            st.session_state.final_video = engine.concatenate_segments()
            st.session_state.logs.append("✅ Video hoàn thành!")
        
        st.session_state.processing = False
        progress_bar.progress(1.0)
        status_text.text("✅ Hoàn thành!")
        
        st.rerun()

# Hiển thị kết quả
if st.session_state.segments:
    st.markdown("---")
    st.header("📊 Kết quả")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Scenes yêu cầu", num_scenes)
    
    with col2:
        st.metric("Segments tìm được", len(st.session_state.segments))
    
    with col3:
        success_rate = (len(st.session_state.segments) / num_scenes) * 100
        st.metric("Tỉ lệ thành công", f"{success_rate:.1f}%")
    
    with col4:
        duration = len(st.session_state.segments) * 5
        st.metric("Độ dài", f"{duration}s")
    
    # Logs
    st.subheader("📝 Logs")
    for log in st.session_state.logs[-10:]:  # 10 logs cuối
        if log.startswith("✅"):
            st.success(log)
        elif log.startswith("⚠️"):
            st.warning(log)
        else:
            st.info(log)

# Final video
if st.session_state.final_video and os.path.exists(st.session_state.final_video):
    st.markdown("---")
    st.header("🎥 Video Hoàn Chỉnh")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.video(st.session_state.final_video)
    
    with col2:
        st.subheader("⬇️ Download")
        
        with open(st.session_state.final_video, "rb") as f:
            video_bytes = f.read()
        
        st.download_button(
            label="📥 Tải Video",
            data=video_bytes,
            file_name=f"compilation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            mime="video/mp4",
            use_container_width=True
        )
        
        file_size = os.path.getsize(st.session_state.final_video) / (1024 * 1024)
        st.info(f"📦 Kích thước: {file_size:.1f} MB")
        
        # Thống kê segments
        st.subheader("📊 Chi tiết")
        for seg in st.session_state.segments[:10]:
            st.caption(f"Scene {seg.scene_id}: {seg.source_title[:30]}...")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <p>🎬 POV Master Engine v3</p>
    <p>⚡ Không cần YouTube API - Dùng yt-dlp trực tiếp</p>
    <p>⚠️ Chỉ sử dụng footage bạn có quyền sử dụng</p>
</div>
""", unsafe_allow_html=True)
