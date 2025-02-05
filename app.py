from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
from pydantic import BaseModel
import json
import datetime
import logging
import tempfile
import requests
from urllib.parse import urlparse
import time
from functools import wraps

# Set up logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Decorator for timing and logging operations
def log_operation(operation_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            request_id = f"{operation_name}-{int(start_time)}"
            
            # Log the start of operation
            logger.info(f"[{request_id}] Starting {operation_name}")
            
            # Log request data if available
            if kwargs.get('token_data'):
                logger.info(f"[{request_id}] User ID: {kwargs['token_data']['uid']}")
            
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000
                logger.info(f"[{request_id}] Completed {operation_name} in {execution_time:.2f}ms")
                return result
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                logger.error(f"[{request_id}] Failed {operation_name} in {execution_time:.2f}ms: {str(e)}")
                raise
        return wrapper
    return decorator

# Custom exceptions
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

class ValidationException(HTTPException):
    def __init__(self, message: str):
        super().__init__(
            status_code=400,
            detail=message
        )

# Enhanced helper functions
async def get_video_or_none(video_id: str, request_id: str = None) -> Optional[dict]:
    """Get video document or return None if not found"""
    start_time = time.time()
    logger.info(f"[{request_id}] Fetching video: {video_id}")
    
    try:
        video_ref = db.collection('videos').document(video_id)
        video = video_ref.get()
        if not video.exists:
            logger.warning(f"[{request_id}] Video not found: {video_id} - This may indicate an orphaned reference")
            return None
        
        video_data = video.to_dict()
        video_data['videoId'] = video.id  # Include the ID in the data
        execution_time = (time.time() - start_time) * 1000
        logger.info(f"[{request_id}] Retrieved video {video_id} in {execution_time:.2f}ms")
        logger.debug(f"[{request_id}] Video data: {json.dumps(video_data, indent=2)}")
        
        return video_data
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"[{request_id}] Error fetching video {video_id} in {execution_time:.2f}ms: {str(e)}")
        return None

async def cleanup_orphaned_references(user_id: str, request_id: str = None):
    """Clean up reactions and try-list items that reference non-existent videos"""
    try:
        # Get all user's reactions
        reactions_ref = db.collection('user_video_reactions').where('userId', '==', user_id)
        try_list_ref = db.collection('user_try_list').where('userId', '==', user_id)
        
        # Check and clean reactions
        for reaction in reactions_ref.stream():
            video_id = reaction.get('videoId')
            if video_id:
                video = await get_video_or_none(video_id, request_id)
                if not video:
                    logger.warning(f"[{request_id}] Cleaning up orphaned reaction {reaction.id} for missing video {video_id}")
                    reaction.reference.delete()
        
        # Check and clean try-list
        for item in try_list_ref.stream():
            video_id = item.get('videoId')
            if video_id:
                video = await get_video_or_none(video_id, request_id)
                if not video:
                    logger.warning(f"[{request_id}] Cleaning up orphaned try-list item {item.id} for missing video {video_id}")
                    item.reference.delete()
                    
    except Exception as e:
        logger.error(f"[{request_id}] Error during cleanup: {str(e)}")

# Initialize FastAPI app
app = FastAPI(title="HomeYum API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:19006", "exp://localhost:19000", "exp://192.168.1.158:19000", "*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin SDK
cred = credentials.Certificate("./home-yum-36d51-firebase-adminsdk-fbsvc-dbc5ba14e4.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'home-yum-36d51.firebasestorage.app'
})

# Get Firestore client
db = firestore.client()

# Get Storage bucket
bucket = storage.bucket()

# Dependency to verify Firebase ID token
async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(' ')[1]
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")

# Models
class UserProfile(BaseModel):
    userId: str
    username: str
    email: str
    profilePic: Optional[str] = None
    createdAt: str
    updatedAt: str
    passwordHash: Optional[str] = None  # We don't expose this

# Models for reactions
class VideoReactionCreate(BaseModel):
    videoId: str
    reactionType: str

