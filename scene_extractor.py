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
        including timestamps and image paths
        
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
            
            # Create a subdirectory for images in the temp directory
            images_dir = os.path.join(self.temp_dir, 'scenes')
            os.makedirs(images_dir, exist_ok=True)
            
            # Detect scenes
            logger.info("Detecting scenes...")
            scene_list = detect(video_path, ContentDetector(threshold=threshold))
            
            if not scene_list:
                logger.warning("No scenes detected in video")
                return []
            
            logger.info(f"Found {len(scene_list)} scenes")
            
            # Save scene images
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
                    # Save the frame
                    image_path = os.path.join(images_dir, f'scene_{i:03d}.jpg')
                    cv2.imwrite(image_path, frame)
                    
                    # Read the image back as bytes
                    with open(image_path, 'rb') as img_file:
                        image_bytes = img_file.read()
                    
                    scene_info = {
                        'scene_number': i,
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': end_time - start_time,
                        'image_data': image_bytes
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