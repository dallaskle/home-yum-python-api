import logging
import json
import os
from extractor import TikTokMetadataExtractor
import re

# Set up logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test video URLs - uncomment the one you want to test
TEST_VIDEO_URL = "https://vm.tiktok.com/ZNeoxtLpP/"  # Current format
# TEST_VIDEO_URL = "https://www.tiktok.com/@username/video/1234567890123456789"  # Standard format
# TEST_VIDEO_URL = "https://vm.tiktok.com/ZNeoxtLpP/"  # Short format

def validate_tiktok_url(url):
    """Validate and potentially fix TikTok URL format."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    if 'vm.tiktok.com' in url:
        return url  # Short URL format is fine as is
    
    if 'tiktok.com' in url and not url.startswith('https://www.tiktok.com'):
        url = url.replace('https://', 'https://www.')
        url = url.replace('http://', 'https://www.')
    
    logger.info(f"Using URL: {url}")
    return url

def main():
    # Initialize the TikTok metadata extractor
    extractor = TikTokMetadataExtractor()
    
    try:
        logger.info("Starting metadata extraction...")
        
        # Validate and fix URL format
        validated_url = validate_tiktok_url(TEST_VIDEO_URL)
        
        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)
        
        # Extract metadata from the video
        logger.info("Calling extract_metadata...")
        metadata_result = extractor.extract_metadata(validated_url)
        
        if metadata_result:
            logger.info("\nExtracted Metadata:")
            print(json.dumps(metadata_result, indent=2))
            
            # Write results to a file
            logger.info("Writing results to file...")
            with open('output/tiktok_metadata.txt', 'w') as f:
                f.write("TikTok Video Metadata\n")
                f.write("=" * 50 + "\n\n")
                f.write(json.dumps(metadata_result, indent=2))
            logger.info("Results written to output/tiktok_metadata.txt")
            
            # Log specific important fields
            logger.info(f"\nTitle: {metadata_result.get('title', 'N/A')}")
            logger.info(f"Description: {metadata_result.get('description', 'N/A')}")
            logger.info(f"Duration: {metadata_result.get('duration', 'N/A')} seconds")
            logger.info(f"View Count: {metadata_result.get('view_count', 'N/A')}")
            logger.info(f"Like Count: {metadata_result.get('like_count', 'N/A')}")
            
            # Log subtitle availability
            if metadata_result.get('subtitle_text'):
                logger.info("\nSubtitles were successfully extracted")
                logger.info(f"Subtitle length: {len(metadata_result['subtitle_text'])} characters")
            else:
                logger.info("\nNo subtitles were available or could be extracted")
                
        else:
            logger.error("Metadata extraction failed: Empty result returned")
            
    except Exception as e:
        logger.error(f"Error running extractor test: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 