class TryListItemCreate(BaseModel):
    videoId: str
    notes: Optional[str] = None

# Meal Schedule Models
class MealScheduleCreate(BaseModel):
    videoId: str
    mealDate: str
    mealTime: str

class MealScheduleUpdate(BaseModel):
    mealDate: str
    mealTime: str

# Routes
@app.get("/")
async def root():
    return {"message": "HomeYum API is running"}

@app.get("/api/user/profile")
async def get_user_profile(token_data=Depends(verify_token)):
    """Get user profile data from Firestore"""
    user_id = token_data['uid']
    try:
        doc_ref = db.collection('users').document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            user_data = doc.to_dict()
            # Remove sensitive data
            if 'passwordHash' in user_data:
                del user_data['passwordHash']
            return user_data
        logger.error(f"User profile not found for ID: {user_id}")
        raise HTTPException(status_code=404, detail="User profile not found")
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/create")
async def create_user_profile(token_data=Depends(verify_token)):
    """Create a new user profile in Firestore after signup"""
    user_id = token_data['uid']
    try:
        # Get user email from Firebase Auth
        user = auth.get_user(user_id)
        
        # Create user document
        now = datetime.datetime.utcnow().isoformat()
        user_data = {
            "userId": user_id,
            "email": user.email,
            "username": user.email.split('@')[0],  # Default username from email
            "createdAt": now,
            "updatedAt": now
        }
        
        doc_ref = db.collection('users').document(user_id)
        doc_ref.set(user_data)
        return user_data
    except Exception as e:
        logger.error(f"Error creating user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/user/profile")
async def update_user_profile(profile: UserProfile, token_data=Depends(verify_token)):
    """Update user profile in Firestore"""
    user_id = token_data['uid']
    if user_id != profile.userId:
        raise HTTPException(status_code=403, detail="Cannot update other user's profile")
        
    try:
        profile_dict = profile.dict(exclude={'passwordHash'})  # Never update password hash
        profile_dict["updatedAt"] = datetime.datetime.utcnow().isoformat()
        
        doc_ref = db.collection('users').document(user_id)
        doc_ref.update(profile_dict)
        return {"message": "Profile updated successfully"}
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Video Feed Endpoints
class VideoResponse(BaseModel):
    videoId: str
    videoTitle: str
    videoDescription: str
    mealName: str
    mealDescription: str
    videoUrl: str
    thumbnailUrl: str
    duration: int
    uploadedAt: str
    source: str

@app.get("/api/videos/feed")
async def get_video_feed(
    page_size: int = 10,
    last_video_id: Optional[str] = None,
    token_data=Depends(verify_token)
):
    """Get paginated video feed with user reactions and try list status"""
    try:
        user_id = token_data['uid']
        query = db.collection('videos').order_by('uploadedAt', direction=firestore.Query.DESCENDING)
        
        if last_video_id:
            last_doc = db.collection('videos').document(last_video_id).get()
            if last_doc.exists:
                query = query.start_after(last_doc)
        
        query = query.limit(page_size)
        docs = query.stream()
        
        videos = []
        for doc in docs:
            video_data = doc.to_dict()
            video_data['videoId'] = doc.id
            
            # Get user's reaction for this video
            reactions_ref = db.collection('user_video_reactions')
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
            try_list_ref = db.collection('user_try_list')
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

@app.get("/api/videos/{video_id}")
async def get_video(video_id: str, token_data=Depends(verify_token)):
    """Get single video details"""
    try:
        doc_ref = db.collection('videos').document(video_id)
        doc = doc_ref.get()
        if doc.exists:
            video_data = doc.to_dict()
            video_data['videoId'] = doc.id
            return video_data
        raise HTTPException(status_code=404, detail="Video not found")
    except Exception as e:
        logger.error(f"Error getting video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/user/{user_id}")
