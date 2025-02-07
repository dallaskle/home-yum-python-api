import asyncio
import logging
from video_recipe_analyzer import VideoRecipeAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Initialize the analyzer
    analyzer = VideoRecipeAnalyzer()
    
    # Example cooking video URL - replace with an actual cooking video URL
    video_url = "https://vm.tiktok.com/ZNeoxXwWy/"
    
    try:
        # Analyze the video
        logger.info(f"Starting analysis of video: {video_url}")
        result = await analyzer.analyze_video(video_url)
        
        if result['success']:
            logger.info("Analysis completed successfully!")
            logger.info(f"Number of scenes analyzed: {len(result['scene_analyses'])}")
            logger.info("\nFinal Recipe:")
            print(result['final_recipe'])
        else:
            logger.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error running test: {str(e)}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main()) 