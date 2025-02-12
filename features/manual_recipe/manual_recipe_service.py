import logging
import datetime
import asyncio
from typing import Dict, Any, Optional
from firebase_admin import firestore
from fastapi import HTTPException
from langsmith import traceable

from .recipe_generator import RecipeGenerator
from .image_generator import ImageGenerator
from .nutrition_analyzer import ManualNutritionAnalyzer
from .video_creator import VideoCreator

logger = logging.getLogger(__name__)

class ManualRecipeService:
    def __init__(self, db: firestore.Client):
        """Initialize the ManualRecipeService with required components."""
        self.db = db
        self.recipe_generator = RecipeGenerator()
        self.image_generator = ImageGenerator()
        self.nutrition_analyzer = ManualNutritionAnalyzer()
        self.video_creator = VideoCreator()

    async def create_recipe_log(self, user_id: str, prompt: str, request_id: str) -> Dict[str, Any]:
        """Create a new manual recipe log entry."""
        now = datetime.datetime.utcnow().isoformat()
        
        try:
            # Create initial log document
            log_data = {
                "userId": user_id,
                "prompt": prompt,
                "status": "processing",
                "createdAt": now,
                "updatedAt": now,
                "processingSteps": [{
                    "step": "initialization",
                    "status": "completed",
                    "timestamp": now,
                    "success": True
                }]
            }
            
            # Add to Firestore
            log_ref = self.db.collection('manual_recipe_logs').document()
            log_ref.set(log_data)
            log_id = log_ref.id
            
            return {
                "logId": log_id,
                "userId": user_id,
                "prompt": prompt,
                "status": "initialized",
                "createdAt": now,
                "updatedAt": now
            }
            
        except Exception as e:
            logger.error(f"[{request_id}] Error creating manual recipe log: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create recipe log: {str(e)}"
            )

    @traceable(name="generate_initial_recipe")
    async def generate_initial_recipe(self, log_id: str, request_id: str) -> Dict[str, Any]:
        """Generate initial recipe and meal image from prompt in parallel."""
        try:
            # Get log document
            log_ref = self.db.collection('manual_recipe_logs').document(log_id)
            log = log_ref.get()
            
            if not log.exists:
                raise HTTPException(status_code=404, detail="Recipe log not found")
                
            log_data = log.to_dict()
            prompt = log_data['prompt']
            now = datetime.datetime.utcnow().isoformat()
            
            # Run recipe and image generation in parallel
            recipe_task = self.recipe_generator.generate_recipe(prompt)
            image_task = self.image_generator.generate_meal_image(prompt)
            
            # Wait for both tasks to complete
            recipe_result, image_result = await asyncio.gather(recipe_task, image_task)
            
            # Update log with results
            update_data = {
                "recipe": recipe_result,
                "mealImage": image_result,
                "status": "initial_generated",
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "initial_generation",
                    "status": "completed",
                    "timestamp": now,
                    "success": True
                }])
            }
            
            log_ref.update(update_data)
            
            return {
                "logId": log_id,
                "recipe": recipe_result,
                "mealImage": image_result,
                "status": "initial_generated"
            }
            
        except Exception as e:
            logger.error(f"[{request_id}] Error generating initial recipe: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate initial recipe: {str(e)}"
            )

    async def update_recipe(self, log_id: str, updates: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Update recipe or image based on user feedback."""
        try:
            # Get log document
            log_ref = self.db.collection('manual_recipe_logs').document(log_id)
            log = log_ref.get()
            
            if not log.exists:
                raise HTTPException(status_code=404, detail="Recipe log not found")
                
            log_data = log.to_dict()
            now = datetime.datetime.utcnow().isoformat()
            
            # Process recipe updates if provided
            recipe_result = None
            if 'recipe_updates' in updates:
                recipe_result = await self.recipe_generator.update_recipe(
                    log_data['recipe'],
                    updates['recipe_updates']
                )
            
            # Process image updates if provided
            image_result = None
            if 'image_updates' in updates:
                image_result = await self.image_generator.update_meal_image(
                    log_data['mealImage'],
                    updates['image_updates']
                )
            
            # Update log with results
            update_data = {
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "update_generation",
                    "status": "completed",
                    "timestamp": now,
                    "success": True
                }])
            }
            
            if recipe_result:
                update_data["recipe"] = recipe_result
            if image_result:
                update_data["mealImage"] = image_result
                
            log_ref.update(update_data)
            
            return {
                "logId": log_id,
                "recipe": recipe_result or log_data['recipe'],
                "mealImage": image_result or log_data['mealImage'],
                "status": "updated"
            }
            
        except Exception as e:
            logger.error(f"[{request_id}] Error updating recipe: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update recipe: {str(e)}"
            )

    async def confirm_recipe(self, log_id: str, request_id: str) -> Dict[str, Any]:
        """Process final recipe confirmation and generate additional assets."""
        try:
            # Get log document
            log_ref = self.db.collection('manual_recipe_logs').document(log_id)
            log = log_ref.get()
            
            if not log.exists:
                raise HTTPException(status_code=404, detail="Recipe log not found")
                
            log_data = log.to_dict()
            now = datetime.datetime.utcnow().isoformat()
            
            # Generate nutrition information
            nutrition_result = await self.nutrition_analyzer.analyze_recipe(log_data['recipe'])
            
            # Generate ingredient images
            ingredient_images = await self.image_generator.generate_ingredient_images(
                log_data['recipe']['ingredients']
            )
            
            # Create video from images
            video_result = await self.video_creator.create_slideshow(
                ingredient_images,
                log_data['mealImage'],
                log_data['userId'],
                {
                    'title': log_data['recipe']['title'],
                    'description': log_data['recipe']['description'],
                    'mealImage': log_data['mealImage'],
                    'ingredients': log_data['recipe']['ingredients']
                }
            )
            
            if not video_result['success']:
                raise ValueError(video_result.get('error', 'Failed to create video'))
            
            # Update log with final data
            final_update = {
                "videoId": video_result['video_id'],
                "nutrition": nutrition_result,
                "ingredientImages": ingredient_images,
                "video": {
                    "videoId": video_result['video_id'],
                    "videoTitle": f"Recipe: {log_data['recipe']['title']}",
                    "videoDescription": log_data['recipe']['description'],
                    "mealName": log_data['recipe']['title'],
                    "mealDescription": log_data['recipe']['description'],
                    "videoUrl": video_result['video_url'],
                    "thumbnailUrl": log_data['mealImage']['url'],
                    "duration": video_result['duration'],
                    "uploadedAt": now,
                    "source": "manual_recipe"
                },
                "status": "completed",
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "final_generation",
                    "status": "completed",
                    "timestamp": now,
                    "success": True
                }])
            }
            
            # Update Firestore
            log_ref.update(final_update)
            
            # Return response matching ManualRecipeResponse interface
            return {
                "logId": log_id,
                "recipe": log_data['recipe'],
                "mealImage": log_data['mealImage'],
                "status": "completed",
                "video": final_update["video"]
            }
            
        except Exception as e:
            logger.error(f"[{request_id}] Error confirming recipe: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to confirm recipe: {str(e)}"
            )

    async def get_recipe_log(self, log_id: str, request_id: str) -> Dict[str, Any]:
        """Get the current status and data of a manual recipe log."""
        try:
            log_ref = self.db.collection('manual_recipe_logs').document(log_id)
            log = log_ref.get()
            
            if not log.exists:
                raise HTTPException(status_code=404, detail="Recipe log not found")
                
            return log.to_dict()
            
        except Exception as e:
            logger.error(f"[{request_id}] Error getting recipe log: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get recipe log: {str(e)}"
            ) 