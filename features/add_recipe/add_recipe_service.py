import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException
from video_processing.extractor import VideoMetadataExtractor
from video_processing.whisper_extractor import WhisperExtractor
from video_processing.video_recipe_analyzer import VideoRecipeAnalyzer
from video_processing.nutrition import NutritionAnalyzer
from features.add_recipe.generate_recipe_items import RecipeGenerator

logger = logging.getLogger(__name__)

class AddRecipeService:
    def __init__(self, db: firestore.Client):
        self.db = db
        self.metadata_extractor = VideoMetadataExtractor()
        self.whisper_extractor = WhisperExtractor()
        self.video_analyzer = VideoRecipeAnalyzer()
        self.nutrition_analyzer = NutritionAnalyzer()
        self.recipe_generator = RecipeGenerator(db)

    async def process_transcription(self, log_ref, video_url: str, request_id: str) -> dict:
        """Process video transcription using Whisper"""
        now = datetime.datetime.utcnow().isoformat()
        try:
            # Extract transcript
            logger.info(f"[{request_id}] Extracting transcript from video")
            transcript_result = self.whisper_extractor.extract_transcript(video_url)
            
            # Prepare transcription data
            transcription = {
                "text": transcript_result.text if transcript_result else "",
                "timestamp": now,
                "success": bool(transcript_result)
            }
            
            # Update the recipe log with transcription data
            log_ref.update({
                "transcription": transcription,
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "transcription",
                    "status": "completed",
                    "timestamp": now,
                    "success": bool(transcript_result)
                }])
            })
            
            return transcription
            
        except Exception as e:
            logger.error(f"[{request_id}] Error processing transcription: {str(e)}")
            # Update log with error status but don't fail the process
            error_transcription = {
                "text": "",
                "timestamp": now,
                "success": False,
                "error": str(e)
            }
            
            log_ref.update({
                "transcription": error_transcription,
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "transcription",
                    "status": "failed",
                    "timestamp": now,
                    "error": str(e)
                }])
            })
            
            return error_transcription

    async def process_video_analysis(self, log_ref, video_url: str, request_id: str) -> dict:
        """Process video analysis to extract recipe information"""
        now = datetime.datetime.utcnow().isoformat()
        try:
            # Analyze video
            logger.info(f"[{request_id}] Analyzing video for recipe information")
            analysis_result = await self.video_analyzer.analyze_video(video_url)
            
            # Prepare analysis data
            analysis = {
                "scenes": analysis_result.get('scene_analyses', []),
                "recipe": analysis_result.get('final_recipe', ''),
                "timestamp": now,
                "success": analysis_result.get('success', False)
            }
            
            # Update the recipe log with analysis data
            log_ref.update({
                "analysis": analysis,
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "video_analysis",
                    "status": "completed",
                    "timestamp": now,
                    "success": analysis_result.get('success', False)
                }])
            })
            
            # If analysis was successful, generate structured recipe data
            if analysis['success'] and analysis['recipe']:
                logger.info(f"[{request_id}] Generating structured recipe data")
                
                # Get video ID from the video URL
                video_ref = self.db.collection('videos').where('videoUrl', '==', video_url).limit(1).get()
                video_id = video_ref[0].id if video_ref else None
                
                recipe_result = await self.recipe_generator.generate_recipe_data(
                    recipe_text=analysis['recipe'],
                    video_id=video_id
                )
                
                if recipe_result['success']:
                    # Add recipe data to the analysis
                    analysis['structured_recipe'] = recipe_result
                    
                    # Update log with structured recipe data
                    log_ref.update({
                        "analysis": analysis,
                        "updatedAt": now,
                        "processingSteps": firestore.ArrayUnion([{
                            "step": "recipe_generation",
                            "status": "completed",
                            "timestamp": now,
                            "success": True
                        }])
                    })
                else:
                    logger.error(f"[{request_id}] Failed to generate structured recipe: {recipe_result.get('error')}")
                    log_ref.update({
                        "processingSteps": firestore.ArrayUnion([{
                            "step": "recipe_generation",
                            "status": "failed",
                            "timestamp": now,
                            "error": recipe_result.get('error')
                        }])
                    })
            
            return analysis
            
        except Exception as e:
            logger.error(f"[{request_id}] Error processing video analysis: {str(e)}")
            # Update log with error status but don't fail the process
            error_analysis = {
                "scenes": [],
                "recipe": "",
                "timestamp": now,
                "success": False,
                "error": str(e)
            }
            
            log_ref.update({
                "analysis": error_analysis,
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "video_analysis",
                    "status": "failed",
                    "timestamp": now,
                    "error": str(e)
                }])
            })
            
            return error_analysis

    async def process_nutrition(self, log_ref, recipe_text: str, request_id: str) -> dict:
        """Process nutrition analysis for the recipe"""
        now = datetime.datetime.utcnow().isoformat()
        try:
            # Analyze nutrition
            logger.info(f"[{request_id}] Analyzing recipe nutrition")
            nutrition_result = await self.nutrition_analyzer.analyze_recipe_nutrition(recipe_text)
            
            if nutrition_result.get('success'):
                # Get video ID from the recipe log
                log_data = log_ref.get().to_dict()
                video_ref = self.db.collection('videos').where('videoUrl', '==', log_data.get('videoUrl')).limit(1).get()
                video_id = video_ref[0].id if video_ref else None
                
                # Extract total nutrition values and ingredients
                nutrition_info = nutrition_result.get('nutrition_info', {})
                
                # Create nutrition document with total values and ingredients
                nutrition_data = {
                    "videoId": video_id,
                    "calories": nutrition_info.get('calories', 0),
                    "fat": nutrition_info.get('fat', 0),
                    "carbs": nutrition_info.get('carbs', 0),
                    "protein": nutrition_info.get('protein', 0),
                    "fiber": nutrition_info.get('fiber', 0),
                    "ingredients": nutrition_info.get('ingredients', []),
                    "serving_sizes": nutrition_result.get('serving_sizes', ''),
                    "createdAt": now,
                    "updatedAt": now
                }
                
                # Store in Firestore
                nutrition_ref = self.db.collection('nutrition').document()
                nutrition_ref.set(nutrition_data)
                nutrition_id = nutrition_ref.id
                
                # Prepare nutrition data for log
                nutrition = {
                    **nutrition_data,
                    "nutritionId": nutrition_id,
                    "timestamp": now,
                    "success": True
                }
            else:
                nutrition = {
                    "serving_sizes": "",
                    "timestamp": now,
                    "success": False,
                    "error": nutrition_result.get('error', 'Unknown error')
                }
            
            # Update the recipe log with nutrition data
            log_ref.update({
                "nutrition": nutrition,
                "status": "completed",
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "nutrition_analysis",
                    "status": "completed" if nutrition_result.get('success') else "failed",
                    "timestamp": now,
                    "success": nutrition_result.get('success', False),
                    "error": nutrition_result.get('error') if not nutrition_result.get('success') else None
                }])
            })
            
            return nutrition
            
        except Exception as e:
            logger.error(f"[{request_id}] Error processing nutrition analysis: {str(e)}")
            # Update log with error status but don't fail the process
            error_nutrition = {
                "serving_sizes": "",
                "timestamp": now,
                "success": False,
                "error": str(e)
            }
            
            log_ref.update({
                "nutrition": error_nutrition,
                "updatedAt": now,
                "processingSteps": firestore.ArrayUnion([{
                    "step": "nutrition_analysis",
                    "status": "failed",
                    "timestamp": now,
                    "error": str(e)
                }])
            })
            
            return error_nutrition

    async def save_video(self, user_id: str, metadata: dict, request_id: str) -> str:
        """Save video data to the videos collection"""
        logger.info(f"[{request_id}] Saving video data to videos collection")
        
        try:
            # Create video document data
            video_data = {
                "userId": user_id,
                "videoTitle": metadata.get('title', ''),
                "videoDescription": metadata.get('description', ''),
                "mealName": metadata.get('title', ''),  # Using title as meal name initially
                "mealDescription": "Restaurant quality meal made right at home.",  # Default description
                "videoUrl": metadata.get('video_url', ''),  # Use the Supabase storage URL
                "thumbnailUrl": metadata.get('thumbnail', ''),
                "duration": metadata.get('duration', 0),
                "uploadedAt": datetime.datetime.utcnow().isoformat(),
                "source": metadata.get('platform', 'unknown'),
                "createdAt": datetime.datetime.utcnow().isoformat(),
                "updatedAt": datetime.datetime.utcnow().isoformat()
            }
            
            # Add to Firestore
            video_ref = self.db.collection('videos').document()
            video_ref.set(video_data)
            video_id = video_ref.id
            
            logger.info(f"[{request_id}] Successfully saved video with ID: {video_id}")
            return video_id
            
        except Exception as e:
            logger.error(f"[{request_id}] Error saving video data: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save video data: {str(e)}"
            )

    async def create_recipe_log(self, user_id: str, video_url: str, request_id: str) -> dict:
        """Create a new recipe log entry and process video data"""
        logger.info(f"[{request_id}] Creating recipe log for video URL: {video_url}")
        
        try:
            now = datetime.datetime.utcnow().isoformat()
            
            # Extract metadata first
            logger.info(f"[{request_id}] Extracting metadata from video URL")
            metadata = await self.metadata_extractor.extract_metadata(video_url)
            platform = metadata.get('platform', 'unknown')
            
            # Download and upload the video to Supabase storage
            logger.info(f"[{request_id}] Uploading video to Supabase storage")
            success, storage_url = await self.metadata_extractor.download_video(video_url)
            if success:
                metadata['video_url'] = storage_url
            else:
                logger.warning(f"[{request_id}] Failed to upload video to storage, using original URL")
                metadata['video_url'] = video_url

            # Save video data first
            video_id = await self.save_video(user_id, metadata, request_id)
            
            # Create recipe log document with metadata
            log_data = {
                "userId": user_id,
                "videoId": video_id,  # Add the video ID reference
                "videoUrl": video_url,
                "platform": platform,
                "status": "processing",
                "createdAt": now,
                "updatedAt": now,
                "metadata": {
                    "title": metadata.get('title', ''),
                    "description": metadata.get('description', ''),
                    "duration": metadata.get('duration', 0),
                    "uploader": metadata.get('uploader', ''),
                    "view_count": metadata.get('view_count', 0),
                    "like_count": metadata.get('like_count', 0),
                    "comment_count": metadata.get('comment_count', 0),
                    "subtitle_text": metadata.get('subtitle_text', ''),
                    "thumbnail": metadata.get('thumbnail', ''),
                    "platform": platform,
                    "storage_url": metadata.get('video_url', '')
                },
                "processingSteps": [
                    {
                        "step": "metadata_extraction",
                        "status": "completed",
                        "timestamp": now,
                        "success": bool(metadata)
                    }
                ]
            }
            
            # Add to Firestore
            log_ref = self.db.collection('recipe_logs').document()
            log_ref.set(log_data)
            log_id = log_ref.id
            
            # Process transcription - errors won't stop the process
            transcription = await self.process_transcription(log_ref, video_url, request_id)
            log_data["transcription"] = transcription
            
            # Process video analysis
            analysis = await self.process_video_analysis(log_ref, video_url, request_id)
            log_data["analysis"] = analysis
            
            # Process nutrition analysis if we have a recipe from video analysis
            if analysis.get('success') and analysis.get('recipe'):
                nutrition = await self.process_nutrition(log_ref, analysis['recipe'], request_id)
                log_data["nutrition"] = nutrition
                log_data["status"] = "completed"
            else:
                log_data["status"] = "analyzed"  # Stop at analysis if we couldn't get a recipe
            
            response_data = {
                "logId": log_id,
                "userId": user_id,
                "videoId": video_id,  # Include video ID in response
                "videoUrl": video_url,
                "platform": platform,
                "status": log_data["status"],
                "metadata": log_data["metadata"],
                "transcription": log_data["transcription"],
                "analysis": log_data["analysis"],
                "nutrition": log_data.get("nutrition", {}),
                "processingSteps": log_data["processingSteps"],
                "createdAt": now,
                "updatedAt": now
            }
            
            logger.info(f"[{request_id}] Created recipe log {log_id} with metadata for {platform} video")
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
                "platform": log_data.get('platform', 'unknown'),
                "status": log_data['status'],
                "metadata": log_data.get('metadata', {}),
                "transcription": log_data.get('transcription', {}),
                "analysis": log_data.get('analysis', {}),
                "nutrition": log_data.get('nutrition', {}),
                "processingSteps": log_data.get('processingSteps', []),
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
