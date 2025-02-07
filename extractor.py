import yt_dlp
from typing import Dict, Any
import requests
import webvtt
import tempfile
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TikTokMetadataExtractor:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'extract_flat': False,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
            'force_generic_extractor': False,
            'no_warnings': True,
            'extractor_args': {'tiktok': {'api-hostname': 'api16-normal-c-useast1a.tiktokv.com'}},
            'format': 'best'
        }

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

    def extract_metadata(self, video_url: str) -> Dict[str, Any]:
        try:
            logger.info(f"Attempting to extract metadata from URL: {video_url}")
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
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
                        'webpage_url': info.get('webpage_url', video_url)
                    }
                    
                    # Log what we found
                    logger.info(f"Found title: {result['title']}")
                    logger.info(f"Found description length: {len(result['description'])}")
                    
                    return result
                    
                except yt_dlp.utils.DownloadError as de:
                    logger.error(f"yt-dlp download error: {str(de)}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {}