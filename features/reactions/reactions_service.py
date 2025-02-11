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

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime,)):
            return obj.isoformat()
        return super().default(obj)

class ReactionsService:
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
        """Clean up reactions that reference non-existent videos"""
        try:
            reactions_ref = self.db.collection('user_video_reactions').where('userId', '==', user_id)
            
            # Check and clean reactions
            for reaction in reactions_ref.stream():
                video_id = reaction.get('videoId')
                if video_id:
                    video = await self.get_video_or_none(video_id, request_id)
                    if not video:
                        reaction.reference.delete()
                        logger.info(f"[{request_id}] Cleaned up orphaned reaction for video {video_id}")
                    
        except Exception as e:
            logger.error(f"[{request_id}] Error during cleanup: {str(e)}")

    async def add_reaction(self, user_id: str, reaction_data: dict, request_id: str) -> dict:
        """Add or update a reaction to a video"""
        logger.info(f"[{request_id}] Adding reaction for video {reaction_data['videoId']}")
        logger.debug(f"[{request_id}] Reaction data: {json.dumps(reaction_data, indent=2)}")
        
        try:
            # Validate video exists first
            video = await self.get_video_or_none(reaction_data['videoId'], request_id)
            if not video:
                raise VideoNotFoundException(reaction_data['videoId'])
            
            now = datetime.datetime.utcnow().isoformat()
            reactions_ref = self.db.collection('user_video_reactions')
            
            # Check if reaction already exists
            existing_reaction = reactions_ref.where('userId', '==', user_id).where('videoId', '==', reaction_data['videoId']).get()
            
            reaction_doc = {
                "userId": user_id,
                "videoId": reaction_data['videoId'],
                "reactionType": reaction_data['reactionType'],
                "reactionDate": now
            }
            
            if existing_reaction:
                # Update existing reaction
                doc = existing_reaction[0]
                logger.info(f"[{request_id}] Updating existing reaction {doc.id}")
                doc.reference.update(reaction_doc)
                reaction_doc['reactionId'] = doc.id
                logger.info(f"[{request_id}] Updated reaction {doc.id} for video {reaction_data['videoId']}")
            else:
                # Create new reaction
                doc_ref = reactions_ref.document()
                logger.info(f"[{request_id}] Creating new reaction")
                doc_ref.set(reaction_doc)
                reaction_doc['reactionId'] = doc_ref.id
                logger.info(f"[{request_id}] Created new reaction {doc_ref.id} for video {reaction_data['videoId']}")
            
            logger.debug(f"[{request_id}] Final reaction data: {json.dumps(reaction_doc, indent=2)}")
            return reaction_doc
        except VideoNotFoundException as e:
            raise e
        except Exception as e:
            logger.error(f"[{request_id}] Error adding reaction: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to add reaction: {str(e)}")

    def convert_timestamps(self, data):
        """Convert datetime objects in the dictionary to ISO format strings."""
        for key, value in data.items():
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data

    async def get_user_reactions(self, user_id: str, request_id: str) -> list:
        """Get all reactions for a user with video data"""
        logger.info(f"[{request_id}] Getting reactions for user {user_id}")
        
        try:
            reactions_ref = self.db.collection('user_video_reactions')
            reactions = reactions_ref.where('userId', '==', user_id).get()
            
            logger.info(f"[{request_id}] Found {len(list(reactions))} reactions")
            
            reaction_list = []
            missing_videos = []
            for reaction in reactions:
                reaction_data = reaction.to_dict()
                reaction_data['reactionId'] = reaction.id
                logger.debug(f"[{request_id}] Processing reaction {reaction.id}")
                
                # Get video data
                video_data = await self.get_video_or_none(reaction_data['videoId'], request_id)
                if video_data:
                    reaction_data['video'] = video_data
                    reaction_list.append(reaction_data)
                    # Use custom encoder for logging
                    logger.debug(f"[{request_id}] Added reaction with video data: {json.dumps(reaction_data, indent=2, cls=CustomJSONEncoder)}")
                else:
                    missing_videos.append(reaction_data['videoId'])
                    logger.warning(f"[{request_id}] Missing video {reaction_data['videoId']} for reaction {reaction.id}")
            
            if missing_videos:
                logger.warning(f"[{request_id}] Found {len(missing_videos)} missing videos: {missing_videos}")
                # Trigger cleanup in background
                await self.cleanup_orphaned_references(user_id, request_id)
            
            logger.info(f"[{request_id}] Returning {len(reaction_list)} valid reactions")
            return reaction_list
        except Exception as e:
            logger.error(f"[{request_id}] Error getting reactions: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get reactions: {str(e)}")

    async def remove_reaction(self, user_id: str, video_id: str) -> dict:
        """Remove a reaction from a video"""
        try:
            reactions_ref = self.db.collection('user_video_reactions')
            reactions = reactions_ref.where('userId', '==', user_id).where('videoId', '==', video_id).get()
            
            if not reactions:
                raise HTTPException(status_code=404, detail="Reaction not found")
            
            for reaction in reactions:
                reaction.reference.delete()
                logger.info(f"Deleted reaction {reaction.id} for video {video_id}")
                
            return {"message": "Reaction removed successfully"}
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"Error removing reaction: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to remove reaction: {str(e)}")
