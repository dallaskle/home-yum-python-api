import logging
import datetime
import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from firebase_admin import firestore

logger = logging.getLogger(__name__)

class RecipeGenerator:
    def __init__(self, db: firestore.Client):
        self.db = db
        self.chat_model = ChatOpenAI(
            model="gpt-4o",
            max_tokens=1000,
            temperature=0
        )
        
        # Prompt template for converting recipe text to structured data
        self.structure_prompt = """You are a JSON converter. Your task is to convert recipe text into a specific JSON format.

Output a single, valid JSON object with this exact structure:

{{
    "recipe": {{
        "title": "string (name of the dish)",
        "summary": "string (1-2 sentence description)",
        "additionalNotes": "string (cooking tips or variations)"
    }},
    "recipeItems": [
        {{
            "stepOrder": number (starting from 1),
            "instruction": "string (main instruction)",
            "additionalDetails": "string (optional details)"
        }}
    ]
}}

Rules:
1. Output ONLY the JSON object, no other text or explanation
2. All string values MUST be in double quotes
3. stepOrder MUST be a plain number (no quotes)
4. The JSON must be properly formatted and valid
5. Do not include any markdown formatting

Recipe text to convert:
---
{}
---"""

    async def generate_recipe_data(self, recipe_text: str, video_id: str = None) -> Dict[str, Any]:
        """
        Generate structured recipe data from recipe text using OpenAI.
        
        Args:
            recipe_text (str): The recipe text to analyze
            video_id (str, optional): The associated video ID
            
        Returns:
            Dict containing the generated recipe and recipe items data
        """
        try:
            # Log the input recipe text
            logger.info("=== Input Recipe Text ===")
            logger.info(recipe_text)
            logger.info("========================")
            
            # Create the prompt with the recipe text
            prompt = self.structure_prompt.format(recipe_text)  # Changed to positional formatting
            message = HumanMessage(content=prompt)
            
            # Get structured data from OpenAI
            response = self.chat_model.invoke([message])
            
            # Log the raw response
            logger.info("=== Raw GPT Response ===")
            logger.info(response.content)
            logger.info("========================")
            
            # Clean the response content (remove any potential markdown or extra whitespace)
            cleaned_content = response.content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.startswith("```"):
                cleaned_content = cleaned_content[3:]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()
            
            logger.info("=== Cleaned Response ===")
            logger.info(cleaned_content)
            logger.info("========================")
            
            # Parse the response into a dictionary
            try:
                structured_data = json.loads(cleaned_content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {str(e)}")
                logger.error("Invalid JSON was:")
                logger.error(cleaned_content)
                return {
                    "success": False,
                    "error": f"Invalid JSON response: {str(e)}"
                }
            
            # Validate the structure
            required_recipe_keys = ["title", "summary", "additionalNotes"]
            required_item_keys = ["stepOrder", "instruction"]
            
            # Check recipe structure
            if "recipe" not in structured_data:
                logger.error("Missing 'recipe' key in response")
                return {"success": False, "error": "Missing 'recipe' key"}
                
            if not all(key in structured_data["recipe"] for key in required_recipe_keys):
                logger.error(f"Recipe missing required keys. Has: {structured_data['recipe'].keys()}")
                return {"success": False, "error": "Recipe missing required keys"}
                
            # Check recipeItems structure
            if "recipeItems" not in structured_data:
                logger.error("Missing 'recipeItems' key in response")
                return {"success": False, "error": "Missing 'recipeItems' key"}
                
            for idx, item in enumerate(structured_data["recipeItems"]):
                if not all(key in item for key in required_item_keys):
                    logger.error(f"Recipe item {idx} missing required keys. Has: {item.keys()}")
                    return {"success": False, "error": f"Recipe item {idx} missing required keys"}
                
                if not isinstance(item["stepOrder"], (int, float)):
                    logger.error(f"stepOrder must be a number, got: {type(item['stepOrder'])}")
                    return {"success": False, "error": "Invalid stepOrder type"}
            
            # Get current timestamp
            now = datetime.datetime.utcnow().isoformat()
            
            # Create recipe document
            recipe_data = {
                "videoId": video_id,
                "title": structured_data["recipe"]["title"],
                "summary": structured_data["recipe"]["summary"],
                "additionalNotes": structured_data["recipe"]["additionalNotes"],
                "createdAt": now,
                "updatedAt": now
            }
            
            # Add to Firestore
            recipe_ref = self.db.collection('recipes').document()
            recipe_ref.set(recipe_data)
            recipe_id = recipe_ref.id
            
            # Create recipe items
            recipe_items = []
            for item in structured_data["recipeItems"]:
                item_data = {
                    "recipeId": recipe_id,
                    "stepOrder": int(item["stepOrder"]),  # Ensure it's an integer
                    "instruction": item["instruction"],
                    "additionalDetails": item.get("additionalDetails", "")
                }
                
                # Add to Firestore
                item_ref = self.db.collection('recipe_items').document()
                item_ref.set(item_data)
                
                # Add to our return data with the generated ID
                recipe_items.append({
                    **item_data,
                    "recipeItemId": item_ref.id
                })
            
            logger.info("Successfully generated and stored recipe data")
            return {
                "success": True,
                "recipe": {
                    **recipe_data,
                    "recipeId": recipe_id
                },
                "recipeItems": recipe_items
            }
            
        except Exception as e:
            logger.error(f"Error generating recipe data: {str(e)}")
            logger.exception("Full traceback:")
            return {
                "success": False,
                "error": str(e)
            }
