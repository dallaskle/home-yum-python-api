import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException
from typing import Optional, List

logger = logging.getLogger(__name__)

class FeedService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def get_video_feed(self, user_id: str, page_size: int = 10, last_video_id: Optional[str] = None) -> List[dict]:
        """Get paginated video feed with user reactions and try list status"""
        try:
            query = self.db.collection('videos').order_by('uploadedAt', direction=firestore.Query.DESCENDING)
            
            if last_video_id:
                last_doc = self.db.collection('videos').document(last_video_id).get()
                if last_doc.exists:
                    query = query.start_after(last_doc)
            
            query = query.limit(page_size)
            docs = query.stream()
            
            videos = []
            for doc in docs:
                video_data = doc.to_dict()
                video_data['videoId'] = doc.id
                
                # Get user's reaction for this video
                reactions_ref = self.db.collection('user_video_reactions')
                reaction = reactions_ref.where('userId', '==', user_id).where('videoId', '==', doc.id).get()
                
                # Add reaction data if exists
                if reaction:
                    reaction_data = reaction[0].to_dict()
                    video_data['userReaction'] = {
                        'reactionId': reaction[0].id,
                        'reactionType': reaction_data['reactionType'],
                        'reactionDate': reaction_data['reactionDate']
                    }
                else:
                    video_data['userReaction'] = None

                # Get try list status for this video
                try_list_ref = self.db.collection('user_try_list')
                try_list_item = try_list_ref.where('userId', '==', user_id).where('videoId', '==', doc.id).get()
                
                # Add try list data if exists
                if try_list_item:
                    try_list_data = try_list_item[0].to_dict()
                    video_data['tryListItem'] = {
                        'tryListId': try_list_item[0].id,
                        'addedDate': try_list_data['addedDate'],
                        'notes': try_list_data.get('notes')
                    }
                else:
                    video_data['tryListItem'] = None
                
                videos.append(video_data)
            
            return videos
        except Exception as e:
            logger.error(f"Error getting video feed: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_user_videos(self, user_id: str) -> List[dict]:
        """Get videos uploaded by a specific user"""
        try:
            # Query videos collection with user_id filter
            videos_ref = self.db.collection('videos')
            query = videos_ref.where('userId', '==', user_id).order_by('uploadedAt', direction=firestore.Query.DESCENDING)
            docs = query.stream()
            
            videos = []
            for doc in docs:
                video_data = doc.to_dict()
                video_data['videoId'] = doc.id
                videos.append(video_data)
            
            logger.info(f"Found {len(videos)} videos for user {user_id}")
            logger.info(f"Sample video data: {videos[0] if videos else 'No videos found'}")
            
            return videos
        except Exception as e:
            logger.error(f"Error getting user videos: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
