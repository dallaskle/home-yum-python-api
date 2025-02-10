import datetime
import logging
from firebase_admin import firestore, auth
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: firestore.Client):
        self.db = db

    async def get_user_profile(self, user_id: str) -> dict:
        """Get user profile data from Firestore"""
        try:
            doc_ref = self.db.collection('users').document(user_id)
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

    async def create_user_profile(self, user_id: str) -> dict:
        """Create a new user profile in Firestore after signup"""
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
            
            doc_ref = self.db.collection('users').document(user_id)
            doc_ref.set(user_data)
            return user_data
        except Exception as e:
            logger.error(f"Error creating user profile: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_user_profile(self, user_id: str, profile: dict) -> dict:
        """Update user profile in Firestore"""
        if user_id != profile.get('userId'):
            raise HTTPException(status_code=403, detail="Cannot update other user's profile")
            
        try:
            # Never update password hash
            if 'passwordHash' in profile:
                del profile['passwordHash']
            
            profile["updatedAt"] = datetime.datetime.utcnow().isoformat()
            
            doc_ref = self.db.collection('users').document(user_id)
            doc_ref.update(profile)
            return {"message": "Profile updated successfully"}
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
