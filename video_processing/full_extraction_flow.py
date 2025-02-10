import logging
import os
import json
import asyncio
from typing import Dict, Any, Optional
from video_processing.extractor import TikTokMetadataExtractor
from video_processing.whisper_extractor import WhisperExtractor
from video_processing.video_recipe_analyzer import VideoRecipeAnalyzer
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FullExtractionFlow:
    def __init__(self):
        """Initialize all extractors and analyzers."""
        self.metadata_extractor = TikTokMetadataExtractor()
        self.whisper_extractor = WhisperExtractor()
        self.video_analyzer = VideoRecipeAnalyzer()
        self.chat_model = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        )

        # Define the final verification prompt
        self.verification_prompt = """I have extracted information from a cooking video using multiple methods. Please analyze all the data and provide the most accurate recipe possible.

Metadata and Subtitles:
{metadata_info}

Audio Transcription:
{audio_transcription}

Video Analysis Results:
{video_analysis}

Based on all this information, please:
1. Verify if the video analysis results are accurate and complete
2. Provide the most complete and accurate recipe using all available information
3. Include any additional context or notes that might be helpful (timing, temperature, etc.)

Please format your response as follows:

**Ingredients:**
[List all ingredients with quantities when available]

**Directions:**
[Step-by-step instructions]

**Notes:**
[Any additional tips, timing information, or important context]"""

    async def _extract_metadata(self, video_url: str) -> Dict[str, Any]:
        """Extract metadata and subtitles asynchronously."""
        return self.metadata_extractor.extract_metadata(video_url)

    async def _extract_audio_transcript(self, video_url: str) -> Any:
        """Extract audio transcript asynchronously."""
        return self.whisper_extractor.extract_transcript(video_url)

    async def extract_all(self, video_url: str) -> Dict[str, Any]:
        """
        Run the full extraction flow on a video URL.
        
        Args:
            video_url (str): URL of the video to analyze
            
        Returns:
            Dict[str, Any]: Complete analysis results
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs('output', exist_ok=True)
            
            # Run metadata extraction and audio transcription concurrently
            # These can run in parallel as they don't depend on each other
            logger.info("Starting metadata extraction and audio transcription...")
            metadata_task = asyncio.create_task(self._extract_metadata(video_url))
            audio_task = asyncio.create_task(self._extract_audio_transcript(video_url))
            
            # Wait for both tasks to complete
            metadata, audio_result = await asyncio.gather(metadata_task, audio_task)
            
            # Video analysis needs to run after metadata extraction as it might use that information
            logger.info("Starting video analysis...")
            video_analysis = await self.video_analyzer.analyze_video(video_url)
            
            # Prepare data for final verification
            logger.info("Preparing final verification...")
            
            metadata_info = f"""
Title: {metadata.get('title', 'N/A')}
Description: {metadata.get('description', 'N/A')}
Duration: {metadata.get('duration', 'N/A')} seconds
Subtitles: {metadata.get('subtitle_text', 'N/A')}
"""

            # Handle Whisper transcription result
            audio_transcription = ""
            if audio_result:
                if hasattr(audio_result, 'text'):
                    audio_transcription = audio_result.text
                elif isinstance(audio_result, dict):
                    audio_transcription = audio_result.get('text', "No transcription available")
                else:
                    audio_transcription = str(audio_result)
            else:
                audio_transcription = "No audio transcription available"
            
            video_analysis_text = video_analysis.get('final_recipe') if video_analysis.get('success') else "Video analysis failed"

            # Final verification
            logger.info("Performing final verification...")
            verification_message = HumanMessage(
                content=self.verification_prompt.format(
                    metadata_info=metadata_info,
                    audio_transcription=audio_transcription,
                    video_analysis=video_analysis_text
                )
            )
            
            final_response = self.chat_model.invoke([verification_message])
            
            # Write all results to output file
            with open('output/full_output.txt', 'w') as f:
                f.write("=== Video Information ===\n")
                f.write(f"URL: {video_url}\n\n")
                f.write("=== Metadata and Subtitles ===\n")
                f.write(json.dumps(metadata, indent=2))
                f.write("\n\n=== Audio Transcription ===\n")
                f.write(audio_transcription)
                f.write("\n\n=== Video Analysis ===\n")
                f.write(json.dumps(video_analysis, indent=2))
                f.write("\n\n=== Final Recipe ===\n")
                f.write(final_response.content)
            
            return {
                'success': True,
                'metadata': metadata,
                'audio_transcription': audio_transcription,
                'video_analysis': video_analysis,
                'final_recipe': final_response.content
            }
            
        except Exception as e:
            logger.error(f"Error in full extraction flow: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            } 