# TikTok Recipe Extractor Setup Guide

This guide explains how to set up a Python script that extracts recipe metadata and subtitles from TikTok videos.

## Prerequisites

Create a virtual environment and install the required packages:

```bash
python3 -m venv venv
source venv/bin/activate
pip install yt-dlp==2025.1.26 webvtt-py==0.4.6 requests>=2.31.0
```

## Implementation

### 1. Create the Metadata Extractor

Create a file named `tiktok_metadata_extractor.py`:

```python
import yt_dlp
from typing import Dict, Any
import requests
import webvtt
import tempfile
import os

class TikTokMetadataExtractor:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
            'force_generic_extractor': False
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
            print(f"Error downloading/parsing subtitles: {str(e)}")
            return ""

    def extract_metadata(self, video_url: str) -> Dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                
                # Extract and process subtitles if available
                subtitle_text = ""
                if 'subtitles' in info and 'eng-US' in info['subtitles']:
                    subs = info['subtitles']['eng-US']
                    if isinstance(subs, list) and len(subs) > 0 and 'url' in subs[0]:
                        subtitle_text = self.download_and_parse_subtitles(subs[0]['url'])
                
                return {
                    'title': info.get('title', ''),
                    'description': info.get('description', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'comment_count': info.get('comment_count', 0),
                    'subtitle_text': subtitle_text
                }
        except Exception as e:
            print(f"Error extracting metadata: {str(e)}")
            return {}
```

### 2. Create the Main Script

Create a file named `recipe_extractor.py`:

```python
from tiktok_metadata_extractor import TikTokMetadataExtractor
import json

def main():
    # TikTok video URL
    video_url = "YOUR_TIKTOK_VIDEO_URL"
    
    # Initialize extractor
    extractor = TikTokMetadataExtractor()
    
    # Extract recipe information
    print("Extracting metadata and subtitles...")
    recipe_info = {
        "metadata": extractor.extract_metadata(video_url),
        "source_url": video_url
    }
    
    # Save to JSON file
    output_file = "recipe_info.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(recipe_info, f, indent=2, ensure_ascii=False)
    print(f"Recipe information saved to {output_file}")

if __name__ == "__main__":
    main()
```

## Usage

1. Replace `YOUR_TIKTOK_VIDEO_URL` in `recipe_extractor.py` with your TikTok video URL
2. Run the script:
```bash
python recipe_extractor.py
```

The script will create a `recipe_info.json` file containing:
- Video metadata (title, description, duration, uploader, view count, like count, comment count)
- Subtitle text (contains the recipe instructions if available)

## How It Works

1. The script uses `yt-dlp` to extract metadata and subtitle information from TikTok videos without downloading the actual video
2. If subtitles are available, it downloads them in WebVTT format
3. The WebVTT subtitles are parsed and combined into a single text string
4. All information is saved to a JSON file for easy processing

## Troubleshooting

- If you get errors about "Unable to extract sigi state", try updating yt-dlp:
```bash
pip install --upgrade yt-dlp
```
- TikTok frequently updates their platform, so make sure to keep yt-dlp updated to the latest version