async def get_user_videos(user_id: str, token_data=Depends(verify_token)):
    """Get videos uploaded by a specific user"""
    try:
        # Query videos collection with user_id filter
        videos_ref = db.collection('videos')
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

# Reaction endpoints
@app.post("/api/videos/reactions")
@log_operation("add_reaction")
async def add_reaction(reaction: VideoReactionCreate, token_data=Depends(verify_token)):
    """Add or update a reaction to a video"""
    request_id = f"reaction-{int(time.time())}"
    logger.info(f"[{request_id}] Adding reaction for video {reaction.videoId}")
    logger.debug(f"[{request_id}] Reaction data: {json.dumps(reaction.dict(), indent=2)}")
    
    try:
        user_id = token_data['uid']
        
        # Validate video exists first
        await get_video_or_none(reaction.videoId, request_id)
        
        now = datetime.datetime.utcnow().isoformat()
        reactions_ref = db.collection('user_video_reactions')
        
        # Check if reaction already exists
        existing_reaction = reactions_ref.where('userId', '==', user_id).where('videoId', '==', reaction.videoId).get()
        
        reaction_data = {
            "userId": user_id,
            "videoId": reaction.videoId,
            "reactionType": reaction.reactionType,
            "reactionDate": now
        }
        
        if existing_reaction:
            # Update existing reaction
            doc = existing_reaction[0]
            logger.info(f"[{request_id}] Updating existing reaction {doc.id}")
            doc.reference.update(reaction_data)
            reaction_data['reactionId'] = doc.id
            logger.info(f"[{request_id}] Updated reaction {doc.id} for video {reaction.videoId}")
        else:
            # Create new reaction
            doc_ref = reactions_ref.document()
            logger.info(f"[{request_id}] Creating new reaction")
            doc_ref.set(reaction_data)
            reaction_data['reactionId'] = doc_ref.id
            logger.info(f"[{request_id}] Created new reaction {doc_ref.id} for video {reaction.videoId}")
        
        logger.debug(f"[{request_id}] Final reaction data: {json.dumps(reaction_data, indent=2)}")
        return reaction_data
    except VideoNotFoundException as e:
        raise e
    except Exception as e:
        logger.error(f"[{request_id}] Error adding reaction: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add reaction: {str(e)}")

@app.get("/api/videos/reactions")
@log_operation("get_user_reactions")
async def get_user_reactions(token_data=Depends(verify_token)):
    """Get all reactions for a user with video data"""
    request_id = f"get-reactions-{int(time.time())}"
    logger.info(f"[{request_id}] Getting reactions for user {token_data['uid']}")
    
    try:
        user_id = token_data['uid']
        reactions_ref = db.collection('user_video_reactions')
        reactions = reactions_ref.where('userId', '==', user_id).get()
        
        logger.info(f"[{request_id}] Found {len(list(reactions))} reactions")
        
        reaction_list = []
        missing_videos = []
        for reaction in reactions:
            reaction_data = reaction.to_dict()
            reaction_data['reactionId'] = reaction.id
            logger.debug(f"[{request_id}] Processing reaction {reaction.id}")
            
            # Get video data
            video_data = await get_video_or_none(reaction_data['videoId'], request_id)
            if video_data:
                reaction_data['video'] = video_data
                reaction_list.append(reaction_data)
                logger.debug(f"[{request_id}] Added reaction with video data: {json.dumps(reaction_data, indent=2)}")
            else:
                missing_videos.append(reaction_data['videoId'])
                logger.warning(f"[{request_id}] Missing video {reaction_data['videoId']} for reaction {reaction.id}")
        
        if missing_videos:
            logger.warning(f"[{request_id}] Found {len(missing_videos)} missing videos: {missing_videos}")
            # Trigger cleanup in background
            await cleanup_orphaned_references(user_id, request_id)
        
        logger.info(f"[{request_id}] Returning {len(reaction_list)} valid reactions")
        return reaction_list
    except Exception as e:
        logger.error(f"[{request_id}] Error getting reactions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get reactions: {str(e)}")

