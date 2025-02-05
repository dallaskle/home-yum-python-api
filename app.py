from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
from pydantic import BaseModel
import json
import datetime
import logging
import tempfile
import requests
from urllib.parse import urlparse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="HomeYum API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:19006", "exp://localhost:19000"],  # Expo development URLs
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
    """Get paginated video feed"""
    try:
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
async def add_reaction(reaction: VideoReactionCreate, token_data=Depends(verify_token)):
    """Add or update a reaction to a video"""
    try:
        user_id = token_data['uid']
        now = datetime.datetime.utcnow().isoformat()
        
        # Check if reaction already exists
        reactions_ref = db.collection('user_video_reactions')
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
            doc.reference.update(reaction_data)
            reaction_data['reactionId'] = doc.id
        else:
            # Create new reaction
            doc_ref = reactions_ref.document()
            doc_ref.set(reaction_data)
            reaction_data['reactionId'] = doc_ref.id
        
        return reaction_data
    except Exception as e:
        logger.error(f"Error adding reaction: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/videos/reactions/{video_id}")
async def remove_reaction(video_id: str, token_data=Depends(verify_token)):
    """Remove a reaction from a video"""
    try:
        user_id = token_data['uid']
        reactions_ref = db.collection('user_video_reactions')
        reactions = reactions_ref.where('userId', '==', user_id).where('videoId', '==', video_id).get()
        
        for reaction in reactions:
            reaction.reference.delete()
            
        return {"message": "Reaction removed successfully"}
    except Exception as e:
        logger.error(f"Error removing reaction: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/reactions")
async def get_user_reactions(token_data=Depends(verify_token)):
    """Get all reactions for a user"""
    try:
        user_id = token_data['uid']
        reactions_ref = db.collection('user_video_reactions')
        reactions = reactions_ref.where('userId', '==', user_id).get()
        
        return [{"reactionId": reaction.id, **reaction.to_dict()} for reaction in reactions]
    except Exception as e:
        logger.error(f"Error getting reactions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Try List endpoints
@app.post("/api/videos/try-list")
async def add_to_try_list(try_item: TryListItemCreate, token_data=Depends(verify_token)):
    """Add a video to user's try list"""
    try:
        user_id = token_data['uid']
        now = datetime.datetime.utcnow().isoformat()
        
        try_list_ref = db.collection('user_try_list')
        existing_item = try_list_ref.where('userId', '==', user_id).where('videoId', '==', try_item.videoId).get()
        
        if existing_item:
            raise HTTPException(status_code=400, detail="Video already in try list")
        
        try_list_data = {
            "userId": user_id,
            "videoId": try_item.videoId,
            "notes": try_item.notes,
            "addedDate": now
        }
        
        doc_ref = try_list_ref.document()
        doc_ref.set(try_list_data)
        try_list_data['tryListId'] = doc_ref.id
        
        return try_list_data
    except Exception as e:
        logger.error(f"Error adding to try list: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/videos/try-list/{video_id}")
async def remove_from_try_list(video_id: str, token_data=Depends(verify_token)):
    """Remove a video from user's try list"""
    try:
        user_id = token_data['uid']
        try_list_ref = db.collection('user_try_list')
        items = try_list_ref.where('userId', '==', user_id).where('videoId', '==', video_id).get()
        
        for item in items:
            item.reference.delete()
            
        return {"message": "Removed from try list successfully"}
    except Exception as e:
        logger.error(f"Error removing from try list: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/try-list")
async def get_try_list(token_data=Depends(verify_token)):
    """Get user's try list"""
    try:
        user_id = token_data['uid']
        try_list_ref = db.collection('user_try_list')
        items = try_list_ref.where('userId', '==', user_id).get()
        
        return [{"tryListId": item.id, **item.to_dict()} for item in items]
    except Exception as e:
        logger.error(f"Error getting try list: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add more endpoints as needed based on your PRD requirements

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
