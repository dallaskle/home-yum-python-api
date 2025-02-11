import datetime
import logging
import json
from firebase_admin import firestore
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class VideoNotFoundException(HTTPException):
    def __init__(self, video_id: str):
        super().__init__(
            status_code=404,
            detail=f"Video with ID {video_id} not found"
        )

class DuplicateEntryException(HTTPException):
    def __init__(self, message: str):
        super().__init__(
            status_code=409,
            detail=message
        )

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime,)):
            return obj.isoformat()
        return super().default(obj)

class TryListService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def get_video_or_none(self, video_id: str, request_id: str = None) -> dict:
        """Get video document or return None if not found"""
        try:
            video_ref = self.db.collection('videos').document(video_id)
            video = video_ref.get()
            if not video.exists:
                return None
            return video.to_dict()
        except Exception as e:
            logger.error(f"Error getting video {video_id}: {str(e)}")
            return None

    async def cleanup_orphaned_references(self, user_id: str, request_id: str):
        """Clean up try-list items that reference non-existent videos"""
        try:
            try_list_ref = self.db.collection('user_try_list').where('userId', '==', user_id)
            
            # Check and clean try-list
            for item in try_list_ref.stream():
                video_id = item.get('videoId')
                if video_id:
                    video = await self.get_video_or_none(video_id, request_id)
                    if not video:
                        item.reference.delete()
                        logger.info(f"[{request_id}] Cleaned up orphaned try-list item for video {video_id}")
                    
        except Exception as e:
            logger.error(f"[{request_id}] Error during cleanup: {str(e)}")

    async def add_to_try_list(self, user_id: str, try_item: dict) -> dict:
        """Add a video to user's try list"""
        try:
            # Validate video exists first
            video = await self.get_video_or_none(try_item['videoId'])
            if not video:
                raise VideoNotFoundException(try_item['videoId'])
            
            now = datetime.datetime.utcnow().isoformat()
            try_list_ref = self.db.collection('user_try_list')
            
            # Check for duplicate
            existing_item = try_list_ref.where('userId', '==', user_id).where('videoId', '==', try_item['videoId']).get()
            if existing_item:
                raise DuplicateEntryException("Video already in try list")
            
            try_list_data = {
                "userId": user_id,
                "videoId": try_item['videoId'],
                "notes": try_item.get('notes'),
                "addedDate": now
            }
            
            doc_ref = try_list_ref.document()
            doc_ref.set(try_list_data)
            try_list_data['tryListId'] = doc_ref.id
            logger.info(f"Added video {try_item['videoId']} to try list for user {user_id}")
            
            return try_list_data
        except (VideoNotFoundException, DuplicateEntryException) as e:
            raise e
        except Exception as e:
            logger.error(f"Error adding to try list: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to add to try list: {str(e)}")

    async def get_try_list(self, user_id: str, request_id: str) -> list:
        """Get user's try list with video data"""
        logger.info(f"[{request_id}] Getting try list for user {user_id}")
        
        try:
            try_list_ref = self.db.collection('user_try_list')
            items = try_list_ref.where('userId', '==', user_id).get()
            
            logger.info(f"[{request_id}] Found {len(list(items))} try list items")
            
            try_list = []
            missing_videos = []
            for item in items:
                try_list_data = item.to_dict()
                try_list_data['tryListId'] = item.id
                logger.debug(f"[{request_id}] Processing try list item {item.id}")
                
                # Get video data
                video_data = await self.get_video_or_none(try_list_data['videoId'], request_id)
                if video_data:
                    try_list_data['video'] = video_data
                    try_list.append(try_list_data)
                    # Use custom encoder for logging
                    logger.debug(f"[{request_id}] Added try list item with video data: {json.dumps(try_list_data, indent=2, cls=CustomJSONEncoder)}")
                else:
                    missing_videos.append(try_list_data['videoId'])
                    logger.warning(f"[{request_id}] Missing video {try_list_data['videoId']} for try list item {item.id}")
            
            if missing_videos:
                logger.warning(f"[{request_id}] Found {len(missing_videos)} missing videos: {missing_videos}")
                # Trigger cleanup in background
                await self.cleanup_orphaned_references(user_id, request_id)
            
            logger.info(f"[{request_id}] Returning {len(try_list)} valid try list items")
            return try_list
        except Exception as e:
            logger.error(f"[{request_id}] Error getting try list: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get try list: {str(e)}")

    async def remove_from_try_list(self, user_id: str, video_id: str) -> dict:
        """Remove a video from user's try list"""
        try:
            try_list_ref = self.db.collection('user_try_list')
            items = try_list_ref.where('userId', '==', user_id).where('videoId', '==', video_id).get()
            
            if not items:
                raise HTTPException(status_code=404, detail="Video not found in try list")
            
            for item in items:
                item.reference.delete()
                logger.info(f"Removed video {video_id} from try list for user {user_id}")
                
            return {"message": "Removed from try list successfully"}
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"Error removing from try list: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to remove from try list: {str(e)}")
