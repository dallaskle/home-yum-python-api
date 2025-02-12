import logging
import os
import replicate
from typing import Dict, Any, List
from dotenv import load_dotenv
from langsmith import traceable
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class ImageGenerator:
    def __init__(self):
        """Initialize the ImageGenerator with Replicate configuration."""
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        if not self.replicate_api_token:
            raise ValueError("REPLICATE_API_TOKEN environment variable is required")

    @traceable(name="generate_meal_image")
    async def generate_meal_image(self, prompt: str) -> Dict[str, Any]:
        """Generate a single image of the complete meal."""
        try:
            logger.info(f"Generating meal image for prompt: {prompt}")
            
            # Enhance the prompt for better meal visualization
            enhanced_prompt = f"Create a professional food photography style image of {prompt}. The image should be well-lit, appetizing, and showcase the complete dish."
            
            # Run image generation
            output = replicate.run(
                "black-forest-labs/flux-schnell",
                input={"prompt": enhanced_prompt}
            )
            
            # Process and save the first generated image
            image_url = None
            for index, item in enumerate(output):
                if index == 0:  # We only need the first image
                    # Save the image and get its URL
                    # Note: In production, you'd want to save this to proper storage
                    with open(f"output_{index}.webp", "wb") as file:
                        file.write(item.read())
                    image_url = f"output_{index}.webp"
                    break
            
            if not image_url:
                raise Exception("No image was generated")
            
            return {
                "success": True,
                "url": image_url,
                "prompt": enhanced_prompt
            }
            
        except Exception as e:
            logger.error(f"Error generating meal image: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def update_meal_image(self, current_image: Dict[str, Any], updates: str) -> Dict[str, Any]:
        """Update the meal image based on user feedback."""
        try:
            logger.info(f"Updating meal image with feedback: {updates}")
            
            # Combine the original prompt with the updates
            enhanced_prompt = f"{current_image['prompt']} {updates}"
            
            # Generate new image
            output = replicate.run(
                "black-forest-labs/flux-schnell",
                input={"prompt": enhanced_prompt}
            )
            
            # Process and save the first generated image
            image_url = None
            for index, item in enumerate(output):
                if index == 0:
                    with open(f"output_updated_{index}.webp", "wb") as file:
                        file.write(item.read())
                    image_url = f"output_updated_{index}.webp"
                    break
            
            if not image_url:
                raise Exception("No image was generated")
            
            return {
                "success": True,
                "url": image_url,
                "prompt": enhanced_prompt
            }
            
        except Exception as e:
            logger.error(f"Error updating meal image: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def generate_ingredient_images(self, ingredients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate individual images for each ingredient."""
        try:
            logger.info(f"Generating images for {len(ingredients)} ingredients")
            
            ingredient_images = []
            
            for index, ingredient in enumerate(ingredients):
                # Create a prompt for the ingredient
                prompt = f"Create a clear, well-lit image of {ingredient['amount']} {ingredient['amountDescription']} of {ingredient['name']} on a white background, food photography style"
                
                # Generate image
                output = replicate.run(
                    "black-forest-labs/flux-schnell",
                    input={"prompt": prompt}
                )
                
                # Save the first generated image
                image_url = None
                for img_index, item in enumerate(output):
                    if img_index == 0:
                        filename = f"ingredient_{index}.webp"
                        with open(filename, "wb") as file:
                            file.write(item.read())
                        image_url = filename
                        break
                
                if image_url:
                    ingredient_images.append({
                        "ingredientName": ingredient['name'],
                        "url": image_url,
                        "prompt": prompt,
                        "order": index
                    })
            
            return ingredient_images
            
        except Exception as e:
            logger.error(f"Error generating ingredient images: {str(e)}")
            return [] 