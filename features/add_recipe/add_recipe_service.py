import datetime
import logging
from firebase_admin import firestore
from fastapi import HTTPException
from video_processing.extractor import VideoMetadataExtractor
from video_processing.whisper_extractor import WhisperExtractor

logger = logging.getLogger(__name__)

class AddRecipeService:
    def __init__(self, db: firestore.Client):
        self.db = db
        self.metadata_extractor = VideoMetadataExtractor()
        self.whisper_extractor = WhisperExtractor()

    async def process_transcription(self, log_ref, video_url: str, request_id: str) -> dict:
        """Process video transcription using Whisper"""
        try:
            now = datetime.datetime.utcnow().isoformat()
            
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
                "status": "transcribed",
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
            # Update log with error status
            log_ref.update({
                "status": "error",
                "logMessage": f"Transcription failed: {str(e)}",
                "updatedAt": datetime.datetime.utcnow().isoformat(),
                "processingSteps": firestore.ArrayUnion([{
                    "step": "transcription",
                    "status": "failed",
                    "timestamp": now,
                    "error": str(e)
                }])
            })
            raise

    async def create_recipe_log(self, user_id: str, video_url: str, request_id: str) -> dict:
        """Create a new recipe log entry and extract metadata"""
        logger.info(f"[{request_id}] Creating recipe log for video URL: {video_url}")
        
        try:
            now = datetime.datetime.utcnow().isoformat()
            
            # Extract metadata first
            logger.info(f"[{request_id}] Extracting metadata from video URL")
            metadata = self.metadata_extractor.extract_metadata(video_url)
            platform = metadata.get('platform', 'unknown')
            
            # Create recipe log document with metadata
            log_data = {
                "userId": user_id,
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
                    "platform": platform
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
            
            # Process transcription
            try:
                transcription = await self.process_transcription(log_ref, video_url, request_id)
                log_data["transcription"] = transcription
                log_data["status"] = "transcribed"
            except Exception as e:
                logger.error(f"[{request_id}] Transcription processing failed: {str(e)}")
                log_data["status"] = "error"
                log_data["logMessage"] = f"Transcription failed: {str(e)}"
            
            response_data = {
                "logId": log_id,
                "userId": user_id,
                "videoUrl": video_url,
                "platform": platform,
                "status": log_data["status"],
                "metadata": log_data["metadata"],
                "transcription": log_data.get("transcription", {}),
                "processingSteps": log_data["processingSteps"],
                "logMessage": log_data.get("logMessage"),
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
                "processingSteps": log_data.get('processingSteps', []),
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
