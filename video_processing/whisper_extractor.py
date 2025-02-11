import yt_dlp
import tempfile
import os
from openai import OpenAI
import logging
from typing import Optional
from langsmith import traceable
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhisperExtractor:
    @traceable(name="initialize_whisper_extractor")
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the WhisperExtractor with OpenAI API key.
        
        Args:
            api_key: OpenAI API key. If not provided, will look for OPENAI_API_KEY in environment.
        """
        self.client = OpenAI(api_key=api_key)
        
        # Configure yt-dlp options for audio extraction
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'outtmpl': {
                'default': '%(id)s.%(ext)s',
                'subtitle': '%(id)s.%(ext)s'
            }
        }

    @traceable(name="download_audio")
    def download_audio(self, video_url: str) -> Optional[str]:
        """Download audio from video URL using yt-dlp.
        
        Args:
            video_url: URL of the video to extract audio from
            
        Returns:
            Path to downloaded audio file or None if download fails
        """
        temp_dir = None
        try:
            # Create a temporary directory
            temp_dir = tempfile.mkdtemp()
            
            # Update output template to use temp directory
            self.ydl_opts['outtmpl'] = {
                'default': os.path.join(temp_dir, '%(id)s.%(ext)s'),
                'subtitle': os.path.join(temp_dir, '%(id)s.%(ext)s')
            }
            
            # Download audio
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if not info:
                    logger.error("No information extracted from video URL")
                    return None
                    
                # Get the video ID and construct the audio path
                video_id = info['id']
                # Note: After FFmpeg post-processing, the extension will be mp3
                audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
                
                if not os.path.exists(audio_path):
                    logger.error(f"Audio file not found at expected path: {audio_path}")
                    return None
                    
                logger.info(f"Audio downloaded successfully to: {audio_path}")
                return audio_path
                    
        except Exception as e:
            logger.error(f"Error downloading audio: {str(e)}")
            return None

    @traceable(name="transcribe_audio")
    def transcribe_audio(self, audio_path: str, prompt: Optional[str] = None) -> Optional[dict]:
        """Transcribe audio file using OpenAI Whisper API.
        
        Args:
            audio_path: Path to audio file to transcribe
            prompt: Optional prompt to guide the transcription
            
        Returns:
            Transcription result or None if transcription fails
        """
        try:
            if not os.path.exists(audio_path):
                logger.error(f"Audio file not found at: {audio_path}")
                return None
                
            with open(audio_path, "rb") as audio_file:
                # Call Whisper API
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    prompt=prompt
                )
                return response
                
        except Exception as e:
            logger.error(f"Error transcribing audio: {str(e)}")
            return None

    @traceable(name="extract_transcript")
    def extract_transcript(self, video_url: str, prompt: Optional[str] = None) -> Optional[dict]:
        """Extract transcript from video URL using Whisper.
        
        Args:
            video_url: URL of video to transcribe
            prompt: Optional prompt to guide the transcription
            
        Returns:
            Transcription result or None if extraction fails
        """
        temp_dir = None
        audio_path = None
        try:
            # Download audio from video
            audio_path = self.download_audio(video_url)
            if not audio_path:
                logger.error("Failed to download audio")
                return None
                
            # Transcribe the audio
            result = self.transcribe_audio(audio_path, prompt)
            if not result:
                logger.error("Failed to transcribe audio")
                return None
                
            return result
                
        except Exception as e:
            logger.error(f"Error extracting transcript: {str(e)}")
            return None
        finally:
            # Clean up the audio file if it exists
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.info(f"Cleaned up audio file: {audio_path}")
                except Exception as e:
                    logger.error(f"Error removing audio file: {str(e)}")
            
            # Clean up the temporary directory if it exists
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temp directory: {str(e)}")

# Example usage
if __name__ == "__main__":
    # Initialize extractor
    extractor = WhisperExtractor()
    
    # Example video URL
    video_url = "https://example.com/video"
    
    # Optional prompt to guide transcription
    prompt = "This is a video about..."
    
    # Extract transcript
    result = extractor.extract_transcript(video_url, prompt)
    
    if result:
        print("Transcription:", result.text)
        # Access word-level timestamps if needed
        if hasattr(result, 'words'):
            print("Word timestamps:", result.words) 