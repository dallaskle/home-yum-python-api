from scene_extractor import VideoSceneExtractor
import os
import argparse

def test_scene_extraction(video_url: str, output_dir: str = "scene_images"):
    """
    Test the scene extractor and save images to a local directory
    
    Args:
        video_url: URL of the video to process
        output_dir: Directory to save the scene images (default: "scene_images")
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize the extractor
    extractor = VideoSceneExtractor()
    
    print(f"Extracting scenes from: {video_url}")
    scenes = extractor.get_video_scenes(video_url)
    
    if not scenes:
        print("No scenes were detected in the video.")
        return
    
    print(f"\nFound {len(scenes)} scenes:")
    
    # Save each scene image
    for scene in scenes:
        scene_number = scene['scene_number']
        duration = scene['duration']
        start_time = scene['start_time']
        
        # Save the image
        image_path = os.path.join(output_dir, f"scene_{scene_number:03d}.jpg")
        with open(image_path, 'wb') as f:
            f.write(scene['image_data'])
        
        print(f"Scene {scene_number:03d}: {start_time:.2f}s - Duration: {duration:.2f}s - Saved as: {image_path}")
    
    print(f"\nAll scene images have been saved to: {os.path.abspath(output_dir)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and save scene images from a video URL")
    parser.add_argument("video_url", help="URL of the video to process")
    parser.add_argument("--output", "-o", default="scene_images",
                      help="Directory to save scene images (default: scene_images)")
    
    args = parser.parse_args()
    test_scene_extraction(args.video_url, args.output) 