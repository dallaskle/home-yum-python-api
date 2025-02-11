import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class VideoService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def get_recipe_data(self, video_id: str) -> dict:
        """Get recipe data for a video including ingredients, instructions, and nutrition info"""
        try:
            # Get recipe data
            recipe_ref = self.db.collection('recipes').where('videoId', '==', video_id).limit(1).get()
            recipe = recipe_ref[0].to_dict() if recipe_ref else None
            
            if recipe:
                recipe['recipeId'] = recipe_ref[0].id
                
                # Get recipe items (instructions)
                recipe_items_ref = self.db.collection('recipe_items').where('recipeId', '==', recipe['recipeId']).get()
                recipe_items = []
                for item in recipe_items_ref:
                    item_data = item.to_dict()
                    item_data['recipeItemId'] = item.id
                    recipe_items.append(item_data)
            
            # Get nutrition info (which now includes ingredients)
            nutrition_ref = self.db.collection('nutrition').where('videoId', '==', video_id).limit(1).get()
            nutrition = nutrition_ref[0].to_dict() if nutrition_ref else None
            ingredients = []
            
            if nutrition:
                nutrition['nutritionId'] = nutrition_ref[0].id
                # Extract ingredients from nutrition data
                ingredients = nutrition.get('ingredients', [])
                # Add ingredient IDs using index as we don't store them separately anymore
                for idx, ingredient in enumerate(ingredients):
                    ingredient['ingredientId'] = f"{nutrition['nutritionId']}_ingredient_{idx}"
            
            return {
                "recipe": recipe,
                "recipeItems": recipe_items if recipe else [],
                "ingredients": ingredients,
                "nutrition": nutrition
            }
        except Exception as e:
            logger.error(f"Error getting recipe data: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_video(self, video_id: str) -> dict:
        """Get single video details"""
        try:
            doc_ref = self.db.collection('videos').document(video_id)
            doc = doc_ref.get()
            if doc.exists:
                video_data = doc.to_dict()
                video_data['videoId'] = doc.id
                return video_data
            raise HTTPException(status_code=404, detail="Video not found")
        except Exception as e:
            logger.error(f"Error getting video: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def generate_recipe_data(self, video_id: str) -> dict:
        """Generate random recipe data for a video"""
        try:
            # Get video to ensure it exists
            video_ref = self.db.collection('videos').document(video_id)
            video = video_ref.get()
            if not video.exists:
                raise HTTPException(status_code=404, detail="Video not found")

            video_data = video.to_dict()
            
            # Generate random recipe
            recipe_data = {
                "videoId": video_id,
                "title": video_data.get('mealName', 'Delicious Recipe'),
                "summary": "A wonderful homemade recipe",
                "additionalNotes": "Best served fresh",
                "createdAt": datetime.datetime.utcnow().isoformat(),
                "updatedAt": datetime.datetime.utcnow().isoformat()
            }
            
            # Create recipe
            recipe_ref = self.db.collection('recipes').document()
            recipe_ref.set(recipe_data)
            recipe_id = recipe_ref.id

            # Generate random recipe items (instructions)
            instructions = [
                {"stepOrder": 1, "instruction": "Prepare all ingredients", "additionalDetails": "Ensure everything is at room temperature"},
                {"stepOrder": 2, "instruction": "Mix dry ingredients", "additionalDetails": "Sift for best results"},
                {"stepOrder": 3, "instruction": "Combine wet ingredients", "additionalDetails": "Mix until smooth"},
                {"stepOrder": 4, "instruction": "Combine all ingredients", "additionalDetails": "Don't overmix"},
                {"stepOrder": 5, "instruction": "Cook according to video instructions", "additionalDetails": "Follow temperature guidelines"}
            ]
            
            recipe_items = []
            for instruction in instructions:
                item_ref = self.db.collection('recipe_items').document()
                item_data = {
                    "recipeId": recipe_id,
                    **instruction
                }
                item_ref.set(item_data)
                recipe_items.append({**item_data, "recipeItemId": item_ref.id})

            # Generate random ingredients
            ingredients = [
                {"name": "All-purpose flour", "quantity": 2, "unit": "cups"},
                {"name": "Sugar", "quantity": 1, "unit": "cup"},
                {"name": "Eggs", "quantity": 2, "unit": "pieces"},
                {"name": "Milk", "quantity": 1, "unit": "cup"},
                {"name": "Butter", "quantity": 0.5, "unit": "cup"}
            ]
            
            ingredient_list = []
            for ingredient in ingredients:
                ing_ref = self.db.collection('ingredients').document()
                ing_data = {
                    "videoId": video_id,
                    **ingredient
                }
                ing_ref.set(ing_data)
                ingredient_list.append({**ing_data, "ingredientId": ing_ref.id})

            # Generate random nutrition data
            nutrition_data = {
                "videoId": video_id,
                "calories": 350,
                "fat": 12,
                "protein": 8,
                "carbohydrates": 48,
                "fiber": 2,
                "sugar": 24,
                "sodium": 400
            }
            
            nutrition_ref = self.db.collection('nutrition').document()
            nutrition_ref.set(nutrition_data)
            nutrition_data["nutritionId"] = nutrition_ref.id

            return {
                "recipe": {**recipe_data, "recipeId": recipe_id},
                "recipeItems": recipe_items,
                "ingredients": ingredient_list,
                "nutrition": nutrition_data
            }
        except Exception as e:
            logger.error(f"Error generating recipe data: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
