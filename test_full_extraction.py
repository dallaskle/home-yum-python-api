import asyncio
import logging
from full_extraction_flow import FullExtractionFlow
import argparse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract recipe from a cooking video')
    parser.add_argument('video_url', help='URL of the cooking video to analyze')
    args = parser.parse_args()
    
    # Initialize the extractor
    extractor = FullExtractionFlow()
    
    try:
        # Run the full extraction
        logger.info(f"Starting full extraction for video: {args.video_url}")
        result = await extractor.extract_all(args.video_url)
        
        if result['success']:
            logger.info("Extraction completed successfully!")
            logger.info("\nFinal Recipe:")
            print(result['final_recipe'])
            logger.info("\nFull results have been saved to output/full_output.txt")
        else:
            logger.error(f"Extraction failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error running extraction: {str(e)}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main()) 