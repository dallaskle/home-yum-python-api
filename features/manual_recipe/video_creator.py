import logging
import cv2
import numpy as np
from typing import Dict, Any, List
import os
import tempfile
import aiohttp
import asyncio
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

class VideoCreator:
    def __init__(self):
        """Initialize the VideoCreator with default settings."""
        self.frame_rate = 1  # 1 frame per second for slideshow
        self.resolution = (1080, 1920)  # 1080p vertical video
        self.duration_per_image = 3  # seconds per image
        self.transition_frames = 30  # number of frames for transition
        
    def create_transition(self, img1: np.ndarray, img2: np.ndarray, num_frames: int) -> List[np.ndarray]:
        """Create a smooth transition between two images."""
        frames = []
        for i in range(num_frames):
            alpha = i / num_frames
            blended = cv2.addWeighted(img1, 1 - alpha, img2, alpha, 0)
            frames.append(blended)
        return frames
        
    def resize_image(self, image_path: str) -> np.ndarray:
        """Resize image to video resolution while maintaining aspect ratio."""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
            
        # Calculate scaling factor to fit within resolution
        h, w = img.shape[:2]
        target_h, target_w = self.resolution
        
        scale = min(target_w/w, target_h/h)
        new_w, new_h = int(w * scale), int(h * scale)
        
        # Resize image
        resized = cv2.resize(img, (new_w, new_h))
        
        # Create black background
        background = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        
        # Calculate position to center image
        y_offset = (target_h - new_h) // 2
        x_offset = (target_w - new_w) // 2
        
        # Place image on background
        background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        
        return background

    async def download_image(self, url: str, temp_dir: str) -> str:
        """Download an image from URL to temporary directory."""
        try:
            # Generate unique filename
            filename = f"{uuid.uuid4().hex}.webp"
            filepath = os.path.join(temp_dir, filename)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise ValueError(f"Failed to download image from {url}")
                    
                    # Save image to temp file
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
            
            return filepath
        except Exception as e:
            logger.error(f"Error downloading image from {url}: {str(e)}")
            raise

    async def create_slideshow(self, ingredient_images: List[Dict[str, Any]], final_image: Dict[str, Any]) -> Dict[str, Any]:
        """Create a slideshow video from ingredient images and final meal image."""
        temp_dir = None
        output_path = None
        
        try:
            logger.info("Creating slideshow video from images")
            
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            logger.info(f"Created temporary directory: {temp_dir}")
            
            # Sort ingredient images by order
            sorted_images = sorted(ingredient_images, key=lambda x: x['order'])
            
            # Download all images
            download_tasks = [
                self.download_image(img['url'], temp_dir) for img in sorted_images
            ]
            download_tasks.append(self.download_image(final_image['url'], temp_dir))
            
            # Wait for all downloads to complete
            local_image_paths = await asyncio.gather(*download_tasks)
            
            # Calculate video parameters
            total_images = len(local_image_paths)
            frames_per_image = self.duration_per_image * self.frame_rate
            total_frames = (total_images * frames_per_image) + (self.transition_frames * (total_images - 1))
            total_duration = total_frames / self.frame_rate
            
            # Create output directory if it doesn't exist
            output_dir = "output_videos"
            os.makedirs(output_dir, exist_ok=True)
            
            # Create unique output filename
            output_path = os.path.join(output_dir, f"recipe_slideshow_{uuid.uuid4().hex}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, self.frame_rate, self.resolution)
            
            try:
                # Process each image
                for i in range(len(local_image_paths)):
                    current_img = self.resize_image(local_image_paths[i])
                    
                    # Write frames for current image
                    for _ in range(frames_per_image):
                        out.write(current_img)
                    
                    # Add transition to next image if not the last image
                    if i < len(local_image_paths) - 1:
                        next_img = self.resize_image(local_image_paths[i + 1])
                        transition_frames = self.create_transition(current_img, next_img, self.transition_frames)
                        
                        for frame in transition_frames:
                            out.write(frame)
                
            finally:
                out.release()
            
            # Get video file size
            video_size = os.path.getsize(output_path)
            
            return {
                "success": True,
                "video_url": output_path,
                "duration": total_duration,
                "size": video_size,
                "resolution": self.resolution,
                "frame_rate": self.frame_rate
            }
            
        except Exception as e:
            logger.error(f"Error creating slideshow video: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
        finally:
            # Clean up temporary files
            if temp_dir and os.path.exists(temp_dir):
                try:
                    for file in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, file))
                    os.rmdir(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary directory: {str(e)}") 