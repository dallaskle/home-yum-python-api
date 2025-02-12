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
from supabase import create_client
from supabase.client import Client
from dotenv import load_dotenv
import aiofiles
from firebase_admin import firestore

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL', ''),
    os.getenv('SUPABASE_ANON_KEY', '')
)

logger = logging.getLogger(__name__)

class VideoCreator:
    def __init__(self):
        """Initialize the VideoCreator with default settings."""
        self.frame_rate = 30  # 30 fps for smooth transitions
        self.resolution = (1080, 1920)  # 1080p vertical video
        self.duration_per_image = 1  # 1 second per image
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

    async def upload_to_supabase(self, video_path: str, recipe_title: str) -> str:
        """Upload video to Supabase storage and return public URL."""
        try:
            # Generate sanitized filename
            filename = f"recipe_video_{uuid.uuid4().hex}.mp4"
            storage_path = f"recipe_videos/{filename}"
            
            # Read video file
            async with aiofiles.open(video_path, 'rb') as f:
                file_content = await f.read()
            
            # Upload to Supabase storage
            supabase.storage.from_('home-yum').upload(
                path=storage_path,
                file=file_content,
                file_options={"content-type": "video/mp4"}
            )
            
            # Get public URL
            public_url = supabase.storage.from_('home-yum').get_public_url(storage_path)
            return public_url.split('?')[0] if '?' in public_url else public_url
            
        except Exception as e:
            logger.error(f"Error uploading to Supabase: {str(e)}")
            raise

    async def create_video_entry(self, user_id: str, video_url: str, recipe_data: Dict[str, Any]) -> str:
        """Create entry in videos table and return video ID."""
        try:
            db = firestore.client()
            
            # Create video data matching the Video interface from database.types.ts
            video_data = {
                "userId": user_id,
                "videoTitle": f"Recipe: {recipe_data['title']}",
                "videoDescription": recipe_data['description'],
                "mealName": recipe_data['title'],
                "mealDescription": recipe_data['description'],
                "videoUrl": video_url,
                "thumbnailUrl": recipe_data['mealImage']['url'],
                "duration": len(recipe_data['ingredients']) + 1,  # Duration in seconds
                "uploadedAt": firestore.SERVER_TIMESTAMP,
                "source": "manual_recipe",
                "userReaction": None,  # Optional field
                "tryListItem": None,   # Optional field
            }
            
            # Insert into videos collection
            doc_ref = db.collection('videos').document()
            doc_ref.set(video_data)
            
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Error creating video entry: {str(e)}")
            logger.error(f"Video data attempted: {video_data}")
            raise

    async def create_slideshow(self, ingredient_images: List[Dict[str, Any]], final_image: Dict[str, Any], user_id: str, recipe_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a slideshow video from ingredient images and final meal image."""
        temp_dir = None
        video_path = None
        
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
            
            # Rearrange image paths to show final image at start and end
            final_image_path = local_image_paths[-1]  # Last path is the final image
            ingredient_paths = local_image_paths[:-1]  # All but the last path are ingredients
            local_image_paths = [final_image_path] + ingredient_paths + [final_image_path]
            
            # Create unique output filename directly in temp directory
            video_path = os.path.join(temp_dir, f"recipe_slideshow_{uuid.uuid4().hex}.mp4")
            
            # Create a text file listing all images
            image_list_path = os.path.join(temp_dir, "image_list.txt")
            with open(image_list_path, 'w') as f:
                for img_path in local_image_paths:
                    # Each image should be shown for 1 second
                    f.write(f"file '{img_path}'\n")
                    f.write(f"duration {self.duration_per_image}\n")
                # Write the last image path again without duration (required by ffmpeg)
                f.write(f"file '{local_image_paths[-1]}'\n")
            
            # Use ffmpeg to create the video with crossfade transitions
            cmd = [
                'ffmpeg', '-y',  # Overwrite output file if it exists
                '-f', 'concat',  # Use concat demuxer
                '-safe', '0',    # Don't restrict file paths
                '-i', image_list_path,  # Input file list
                '-vf', f'fps={self.frame_rate},scale={self.resolution[0]}:{self.resolution[1]}:force_original_aspect_ratio=decrease,pad={self.resolution[0]}:{self.resolution[1]}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',  # Video filters
                '-c:v', 'libx264',  # Use H.264 codec
                '-preset', 'medium',  # Encoding preset (balance between speed and quality)
                '-movflags', '+faststart',  # Enable streaming
                '-pix_fmt', 'yuv420p',  # Pixel format for maximum compatibility
                video_path
            ]
            
            # Run ffmpeg
            import subprocess
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.returncode != 0:
                raise ValueError(f"Failed to create video: {process.stderr}")
            
            # Verify the video file exists and has content
            if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
                raise ValueError(f"Video file is invalid or too small: {video_path}")
                
            # Upload to Supabase and create database entry
            video_url = await self.upload_to_supabase(video_path, recipe_data['title'])
            video_id = await self.create_video_entry(user_id, video_url, recipe_data)
            
            return {
                "success": True,
                "video_url": video_url,
                "video_id": video_id,
                "duration": len(local_image_paths) * self.duration_per_image,
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
                        file_path = os.path.join(temp_dir, file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    os.rmdir(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary directory: {str(e)}") 