import yt_dlp
from typing import Dict, Any, Optional, Tuple
import requests
import webvtt
import tempfile
import os
import logging
from urllib.parse import urlparse
from pathlib import Path
from supabase import create_client
from supabase.client import Client
from dotenv import load_dotenv
import re
import uuid
import asyncio

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL', ''),
    os.getenv('SUPABASE_ANON_KEY', '')
)

class VideoMetadataExtractor:
    def __init__(self):
        self.base_opts = {
            'quiet': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
            'no_warnings': True,
        }
        
        self.youtube_opts = {
            **self.base_opts,
            'extract_flat': True,
            'force_generic_extractor': False,
        }
        
        self.tiktok_opts = {
            **self.base_opts,
            'extract_flat': False,
            'force_generic_extractor': False,
            'extractor_args': {'tiktok': {'api-hostname': 'api16-normal-c-useast1a.tiktokv.com'}},
            'format': 'best'
        }

        self.instagram_opts = {
            **self.base_opts,
            'extract_flat': False,
            'force_generic_extractor': False,
            'format': 'best',
        }

    def get_domain(self, url: str) -> str:
        """Extract the domain from the URL."""
        domain = urlparse(url).netloc.lower()
        if any(tiktok in domain for tiktok in ['tiktok.com', 'vm.tiktok']):
            return 'tiktok'
        elif any(youtube in domain for youtube in ['youtube.com', 'youtu.be']):
            return 'youtube'
        elif 'instagram.com' in domain:
            return 'instagram'
        else:
            return 'unknown'

    def download_and_parse_subtitles(self, subtitle_url: str) -> str:
        try:
            # Download the subtitle file
            response = requests.get(subtitle_url)
            if response.status_code != 200:
                return ""
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.vtt', delete=False) as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
            # Parse the VTT file
            subtitle_texts = []
            try:
                for caption in webvtt.read(tmp_path):
                    subtitle_texts.append(caption.text)
            finally:
                # Clean up temporary file
                os.unlink(tmp_path)
            
            return ' '.join(subtitle_texts)
        except Exception as e:
            logger.error(f"Error downloading/parsing subtitles: {str(e)}")
            return ""

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for Supabase storage by:
        1. Removing special characters and spaces
        2. Converting to lowercase
        3. Adding a unique identifier to prevent collisions
        """
        # Get the name and extension
        name, ext = os.path.splitext(filename)
        
        # Remove special characters and spaces, convert to lowercase
        # Only allow alphanumeric, dash, and underscore
        sanitized_name = re.sub(r'[^a-zA-Z0-9\-_]', '_', name.lower().strip())
        
        # Remove multiple consecutive underscores
        sanitized_name = re.sub(r'_+', '_', sanitized_name)
        
        # Add a unique identifier
        unique_id = str(uuid.uuid4())[:8]
        
        # Combine everything
        return f"{sanitized_name}_{unique_id}{ext}"

    async def download_video(self, video_url: str, output_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Download a video from the given URL and upload it to Supabase storage.
        
        Args:
            video_url: The URL of the video to download
            output_path: Optional path for temporary storage. If not provided, 
                        will create a temporary directory.
        
        Returns:
            Tuple of (success: bool, storage_url: str)
        """
        try:
            # Create a temporary directory for downloading
            with tempfile.TemporaryDirectory() as temp_dir:
                domain = self.get_domain(video_url)
                
                # Configure download options
                download_opts = {
                    **self.base_opts,
                    'format': 'best',  # Get the best quality
                    'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                    'quiet': False,  # Show download progress
                }
                
                # Add domain-specific options
                if domain == 'tiktok':
                    download_opts.update(self.tiktok_opts)
                elif domain == 'instagram':
                    download_opts.update(self.instagram_opts)
                
                # Download video in a separate thread to not block the event loop
                loop = asyncio.get_event_loop()
                video_info = await loop.run_in_executor(None, self._download_video, video_url, download_opts)
                
                if not video_info or not video_info.get('video_path'):
                    logger.error("No information extracted from the URL")
                    return False, ""
                
                video_path = video_info['video_path']
                logger.info(f"Video downloaded successfully to: {video_path}")
                
                # Upload to Supabase storage
                try:
                    with open(video_path, 'rb') as f:
                        # First sanitize the filename
                        original_filename = os.path.basename(video_path)
                        sanitized_filename = self._sanitize_filename(original_filename)
                        
                        # Ensure the storage path is clean
                        storage_path = f"videos/{sanitized_filename}"
                        logger.info(f"Uploading to Supabase storage with path: {storage_path}")
                        
                        # Upload to Supabase storage bucket using run_in_executor for blocking operation
                        try:
                            # Create a function that captures the upload operation
                            def upload_to_supabase():
                                return supabase.storage.from_('home-yum').upload(
                                    path=storage_path,
                                    file=f,
                                    file_options={"content-type": "video/mp4"}
                                )
                            
                            # Run the upload in a separate thread
                            result = await loop.run_in_executor(None, upload_to_supabase)
                            
                            # Get the public URL (this is synchronous and fast, no need for executor)
                            public_url = supabase.storage.from_('home-yum').get_public_url(storage_path)
                            logger.info(f"Video uploaded to Supabase storage: {public_url}")
                            
                            return True, public_url
                            
                        except Exception as upload_error:
                            logger.error(f"Supabase upload error - Path: {storage_path}, Error: {str(upload_error)}")
                            return False, ""
                            
                except Exception as e:
                    logger.error(f"Error uploading to Supabase storage: {str(e)}")
                    return False, ""
                
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            return False, ""

    def _download_video(self, video_url: str, download_opts: dict) -> Dict[str, Any]:
        """Helper method to download video using yt-dlp in a separate thread."""
        try:
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if not info:
                    return {}
                
                return {
                    'video_path': ydl.prepare_filename(info),
                    'info': info
                }
        except Exception as e:
            logger.error(f"Error in _download_video: {str(e)}")
            return {}

    async def extract_metadata(self, video_url: str, download_video: bool = False, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract metadata from a video URL and optionally download the video.
        
        Args:
            video_url: The URL of the video
            download_video: Whether to also download the video file
            output_path: Optional path where to save the video if downloading
        """
        try:
            logger.info(f"Attempting to extract metadata from URL: {video_url}")
            
            # Get basic metadata first
            result = await self._extract_basic_metadata(video_url)
            
            # Download video if requested
            if download_video:
                success, video_path = await self.download_video(video_url, output_path)
                if success:
                    result['video_path'] = video_path
                else:
                    result['video_path'] = None
                    logger.warning("Failed to download video file")
            
            return result
                    
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    async def _extract_basic_metadata(self, video_url: str) -> Dict[str, Any]:
        """Internal method to extract basic metadata without downloading."""
        domain = self.get_domain(video_url)
        logger.info(f"Detected domain type: {domain}")
        
        if domain == 'unknown':
            logger.error("Unsupported URL domain")
            return {}
        
        # Select the appropriate options based on the domain
        if domain == 'tiktok':
            ydl_opts = self.tiktok_opts
        elif domain == 'instagram':
            ydl_opts = self.instagram_opts
        else:
            ydl_opts = self.youtube_opts
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    logger.error("No information extracted from the URL")
                    return {}
                
                logger.info("Successfully extracted basic metadata")
                
                # Extract and process subtitles if available
                subtitle_text = ""
                if 'subtitles' in info and 'eng-US' in info['subtitles']:
                    subs = info['subtitles']['eng-US']
                    if isinstance(subs, list) and len(subs) > 0 and 'url' in subs[0]:
                        subtitle_text = self.download_and_parse_subtitles(subs[0]['url'])
                
                result = {
                    'title': info.get('title', ''),
                    'description': info.get('description', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'comment_count': info.get('comment_count', 0),
                    'subtitle_text': subtitle_text,
                    'thumbnail': info.get('thumbnail', ''),
                    'webpage_url': info.get('webpage_url', video_url),
                    'platform': domain
                }
                
                logger.info(f"Found title: {result['title']}")
                logger.info(f"Found description length: {len(result['description'])}")
                
                return result
                
            except yt_dlp.utils.DownloadError as de:
                logger.error(f"yt-dlp download error: {str(de)}")
                return {}