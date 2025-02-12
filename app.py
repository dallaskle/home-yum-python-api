from fastapi import FastAPI, HTTPException, Depends, Header, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
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
from video_processing.extractor import VideoMetadataExtractor
from video_processing.whisper_extractor import WhisperExtractor
from dotenv import load_dotenv
from langsmith import traceable
from video_processing.vision_analyzer import VisionAnalyzer
import os
from video_processing.video_recipe_analyzer import VideoRecipeAnalyzer
from video_processing.nutrition import NutritionAnalyzer
from features.add_recipe.add_recipe_service import AddRecipeService
from features.user.user_service import UserService
from features.ratings.ratings_service import RatingsService
from features.schedule.schedule_service import ScheduleService
from features.try_list.try_list_service import TryListService
from features.reactions.reactions_service import ReactionsService
from features.feed.feed_service import FeedService
from features.videos.video_service import VideoService
from features.manual_recipe.manual_recipe_service import ManualRecipeService

load_dotenv()

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
        
        # Convert Firestore timestamps to ISO format strings
        if 'uploadedAt' in video_data:
            video_data['uploadedAt'] = video_data['uploadedAt'].isoformat()
        
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
        
        # Check and clean try-list
        for item in try_list_ref.stream():
            video_id = item.get('videoId')
            if video_id:
                video = await get_video_or_none(video_id, request_id)
                    
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
cred = credentials.Certificate(os.getenv('FIREBASE_CREDENTIALS_PATH'))
firebase_admin.initialize_app(cred, {
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET')
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

# Models
class TikTokExtractionRequest(BaseModel):
    video_url: str

class RecipeLogCreate(BaseModel):
    video_url: str

# Initialize VisionAnalyzer
vision_analyzer = VisionAnalyzer()

# Initialize additional extractors/analyzers
video_metadata_extractor = VideoMetadataExtractor()
video_recipe_analyzer = VideoRecipeAnalyzer()
nutrition_analyzer = NutritionAnalyzer()

# Initialize services
add_recipe_service = AddRecipeService(db)
user_service = UserService(db)
ratings_service = RatingsService(db)
schedule_service = ScheduleService(db)
try_list_service = TryListService(db)
reactions_service = ReactionsService(db)
feed_service = FeedService(db)
video_service = VideoService(db)
manual_recipe_service = ManualRecipeService(db)

# Routes
@app.get("/")
async def root():
    return {"message": "HomeYum API is running"}

@app.get("/api/user/profile")
async def get_user_profile(token_data=Depends(verify_token)):
    """Get user profile data from Firestore"""
    return await user_service.get_user_profile(token_data['uid'])

@app.post("/api/user/create")
async def create_user_profile(token_data=Depends(verify_token)):
    """Create a new user profile in Firestore after signup"""
    return await user_service.create_user_profile(token_data['uid'])

@app.put("/api/user/profile")
async def update_user_profile(profile: UserProfile, token_data=Depends(verify_token)):
    """Update user profile in Firestore"""
    return await user_service.update_user_profile(token_data['uid'], profile.dict())

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

@app.post("/api/recipe-log")
@log_operation("create_recipe_log")
async def create_recipe_log(recipe_log: RecipeLogCreate, token_data=Depends(verify_token)):
    """Create a new recipe log entry and start processing the video"""
    request_id = f"create-recipe-log-{int(time.time())}"
    return await add_recipe_service.create_recipe_log(token_data['uid'], recipe_log.video_url, request_id)

@app.get("/api/recipe-log/{log_id}")
@log_operation("get_recipe_log")
async def get_recipe_log(log_id: str, token_data=Depends(verify_token)):
    """Get the status of a recipe log"""
    request_id = f"get-recipe-log-{int(time.time())}"
    return await add_recipe_service.get_recipe_log(token_data['uid'], log_id, request_id)

@app.get("/api/videos/feed")
async def get_video_feed(
    page_size: int = 10,
    last_video_id: Optional[str] = None,
    token_data=Depends(verify_token)
):
    """Get paginated video feed with user reactions and try list status"""
    return await feed_service.get_video_feed(token_data['uid'], page_size, last_video_id)

@app.get("/api/videos/user/{user_id}")
async def get_user_videos(user_id: str, token_data=Depends(verify_token)):
    """Get videos uploaded by a specific user"""
    return await feed_service.get_user_videos(user_id)

# Reaction endpoints
@app.post("/api/videos/reactions")
@log_operation("add_reaction")
async def add_reaction(reaction: VideoReactionCreate, token_data=Depends(verify_token)):
    """Add or update a reaction to a video"""
    request_id = f"reaction-{int(time.time())}"
    return await reactions_service.add_reaction(token_data['uid'], reaction.dict(), request_id)

@app.get("/api/videos/reactions")
@log_operation("get_user_reactions")
async def get_user_reactions(token_data=Depends(verify_token)):
    """Get all reactions for a user with video data"""
    request_id = f"get-reactions-{int(time.time())}"
    return await reactions_service.get_user_reactions(token_data['uid'], request_id)

@app.delete("/api/videos/reactions/{video_id}")
async def remove_reaction(video_id: str, token_data=Depends(verify_token)):
    """Remove a reaction from a video"""
    return await reactions_service.remove_reaction(token_data['uid'], video_id)

# Try List endpoints
@app.post("/api/videos/try-list")
async def add_to_try_list(try_item: TryListItemCreate, token_data=Depends(verify_token)):
    """Add a video to user's try list"""
    return await try_list_service.add_to_try_list(token_data['uid'], try_item.dict())

@app.get("/api/videos/try-list")
@log_operation("get_try_list")
async def get_try_list(token_data=Depends(verify_token)):
    """Get user's try list with video data"""
    request_id = f"get-trylist-{int(time.time())}"
    return await try_list_service.get_try_list(token_data['uid'], request_id)

@app.delete("/api/videos/try-list/{video_id}")
async def remove_from_try_list(video_id: str, token_data=Depends(verify_token)):
    """Remove a video from user's try list"""
    return await try_list_service.remove_from_try_list(token_data['uid'], video_id)

# Meal Schedule endpoints
@app.post("/api/meals/schedule")
async def schedule_meal(meal: MealScheduleCreate, token_data=Depends(verify_token)):
    """Schedule a meal for a specific date and time"""
    return await schedule_service.schedule_meal(token_data['uid'], meal.dict())

@app.get("/api/meals/schedule")
async def get_scheduled_meals(token_data=Depends(verify_token)):
    """Get user's scheduled meals"""
    return await schedule_service.get_scheduled_meals(token_data['uid'])

@app.put("/api/meals/schedule/{meal_id}")
async def update_meal_schedule(meal_id: str, meal: MealScheduleUpdate, token_data=Depends(verify_token)):
    """Update a scheduled meal's date and time"""
    return await schedule_service.update_meal_schedule(token_data['uid'], meal_id, meal.dict())

@app.delete("/api/meals/schedule/{meal_id}")
async def delete_meal_schedule(meal_id: str, token_data=Depends(verify_token)):
    """Delete a scheduled meal"""
    return await schedule_service.delete_meal_schedule(token_data['uid'], meal_id)

@app.get("/api/videos/{video_id}/recipe")
async def get_recipe_data(video_id: str, token_data=Depends(verify_token)):
    """Get recipe data for a video including ingredients, instructions, and nutrition info"""
    return await video_service.get_recipe_data(video_id)

@app.get("/api/videos/{video_id}")
async def get_video(video_id: str, token_data=Depends(verify_token)):
    """Get single video details"""
    return await video_service.get_video(video_id)

@app.post("/api/videos/{video_id}/recipe/generate")
async def generate_recipe_data(video_id: str, token_data=Depends(verify_token)):
    """Generate random recipe data for a video"""
    return await video_service.generate_recipe_data(video_id)

@app.post("/api/meals/rate")
async def rate_meal(rating_data: dict, token_data=Depends(verify_token)):
    """Rate a meal"""
    return await ratings_service.rate_meal(token_data['uid'], rating_data)

@app.get("/api/meals/ratings")
async def get_user_ratings(token_data=Depends(verify_token)):
    """Get user's meal ratings"""
    return await ratings_service.get_user_ratings(token_data['uid'])

@app.get("/api/meals/ratings/aggregated")
@log_operation("get_aggregated_ratings")
async def get_aggregated_ratings(token_data=Depends(verify_token)):
    """Get aggregated ratings for each video with video details"""
    request_id = f"get-agg-ratings-{int(time.time())}"
    return await ratings_service.get_aggregated_ratings(token_data['uid'], request_id)

@app.post("/api/extract/metadata")
@log_operation("extract_video_metadata")
async def extract_video_metadata(video_url: str):
    """Extract metadata from a video URL (YouTube, TikTok, Instagram)"""
    try:
        logger.info(f"Extracting metadata from URL: {video_url}")
        metadata = video_metadata_extractor.extract_metadata(video_url)
        
        if not metadata:
            raise HTTPException(
                status_code=400,
                detail="Failed to extract metadata from the provided URL"
            )
        
        return {
            "success": True,
            "metadata": metadata
        }
    except Exception as e:
        logger.error(f"Error extracting video metadata: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract metadata: {str(e)}"
        )

@app.post("/api/extract/whisper/enhanced")
@log_operation("extract_enhanced_whisper")
async def extract_enhanced_whisper(
    video_url: str,
    prompt: Optional[str] = None
):
    """Enhanced whisper extraction with optional prompt guidance"""
    try:
        # Initialize WhisperExtractor
        whisper = WhisperExtractor()
        
        logger.info(f"Starting enhanced extraction for URL: {video_url}")
        
        # Extract transcript with prompt if provided
        result = whisper.extract_transcript(video_url, prompt)
        if not result:
            logger.error("No result returned from whisper.extract_transcript")
            raise HTTPException(
                status_code=400,
                detail="Failed to extract transcription"
            )
        
        logger.info("Successfully extracted enhanced transcription")
        return {
            "success": True,
            "transcription": result
        }
    except Exception as e:
        logger.error(f"Error extracting enhanced Whisper transcription: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract transcription: {str(e)}"
        )

@app.post("/api/analyze/recipe/video")
@log_operation("analyze_video_recipe")
async def analyze_video_recipe(
    video_url: str,
    scene_analysis: bool = False
):
    """Analyze a video for recipe information with optional scene-by-scene analysis"""
    try:
        logger.info(f"Starting recipe analysis for URL: {video_url}")
        
        # Analyze the video
        analysis = await video_recipe_analyzer.analyze_video(video_url)
        
        if not analysis.get('success'):
            raise HTTPException(
                status_code=400,
                detail="Failed to analyze video recipe"
            )
        
        # Remove scene analyses if not requested
        if not scene_analysis and 'scene_analyses' in analysis:
            del analysis['scene_analyses']
        
        return analysis
    except Exception as e:
        logger.error(f"Error analyzing video recipe: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze recipe: {str(e)}"
        )

@app.post("/api/analyze/nutrition/serving-size")
@log_operation("analyze_serving_size")
async def analyze_serving_size(recipe_info: str):
    """Analyze recipe for serving sizes for 4 people"""
    try:
        logger.info("Starting serving size analysis")
        
        result = await nutrition_analyzer.get_serving_sizes(recipe_info)
        if not result.get('success'):
            raise HTTPException(
                status_code=400,
                detail="Failed to analyze serving sizes"
            )
        
        return result
    except Exception as e:
        logger.error(f"Error analyzing serving sizes: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze serving sizes: {str(e)}"
        )

@app.post("/api/analyze/nutrition/info")
@log_operation("analyze_nutrition_info")
async def analyze_nutrition_info(serving_sizes: str):
    """Get nutritional information based on serving sizes"""
    try:
        logger.info("Starting nutritional information analysis")
        
        result = await nutrition_analyzer.get_nutrition_info(serving_sizes)
        if not result.get('success'):
            raise HTTPException(
                status_code=400,
                detail="Failed to analyze nutritional information"
            )
        
        return result
    except Exception as e:
        logger.error(f"Error analyzing nutritional information: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze nutritional information: {str(e)}"
        )

# Add more endpoints as needed based on your PRD requirements

# Manual Recipe endpoints
@app.post("/api/manual-recipe/generate")
@log_operation("generate_manual_recipe")
async def generate_manual_recipe(request: Request):
    """Generate initial recipe and meal image from prompt."""
    request_id = f"generate-recipe-{int(time.time())}"
    uid = "61d1f2c8-2100-4b5d-92df-5e5705a0383d"  # Hardcoded UID
    
    # Get the prompt from request body
    body = await request.json()
    if 'prompt' not in body:
        raise HTTPException(status_code=422, detail="Prompt is required in request body")
    prompt = body['prompt']
    
    # Create recipe log
    log_result = await manual_recipe_service.create_recipe_log(uid, prompt, request_id)
    
    # Generate initial recipe
    result = await manual_recipe_service.generate_initial_recipe(log_result['logId'], request_id)
    
    return result

@app.put("/api/manual-recipe/{log_id}/update")
@log_operation("update_manual_recipe")
async def update_manual_recipe(
    log_id: str,
    updates: Dict[str, Any],
    token_data=Depends(verify_token)
):
    """Update recipe or image based on user feedback."""
    request_id = f"update-recipe-{int(time.time())}"
    return await manual_recipe_service.update_recipe(log_id, updates, request_id)

@app.post("/api/manual-recipe/{log_id}/confirm")
@log_operation("confirm_manual_recipe")
async def confirm_manual_recipe(log_id: str, token_data=Depends(verify_token)):
    """Confirm recipe and generate final assets."""
    request_id = f"confirm-recipe-{int(time.time())}"
    return await manual_recipe_service.confirm_recipe(log_id, request_id)

@app.get("/api/manual-recipe/{log_id}")
@log_operation("get_manual_recipe")
async def get_manual_recipe(log_id: str, token_data=Depends(verify_token)):
    """Get the current status of a manual recipe."""
    request_id = f"get-recipe-{int(time.time())}"
    return await manual_recipe_service.get_recipe_log(log_id, request_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
