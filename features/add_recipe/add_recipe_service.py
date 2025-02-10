import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class AddRecipeService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def create_recipe_log(self, user_id: str, video_url: str, request_id: str) -> dict:
        """Create a new recipe log entry"""
        logger.info(f"[{request_id}] Creating recipe log for video URL: {video_url}")
        
        try:
            now = datetime.datetime.utcnow().isoformat()
            
            # Create recipe log document
            log_data = {
                "userId": user_id,
                "videoUrl": video_url,
                "status": "pending",
                "createdAt": now,
                "updatedAt": now
            }
            
            # Add to Firestore
            log_ref = self.db.collection('recipe_logs').document()
            log_ref.set(log_data)
            log_id = log_ref.id
            
            # Start processing in background
            # TODO: Add background task processing here using your video processing pipeline
            
            response_data = {
                "logId": log_id,
                "userId": user_id,
                "videoUrl": video_url,
                "status": "pending",
                "createdAt": now,
                "updatedAt": now
            }
            
            logger.info(f"[{request_id}] Created recipe log {log_id}")
            return response_data
            
        except Exception as e:
            logger.error(f"[{request_id}] Error creating recipe log: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create recipe log: {str(e)}"
            )

    async def get_recipe_log(self, user_id: str, log_id: str, request_id: str) -> dict:
        """Get the status of a recipe log"""
        logger.info(f"[{request_id}] Getting recipe log {log_id}")
        
        try:
            # Get recipe log document
            log_ref = self.db.collection('recipe_logs').document(log_id)
            log = log_ref.get()
            
            if not log.exists:
                logger.error(f"[{request_id}] Recipe log {log_id} not found")
                raise HTTPException(status_code=404, detail="Recipe log not found")
                
            log_data = log.to_dict()
            
            # Verify user owns this log
            if log_data['userId'] != user_id:
                logger.error(f"[{request_id}] User {user_id} not authorized to access log {log_id}")
                raise HTTPException(status_code=403, detail="Not authorized to access this recipe log")
            
            response_data = {
                "logId": log_id,
                "userId": log_data['userId'],
                "videoUrl": log_data['videoUrl'],
                "status": log_data['status'],
                "logMessage": log_data.get('logMessage'),
                "createdAt": log_data['createdAt'],
                "updatedAt": log_data['updatedAt']
            }
            
            logger.info(f"[{request_id}] Retrieved recipe log {log_id}")
            return response_data
            
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"[{request_id}] Error getting recipe log: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get recipe log: {str(e)}"
            )
