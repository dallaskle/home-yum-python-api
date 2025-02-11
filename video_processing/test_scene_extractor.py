from video_processing.scene_extractor import VideoSceneExtractor
import os
import argparse

def test_scene_extraction(video_url: str):
    """
    Test the scene extractor
    
    Args:
        video_url: URL of the video to process
    """
    # Initialize the extractor
    extractor = VideoSceneExtractor()
    
    print(f"Extracting scenes from: {video_url}")
    scenes = extractor.get_video_scenes(video_url)
    
    if not scenes:
        print("No scenes were detected in the video.")
        return
    
    print(f"\nFound {len(scenes)} scenes:")
    
    # Print scene information
    for scene in scenes:
        scene_number = scene['scene_number']
        duration = scene['duration']
        start_time = scene['start_time']
        
        print(f"Scene {scene_number:03d}: {start_time:.2f}s - Duration: {duration:.2f}s")
    
    print(f"\nAll scenes extracted successfully")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract scenes from a video URL")
    parser.add_argument("video_url", help="URL of the video to process")
    
    args = parser.parse_args()
    test_scene_extraction(args.video_url) 