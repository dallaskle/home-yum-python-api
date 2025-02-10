import logging
import os
import json
from typing import List, Dict, Any
from video_processing.scene_extractor import VideoSceneExtractor
from video_processing.vision_analyzer import VisionAnalyzer
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoRecipeAnalyzer:
    def __init__(self):
        """Initialize the VideoRecipeAnalyzer with scene extractor and vision analyzer."""
        self.scene_extractor = VideoSceneExtractor()
        self.vision_analyzer = VisionAnalyzer()
        self.chat_model = ChatOpenAI(
            model="gpt-4o",
            max_tokens=1000,
            temperature=0
        )
        
        # Load the scene analysis prompt
        self.scene_prompt = """Below is a scene from a cooking video. Please analyze this scene and extract any details related to the recipe. In your answer, please provide:

- A list of ingredients that are visible or mentioned.
- Any cooking actions or techniques demonstrated (e.g., chopping, mixing, frying).
- Any contextual details that might indicate quantities or timings (if available).

Please be as concise as possible, using bullet points where applicable."""

        # Define the aggregate prompt
        self.aggregate_prompt = """I have extracted information from {scene_count} scenes of a cooking video. Below are the summarized details from each scene, including identified ingredients and cooking steps.

{scene_analyses}

Based on the above, please create a final consolidated list of ingredients (with any available quantities or notes, if mentioned) and a step-by-step set of instructions that form a complete recipe. Organize your answer clearly under two sections:

**Ingredients:**

**Directions:**

Please ensure that any duplicate ingredients are combined and the cooking steps are in a logical order."""

    async def _analyze_single_scene(self, scene: Dict[str, Any], scene_number: int) -> Dict[str, Any]:
        """Analyze a single scene from the video.
        
        Args:
            scene: Dictionary containing scene data
            scene_number: Index of the scene
            
        Returns:
            Dict containing scene analysis results
        """
        try:
            # Save the scene image temporarily
            temp_image_path = f"output/scene_{scene_number:03d}.jpg"
            with open(temp_image_path, 'wb') as img_file:
                img_file.write(scene['image_data'])
            
            # Analyze the scene
            analysis = await self.vision_analyzer.analyze_image(
                temp_image_path,
                self.scene_prompt
            )
            
            result = {
                'scene_number': scene_number,
                'timestamp': f"{scene['start_time']:.2f}s - {scene['end_time']:.2f}s",
                'analysis': analysis.get('analysis', 'Analysis failed')
            }
            
            # Log to output file - using append mode to handle concurrent writes
            with open('output/output.txt', 'a') as f:
                f.write(f"\nScene {scene_number} Analysis:\n")
                f.write(f"Timestamp: {scene['start_time']:.2f}s - {scene['end_time']:.2f}s\n")
                f.write(f"Analysis: {analysis.get('analysis', 'Analysis failed')}\n")
                f.write("-" * 80 + "\n")
                
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing scene {scene_number}: {str(e)}")
            return {
                'scene_number': scene_number,
                'timestamp': f"{scene['start_time']:.2f}s - {scene['end_time']:.2f}s",
                'analysis': f"Analysis failed: {str(e)}"
            }

    async def analyze_video(self, video_url: str) -> Dict[str, Any]:
        """
        Analyze a cooking video by extracting scenes and running vision analysis on each scene.
        
        Args:
            video_url (str): URL of the video to analyze
            
        Returns:
            Dict[str, Any]: Complete analysis including scene-by-scene and aggregate analysis
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs('output', exist_ok=True)
            
            # Step 1: Extract scenes from video
            logger.info("Extracting scenes from video...")
            scenes = self.scene_extractor.get_video_scenes(video_url)
            
            with open('output/output.txt', 'w') as f:
                f.write(f"Found {len(scenes)} scenes in the video\n\n")
            
            # Step 2: Analyze scenes concurrently
            logger.info(f"Analyzing {len(scenes)} scenes concurrently...")
            analysis_tasks = [
                self._analyze_single_scene(scene, i)
                for i, scene in enumerate(scenes)
            ]
            
            # Wait for all scene analyses to complete
            scene_analyses = await asyncio.gather(*analysis_tasks)
            
            # Sort the results by scene number to maintain order
            scene_analyses.sort(key=lambda x: x['scene_number'])
            
            # Step 3: Generate aggregate analysis
            logger.info("Generating aggregate analysis...")
            scene_analyses_text = "\n\n".join([
                f"Scene {s['scene_number']} ({s['timestamp']}):\n{s['analysis']}"
                for s in scene_analyses
            ])
            
            aggregate_message = HumanMessage(
                content=self.aggregate_prompt.format(
                    scene_count=len(scenes),
                    scene_analyses=scene_analyses_text
                )
            )
            
            aggregate_response = self.chat_model.invoke([aggregate_message])
            
            # Log final analysis to output file
            with open('output/output.txt', 'a') as f:
                f.write("\nFinal Recipe Analysis:\n")
                f.write("=" * 80 + "\n")
                f.write(aggregate_response.content)
                f.write("\n" + "=" * 80 + "\n")
            
            return {
                'success': True,
                'scene_analyses': scene_analyses,
                'final_recipe': aggregate_response.content
            }
            
        except Exception as e:
            logger.error(f"Error in video analysis: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            } 