@app.delete("/api/videos/reactions/{video_id}")
async def remove_reaction(video_id: str, token_data=Depends(verify_token)):
    """Remove a reaction from a video"""
    try:
        user_id = token_data['uid']
        reactions_ref = db.collection('user_video_reactions')
        reactions = reactions_ref.where('userId', '==', user_id).where('videoId', '==', video_id).get()
        
        if not reactions:
            raise HTTPException(status_code=404, detail="Reaction not found")
        
        for reaction in reactions:
            reaction.reference.delete()
            logger.info(f"Deleted reaction {reaction.id} for video {video_id}")
            
        return {"message": "Reaction removed successfully"}
    except Exception as e:
        logger.error(f"Error removing reaction: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to remove reaction: {str(e)}")

# Try List endpoints
@app.post("/api/videos/try-list")
async def add_to_try_list(try_item: TryListItemCreate, token_data=Depends(verify_token)):
    """Add a video to user's try list"""
    try:
        user_id = token_data['uid']
        
        # Validate video exists first
        await get_video_or_none(try_item.videoId, request_id)
        
        now = datetime.datetime.utcnow().isoformat()
        try_list_ref = db.collection('user_try_list')
        
        # Check for duplicate
        existing_item = try_list_ref.where('userId', '==', user_id).where('videoId', '==', try_item.videoId).get()
        if existing_item:
            raise DuplicateEntryException("Video already in try list")
        
        try_list_data = {
            "userId": user_id,
            "videoId": try_item.videoId,
            "notes": try_item.notes,
            "addedDate": now
        }
        
        doc_ref = try_list_ref.document()
        doc_ref.set(try_list_data)
        try_list_data['tryListId'] = doc_ref.id
        logger.info(f"Added video {try_item.videoId} to try list for user {user_id}")
        
        return try_list_data
    except (VideoNotFoundException, DuplicateEntryException) as e:
        raise e
    except Exception as e:
        logger.error(f"Error adding to try list: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add to try list: {str(e)}")

@app.get("/api/videos/try-list")
@log_operation("get_try_list")
async def get_try_list(token_data=Depends(verify_token)):
    """Get user's try list with video data"""
    request_id = f"get-trylist-{int(time.time())}"
    logger.info(f"[{request_id}] Getting try list for user {token_data['uid']}")
    
    try:
        user_id = token_data['uid']
        try_list_ref = db.collection('user_try_list')
        items = try_list_ref.where('userId', '==', user_id).get()
        
        logger.info(f"[{request_id}] Found {len(list(items))} try list items")
        
        try_list = []
        missing_videos = []
        for item in items:
            try_list_data = item.to_dict()
            try_list_data['tryListId'] = item.id
            logger.debug(f"[{request_id}] Processing try list item {item.id}")
            
            # Get video data
            video_data = await get_video_or_none(try_list_data['videoId'], request_id)
            if video_data:
                try_list_data['video'] = video_data
                try_list.append(try_list_data)
                logger.debug(f"[{request_id}] Added try list item with video data: {json.dumps(try_list_data, indent=2)}")
            else:
                missing_videos.append(try_list_data['videoId'])
                logger.warning(f"[{request_id}] Missing video {try_list_data['videoId']} for try list item {item.id}")
        
        if missing_videos:
            logger.warning(f"[{request_id}] Found {len(missing_videos)} missing videos: {missing_videos}")
            # Trigger cleanup in background
            await cleanup_orphaned_references(user_id, request_id)
        
        logger.info(f"[{request_id}] Returning {len(try_list)} valid try list items")
        return try_list
    except Exception as e:
        logger.error(f"[{request_id}] Error getting try list: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get try list: {str(e)}")

