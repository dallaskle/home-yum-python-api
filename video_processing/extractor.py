import yt_dlp
from typing import Dict, Any, Optional, Tuple
import requests
import webvtt
import tempfile
import os
import logging
from urllib.parse import urlparse
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    def download_video(self, video_url: str, output_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Download a video from the given URL.
        
        Args:
            video_url: The URL of the video to download
            output_path: Optional path where to save the video. If not provided, 
                        will create a videos directory in the current path.
        
        Returns:
            Tuple of (success: bool, file_path: str)
        """
        try:
            if output_path is None:
                # Create a videos directory if it doesn't exist
                output_dir = Path('videos')
                output_dir.mkdir(exist_ok=True)
                output_path = str(output_dir)

            domain = self.get_domain(video_url)
            
            # Configure download options
            download_opts = {
                **self.base_opts,
                'format': 'best',  # Get the best quality
                'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                'quiet': False,  # Show download progress
            }
            
            # Add domain-specific options
            if domain == 'tiktok':
                download_opts.update(self.tiktok_opts)
            elif domain == 'instagram':
                download_opts.update(self.instagram_opts)
            
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if not info:
                    logger.error("No information extracted from the URL")
                    return False, ""
                
                # Get the path of the downloaded file
                video_path = ydl.prepare_filename(info)
                logger.info(f"Video downloaded successfully to: {video_path}")
                return True, video_path
                
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            return False, ""

    def extract_metadata(self, video_url: str, download_video: bool = False, output_path: Optional[str] = None) -> Dict[str, Any]:
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
            result = self._extract_basic_metadata(video_url)
            
            # Download video if requested
            if download_video:
                success, video_path = self.download_video(video_url, output_path)
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

    def _extract_basic_metadata(self, video_url: str) -> Dict[str, Any]:
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