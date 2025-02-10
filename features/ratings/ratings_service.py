import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException
import time

logger = logging.getLogger(__name__)

class RatingsService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def rate_meal(self, user_id: str, rating_data: dict) -> dict:
        """Rate a meal"""
        try:
            video_id = rating_data['videoId']
            rating = rating_data['rating']
            meal_id = rating_data.get('mealId')
            comment = rating_data.get('comment')
            
            rating_ref = self.db.collection('meal_ratings').document()
            rating_data = {
                "userId": user_id,
                "videoId": video_id,
                "mealId": meal_id,
                "rating": rating,
                "comment": comment,
                "ratedAt": datetime.datetime.utcnow().isoformat()
            }
            
            rating_ref.set(rating_data)
            rating_data['ratingId'] = rating_ref.id
            
            return rating_data
        except Exception as e:
            logger.error(f"Error rating meal: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_user_ratings(self, user_id: str) -> list:
        """Get user's meal ratings"""
        try:
            ratings = self.db.collection('meal_ratings').where('userId', '==', user_id).get()
            
            return [
                {**rating.to_dict(), 'ratingId': rating.id}
                for rating in ratings
            ]
        except Exception as e:
            logger.error(f"Error getting ratings: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_aggregated_ratings(self, user_id: str, request_id: str) -> list:
        """Get aggregated ratings for each video with video details"""
        logger.info(f"[{request_id}] Getting aggregated ratings for user {user_id}")
        
        try:
            ratings_ref = self.db.collection('meal_ratings').where('userId', '==', user_id)
            ratings = ratings_ref.get()
            
            # Group ratings by videoId
            video_ratings = {}
            for rating in ratings:
                rating_data = rating.to_dict()
                video_id = rating_data['videoId']
                
                if video_id not in video_ratings:
                    video_ratings[video_id] = {
                        'ratings': [],
                        'comments': [],
                        'lastRated': rating_data['ratedAt']
                    }
                
                video_ratings[video_id]['ratings'].append(rating_data['rating'])
                if rating_data.get('comment'):
                    video_ratings[video_id]['comments'].append(rating_data['comment'])
                
                # Update lastRated if this rating is more recent
                if rating_data['ratedAt'] > video_ratings[video_id]['lastRated']:
                    video_ratings[video_id]['lastRated'] = rating_data['ratedAt']
            
            # Calculate averages and get video details
            result = []
            for video_id, data in video_ratings.items():
                # Get video details
                video_doc = self.db.collection('videos').document(video_id).get()
                if not video_doc.exists:
                    logger.warning(f"[{request_id}] Video {video_id} not found")
                    continue
                    
                video_data = video_doc.to_dict()
                
                # Calculate average rating
                avg_rating = sum(data['ratings']) / len(data['ratings'])
                
                result.append({
                    'videoId': video_id,
                    'averageRating': round(avg_rating, 1),
                    'numberOfRatings': len(data['ratings']),
                    'lastRated': data['lastRated'],
                    'comments': data['comments'],
                    'video': {
                        'mealName': video_data.get('mealName', ''),
                        'mealDescription': video_data.get('mealDescription', ''),
                        'thumbnailUrl': video_data.get('thumbnailUrl', '')
                    }
                })
            
            # Sort by lastRated date (most recent first)
            result.sort(key=lambda x: x['lastRated'], reverse=True)
            
            logger.info(f"[{request_id}] Returning {len(result)} aggregated ratings")
            return result
        except Exception as e:
            logger.error(f"[{request_id}] Error getting aggregated ratings: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get aggregated ratings: {str(e)}")