@app.delete("/api/videos/try-list/{video_id}")
async def remove_from_try_list(video_id: str, token_data=Depends(verify_token)):
    """Remove a video from user's try list"""
    try:
        user_id = token_data['uid']
        try_list_ref = db.collection('user_try_list')
        items = try_list_ref.where('userId', '==', user_id).where('videoId', '==', video_id).get()
        
        if not items:
            raise HTTPException(status_code=404, detail="Video not found in try list")
        
        for item in items:
            item.reference.delete()
            logger.info(f"Removed video {video_id} from try list for user {user_id}")
            
        return {"message": "Removed from try list successfully"}
    except Exception as e:
        logger.error(f"Error removing from try list: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to remove from try list: {str(e)}")

# Meal Schedule endpoints
@app.post("/api/meals/schedule")
async def schedule_meal(meal: MealScheduleCreate, token_data=Depends(verify_token)):
    """Schedule a meal for a specific date and time"""
    try:
        user_id = token_data['uid']
        now = datetime.datetime.utcnow().isoformat()
        
        # Create meal document
        meal_data = {
            "userId": user_id,
            "videoId": meal.videoId,
            "mealDate": meal.mealDate,
            "mealTime": meal.mealTime,
            "completed": False,
            "createdAt": now,
            "updatedAt": now
        }
        
        doc_ref = db.collection('meals').document()
        doc_ref.set(meal_data)
        
        meal_data['mealId'] = doc_ref.id
        return meal_data
    except Exception as e:
        logger.error(f"Error scheduling meal: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/meals/schedule")
async def get_scheduled_meals(token_data=Depends(verify_token)):
    """Get all scheduled meals for a user"""
    try:
        user_id = token_data['uid']
        meals_ref = db.collection('meals')
        meals = meals_ref.where('userId', '==', user_id).order_by('mealDate').order_by('mealTime').get()
        
        # Get all meal documents with video details
        meal_list = []
        for meal in meals:
            meal_data = meal.to_dict()
            meal_data['mealId'] = meal.id
            
            # Get video details
            video_ref = db.collection('videos').document(meal_data['videoId'])
            video_doc = video_ref.get()
            if video_doc.exists:
                video_data = video_doc.to_dict()
                meal_data['video'] = {
                    'videoId': video_doc.id,
                    'mealName': video_data.get('mealName', ''),
                    'mealDescription': video_data.get('mealDescription', ''),
                    'thumbnailUrl': video_data.get('thumbnailUrl', '')
                }
            
            meal_list.append(meal_data)
        
        return meal_list
    except Exception as e:
        logger.error(f"Error getting scheduled meals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/meals/schedule/{meal_id}")
async def update_meal_schedule(meal_id: str, meal: MealScheduleUpdate, token_data=Depends(verify_token)):
    """Update a scheduled meal's date and time"""
    try:
        user_id = token_data['uid']
        meal_ref = db.collection('meals').document(meal_id)
        meal_doc = meal_ref.get()
        
        if not meal_doc.exists:
            raise HTTPException(status_code=404, detail="Meal schedule not found")
            
        meal_data = meal_doc.to_dict()
        if meal_data['userId'] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this meal schedule")
        
        update_data = {
            "mealDate": meal.mealDate,
            "mealTime": meal.mealTime,
            "updatedAt": datetime.datetime.utcnow().isoformat()
        }
        
        meal_ref.update(update_data)
        
        return {
            "mealId": meal_id,
            **meal_data,
            **update_data
        }
    except Exception as e:
        logger.error(f"Error updating meal schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/meals/schedule/{meal_id}")
async def delete_meal_schedule(meal_id: str, token_data=Depends(verify_token)):
    """Delete a scheduled meal"""
    try:
        user_id = token_data['uid']
        meal_ref = db.collection('meals').document(meal_id)
        meal_doc = meal_ref.get()
        
        if not meal_doc.exists:
            raise HTTPException(status_code=404, detail="Meal schedule not found")
            
        meal_data = meal_doc.to_dict()
        if meal_data['userId'] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this meal schedule")
        
        meal_ref.delete()
        return {"message": "Meal schedule deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting meal schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add more endpoints as needed based on your PRD requirements

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
