import logging
import os
import replicate
import tempfile
import uuid
import aiofiles
from typing import Dict, Any, List
from dotenv import load_dotenv
from langsmith import traceable
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class ImageGenerator:
    def __init__(self):
        """Initialize the ImageGenerator with Replicate and Supabase configuration."""
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        if not self.replicate_api_token:
            raise ValueError("REPLICATE_API_TOKEN environment variable is required")
            
        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        self.supabase: Client = create_client(supabase_url, supabase_key)

    def _sanitize_filename(self, prefix: str) -> str:
        """Generate a sanitized filename with a UUID."""
        unique_id = str(uuid.uuid4())[:8]
        return f"{prefix}_{unique_id}.webp"

    async def _upload_to_supabase(self, file_content: bytes, storage_path: str) -> str:
        """Upload file to Supabase storage and return the public URL."""
        try:
            self.supabase.storage.from_('home-yum').upload(
                path=storage_path,
                file=file_content,
                file_options={"content-type": "image/webp"}
            )
            
            # Get public URL
            public_url = self.supabase.storage.from_('home-yum').get_public_url(storage_path)
            return public_url.split('?')[0] if '?' in public_url else public_url
            
        except Exception as e:
            logger.error(f"Supabase upload error - Path: {storage_path}, Error: {str(e)}")
            raise

    @traceable(name="generate_meal_image")
    async def generate_meal_image(self, prompt: str) -> Dict[str, Any]:
        """Generate a single image of the complete meal."""
        temp_file = None
        try:
            logger.info(f"Generating meal image for prompt: {prompt}")
            
            # Enhance the prompt for better meal visualization
            enhanced_prompt = f"Create a professional food photography style image of {prompt}. The image should be well-lit, appetizing, and showcase the complete dish."
            
            # Run image generation
            output = replicate.run(
                "black-forest-labs/flux-schnell",
                input={"prompt": enhanced_prompt}
            )
            
            # Process the first generated image
            for index, item in enumerate(output):
                if index == 0:  # We only need the first image
                    # Create a temporary file
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    temp_file.write(item.read())
                    temp_file.close()
                    
                    # Read the file content
                    async with aiofiles.open(temp_file.name, 'rb') as f:
                        file_content = await f.read()
                    
                    # Generate storage path and upload
                    storage_path = f"recipe_images/{self._sanitize_filename('meal')}"
                    image_url = await self._upload_to_supabase(file_content, storage_path)
                    
                    return {
                        "success": True,
                        "url": image_url,
                        "prompt": enhanced_prompt
                    }
            
            raise Exception("No image was generated")
            
        except Exception as e:
            logger.error(f"Error generating meal image: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    async def update_meal_image(self, current_image: Dict[str, Any], updates: str) -> Dict[str, Any]:
        """Update the meal image based on user feedback."""
        temp_file = None
        try:
            logger.info(f"Updating meal image with feedback: {updates}")
            
            # Combine the original prompt with the updates
            enhanced_prompt = f"{current_image['prompt']} {updates}"
            
            # Generate new image
            output = replicate.run(
                "black-forest-labs/flux-schnell",
                input={"prompt": enhanced_prompt}
            )
            
            # Process the first generated image
            for index, item in enumerate(output):
                if index == 0:
                    # Create a temporary file
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    temp_file.write(item.read())
                    temp_file.close()
                    
                    # Read the file content
                    async with aiofiles.open(temp_file.name, 'rb') as f:
                        file_content = await f.read()
                    
                    # Generate storage path and upload
                    storage_path = f"recipe_images/{self._sanitize_filename('meal_updated')}"
                    image_url = await self._upload_to_supabase(file_content, storage_path)
                    
                    return {
                        "success": True,
                        "url": image_url,
                        "prompt": enhanced_prompt
                    }
            
            raise Exception("No image was generated")
            
        except Exception as e:
            logger.error(f"Error updating meal image: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    async def generate_ingredient_images(self, ingredients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate individual images for each ingredient."""
        try:
            logger.info(f"Generating images for {len(ingredients)} ingredients")
            
            ingredient_images = []
            
            for index, ingredient in enumerate(ingredients):
                temp_file = None
                try:
                    # Create a prompt for the ingredient
                    prompt = f"Create a clear, well-lit image of {ingredient['amount']} {ingredient['amountDescription']} of {ingredient['name']} on a white background, food photography style"
                    
                    # Generate image
                    output = replicate.run(
                        "black-forest-labs/flux-schnell",
                        input={"prompt": prompt}
                    )
                    
                    # Process the first generated image
                    for img_index, item in enumerate(output):
                        if img_index == 0:
                            # Create a temporary file
                            temp_file = tempfile.NamedTemporaryFile(delete=False)
                            temp_file.write(item.read())
                            temp_file.close()
                            
                            # Read the file content
                            async with aiofiles.open(temp_file.name, 'rb') as f:
                                file_content = await f.read()
                            
                            # Generate storage path and upload
                            storage_path = f"recipe_images/ingredients/{self._sanitize_filename(f'ingredient_{index}')}"
                            image_url = await self._upload_to_supabase(file_content, storage_path)
                            
                            ingredient_images.append({
                                "ingredientName": ingredient['name'],
                                "url": image_url,
                                "prompt": prompt,
                                "order": index
                            })
                            break
                            
                finally:
                    # Clean up temporary file
                    if temp_file and os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
            
            return ingredient_images
            
        except Exception as e:
            logger.error(f"Error generating ingredient images: {str(e)}")
            return [] 