import base64
import requests
import logging
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VisionAnalyzer:
    @traceable(name="initialize_vision_analyzer")
    def __init__(self):
        """Initialize the VisionAnalyzer with LangChain configuration."""
        load_dotenv()
        
        # Initialize ChatOpenAI with GPT-4 Vision
        self.model = ChatOpenAI(
            model="gpt-4o",
            max_tokens=300,
            temperature=0
        )

    @traceable(name="encode_image")
    def encode_image(self, image_path: str) -> Optional[str]:
        """
        Read and encode an image file to base64.
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            Optional[str]: Base64 encoded image string or None if failed
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image: {str(e)}")
            return None

    @traceable(name="analyze_image")
    async def analyze_image(self, 
                     image_path: str, 
                     prompt: str = "What's in this image?", 
                     max_tokens: int = 300) -> Dict[str, Any]:
        """
        Analyze an image using GPT-4 Vision via LangChain.
        
        Args:
            image_path (str): Path to the image file
            prompt (str): Text prompt to accompany the image
            max_tokens (int): Maximum tokens in the response
            
        Returns:
            Dict[str, Any]: Analysis results or error message
        """
        try:
            # Encode the image
            base64_image = self.encode_image(image_path)
            if not base64_image:
                return {"error": "Failed to encode image"}

            # Create message content with text and image
            message = HumanMessage(
                content=[
                    {
                        "type": "text", 
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            )

            # Invoke the model
            logger.info(f"Sending request to analyze image: {image_path}")
            response = self.model.invoke([message])
            
            logger.info("Successfully analyzed image")
            return {
                "success": True,
                "analysis": response.content
            }

        except Exception as e:
            logger.error(f"Error analyzing image: {str(e)}")
            return {
                "success": False,
                "error": f"Error analyzing image: {str(e)}"
            }

    @traceable(name="analyze_image_from_url")
    async def analyze_image_from_url(self, 
                                   image_url: str, 
                                   prompt: str = "What's in this image?", 
                                   max_tokens: int = 300) -> Dict[str, Any]:
        """
        Analyze an image from a URL using GPT-4 Vision via LangChain.
        
        Args:
            image_url (str): URL of the image
            prompt (str): Text prompt to accompany the image
            max_tokens (int): Maximum tokens in the response
            
        Returns:
            Dict[str, Any]: Analysis results or error message
        """
        try:
            # Create message content with text and image
            message = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            )

            # Invoke the model
            logger.info(f"Sending request to analyze image from URL: {image_url}")
            response = self.model.invoke([message])
            
            logger.info("Successfully analyzed image from URL")
            return {
                "success": True,
                "analysis": response.content
            }

        except Exception as e:
            logger.error(f"Error analyzing image: {str(e)}")
            return {
                "success": False,
                "error": f"Error analyzing image: {str(e)}"
            } 