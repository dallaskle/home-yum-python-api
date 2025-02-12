import logging
import cv2
import numpy as np
from typing import Dict, Any, List
import os

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

    async def create_slideshow(self, ingredient_images: List[Dict[str, Any]], final_image: Dict[str, Any]) -> Dict[str, Any]:
        """Create a slideshow video from ingredient images and final meal image."""
        try:
            logger.info("Creating slideshow video from images")
            
            # Sort ingredient images by order
            sorted_images = sorted(ingredient_images, key=lambda x: x['order'])
            
            # Add final image to the sequence
            image_sequence = [img['url'] for img in sorted_images] + [final_image['url']]
            
            # Calculate video parameters
            total_images = len(image_sequence)
            frames_per_image = self.duration_per_image * self.frame_rate
            total_frames = (total_images * frames_per_image) + (self.transition_frames * (total_images - 1))
            total_duration = total_frames / self.frame_rate
            
            # Create video writer
            output_path = "recipe_slideshow.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, self.frame_rate, self.resolution)
            
            try:
                # Process each image
                for i in range(len(image_sequence)):
                    current_img = self.resize_image(image_sequence[i])
                    
                    # Write frames for current image
                    for _ in range(frames_per_image):
                        out.write(current_img)
                    
                    # Add transition to next image if not the last image
                    if i < len(image_sequence) - 1:
                        next_img = self.resize_image(image_sequence[i + 1])
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