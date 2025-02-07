import asyncio
import logging
from video_recipe_analyzer import VideoRecipeAnalyzer
from nutrition import NutritionAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Initialize the analyzers
    analyzer = VideoRecipeAnalyzer()
    nutrition_analyzer = NutritionAnalyzer()
    
    # Example cooking video URL - replace with an actual cooking video URL
    #video_url = "https://vm.tiktok.com/ZNeoxXwWy/"
    video_url = "https://www.instagram.com/chefshaan19/reel/C6rEZMiplWn/"
    
    try:
        # Analyze the video
        logger.info(f"Starting analysis of video: {video_url}")
        result = await analyzer.analyze_video(video_url)
        
        if result['success']:
            logger.info("Analysis completed successfully!")
            logger.info(f"Number of scenes analyzed: {len(result['scene_analyses'])}")
            logger.info("\nFinal Recipe:")
            print(result['final_recipe'])
            
            # Add nutrition analysis
            logger.info("\nAnalyzing nutrition information...")
            nutrition_result = await nutrition_analyzer.analyze_recipe_nutrition(result['final_recipe'])
            
            if nutrition_result['success']:
                logger.info("\nServing Sizes (for 4 people):")
                print(nutrition_result['serving_sizes'])
                logger.info("\nNutritional Information:")
                print(nutrition_result['nutrition_info'])
            else:
                logger.error(f"Nutrition analysis failed: {nutrition_result.get('error', 'Unknown error')}")
        else:
            logger.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error running test: {str(e)}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main()) 