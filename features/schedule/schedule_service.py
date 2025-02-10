import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class ScheduleService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def schedule_meal(self, user_id: str, meal_data: dict) -> dict:
        """Schedule a meal for a specific date and time"""
        try:
            now = datetime.datetime.utcnow().isoformat()
            
            # Create meal document
            meal_doc = {
                "userId": user_id,
                "videoId": meal_data['videoId'],
                "mealDate": meal_data['mealDate'],
                "mealTime": meal_data['mealTime'],
                "completed": False,
                "createdAt": now,
                "updatedAt": now
            }
            
            doc_ref = self.db.collection('meals').document()
            doc_ref.set(meal_doc)
            
            meal_doc['mealId'] = doc_ref.id
            return meal_doc
        except Exception as e:
            logger.error(f"Error scheduling meal: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_scheduled_meals(self, user_id: str) -> list:
        """Get user's scheduled meals"""
        try:
            meals = self.db.collection('meals').where('userId', '==', user_id).get()
            
            # Get all meal ratings for this user
            ratings = {
                rating.to_dict()['mealId']: rating.to_dict()  # Changed from videoId to mealId
                for rating in self.db.collection('meal_ratings')
                    .where('userId', '==', user_id)
                    .get()
            }
            
            # Fetch videos for all meals
            video_ids = [meal.to_dict()['videoId'] for meal in meals]
            
            # Get videos by their document IDs directly
            videos = {}
            if video_ids:
                for video_id in video_ids:
                    video_doc = self.db.collection('videos').document(video_id).get()
                    if video_doc.exists:
                        videos[video_id] = video_doc.to_dict()

            logger.info(f"Found {len(videos)} videos for {len(video_ids)} meal(s)")
            
            result = []
            for meal in meals:
                meal_data = meal.to_dict()
                meal_data['mealId'] = meal.id
                
                # Add video data if available
                if meal_data['videoId'] in videos:
                    video_data = videos[meal_data['videoId']]
                    meal_data['video'] = {
                        'videoId': meal_data['videoId'],
                        'mealName': video_data.get('mealName', ''),
                        'mealDescription': video_data.get('mealDescription', ''),
                        'thumbnailUrl': video_data.get('thumbnailUrl', '')
                    }
                else:
                    logger.warning(f"No video found for meal {meal_data['mealId']} with videoId {meal_data['videoId']}")
                
                # Add rating if available for this specific meal
                if meal_data['mealId'] in ratings:  # Changed from videoId to mealId
                    meal_data['rating'] = ratings[meal_data['mealId']]
                
                result.append(meal_data)
                
            return result
        except Exception as e:
            logger.error(f"Error getting scheduled meals: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_meal_schedule(self, user_id: str, meal_id: str, update_data: dict) -> dict:
        """Update a scheduled meal's date and time"""
        try:
            meal_ref = self.db.collection('meals').document(meal_id)
            meal_doc = meal_ref.get()
            
            if not meal_doc.exists:
                raise HTTPException(status_code=404, detail="Meal schedule not found")
                
            meal_data = meal_doc.to_dict()
            if meal_data['userId'] != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to update this meal schedule")
            
            update_data = {
                "mealDate": update_data['mealDate'],
                "mealTime": update_data['mealTime'],
                "updatedAt": datetime.datetime.utcnow().isoformat()
            }
            
            meal_ref.update(update_data)
            
            return {
                "mealId": meal_id,
                **meal_data,
                **update_data
            }
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"Error updating meal schedule: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_meal_schedule(self, user_id: str, meal_id: str) -> dict:
        """Delete a scheduled meal"""
        try:
            meal_ref = self.db.collection('meals').document(meal_id)
            meal_doc = meal_ref.get()
            
            if not meal_doc.exists:
                raise HTTPException(status_code=404, detail="Meal schedule not found")
                
            meal_data = meal_doc.to_dict()
            if meal_data['userId'] != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to delete this meal schedule")
            
            meal_ref.delete()
            return {"message": "Meal schedule deleted successfully"}
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"Error deleting meal schedule: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
