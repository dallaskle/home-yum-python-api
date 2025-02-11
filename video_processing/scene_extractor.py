import yt_dlp
import tempfile
import os
import logging
from typing import List, Dict, Any
from scenedetect import detect, ContentDetector, split_video_ffmpeg
from scenedetect.scene_manager import save_images
import cv2

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoSceneExtractor:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'format': 'best[ext=mp4]',  # Prefer MP4 format
            'outtmpl': '%(id)s.%(ext)s'
        }
        # Store temp directory as instance variable
        self.temp_dir = None
        # Target size for resized images
        self.target_width = 360
        self.target_height = 640

    def resize_image(self, frame):
        """
        Resize the image while maintaining aspect ratio
        """
        height, width = frame.shape[:2]
        
        # Calculate aspect ratio
        aspect = width / height
        
        # If image is portrait (taller than wide)
        if height > width:
            new_height = self.target_height
            new_width = int(new_height * aspect)
            if new_width > self.target_width:
                new_width = self.target_width
                new_height = int(new_width / aspect)
        else:
            new_width = self.target_width
            new_height = int(new_width / aspect)
            if new_height > self.target_height:
                new_height = self.target_height
                new_width = int(new_height * aspect)
        
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    def download_video(self, video_url: str) -> str:
        """
        Download video to a temporary location and return the path
        """
        try:
            # Create temp directory if it doesn't exist
            if not self.temp_dir:
                self.temp_dir = tempfile.mkdtemp()
            
            # Update options to use temporary directory
            self.ydl_opts['outtmpl'] = os.path.join(self.temp_dir, '%(id)s.%(ext)s')
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                logger.info("Downloading video...")
                info = ydl.extract_info(video_url, download=True)
                video_path = os.path.join(self.temp_dir, f"{info['id']}.{info.get('ext', 'mp4')}")
                logger.info(f"Video downloaded to: {video_path}")
                return video_path
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            raise

    def extract_scenes(self, video_url: str, threshold: float = 30.0) -> List[Dict[str, Any]]:
        """
        Extract scenes from a video URL and return a list of scene information
        including timestamps and image data
        
        Args:
            video_url: URL of the video to process
            threshold: Content detection threshold (default: 30.0)
            
        Returns:
            List of dictionaries containing scene information
        """
        try:
            # Download the video
            video_path = self.download_video(video_url)
            
            if not os.path.exists(video_path):
                logger.error(f"Downloaded video not found at: {video_path}")
                return []
            
            # Detect scenes
            logger.info("Detecting scenes...")
            scene_list = detect(video_path, ContentDetector(threshold=threshold))
            
            if not scene_list:
                logger.warning("No scenes detected in video")
                return []
            
            logger.info(f"Found {len(scene_list)} scenes")
            
            # Extract scene images
            scene_images = []
            video_cap = cv2.VideoCapture(video_path)
            fps = video_cap.get(cv2.CAP_PROP_FPS)
            
            for i, scene in enumerate(scene_list):
                # Calculate timestamp in seconds
                start_time = scene[0].get_seconds()
                end_time = scene[1].get_seconds()
                
                # Set video position to start of scene
                video_cap.set(cv2.CAP_PROP_POS_FRAMES, scene[0].get_frames())
                ret, frame = video_cap.read()
                
                if ret:
                    # Resize the frame
                    resized_frame = self.resize_image(frame)
                    
                    # Convert frame to JPEG bytes
                    success, buffer = cv2.imencode('.jpg', resized_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if not success:
                        logger.error(f"Failed to encode scene {i} image")
                        continue
                    
                    scene_info = {
                        'scene_number': i,
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': end_time - start_time,
                        'image_data': buffer.tobytes()
                    }
                    scene_images.append(scene_info)
            
            video_cap.release()
            return scene_images
                
        except Exception as e:
            logger.error(f"Error extracting scenes: {str(e)}")
            return []
        finally:
            # Clean up the temporary directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None

    def get_video_scenes(self, video_url: str) -> List[Dict[str, Any]]:
        """
        Main method to get scenes from a video URL
        
        Args:
            video_url: URL of the video to process
            
        Returns:
            List of dictionaries containing scene information and images
        """
        try:
            return self.extract_scenes(video_url)
        except Exception as e:
            logger.error(f"Error processing video: {str(e)}")
            return [] 