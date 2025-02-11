import logging
import json
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from langsmith import traceable
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class NutritionAnalyzer:
    # Class constant for serving size
    DEFAULT_SERVING_SIZE = 4

    def __init__(self):
        """Initialize the NutritionAnalyzer with LangChain configuration."""
        self.chat_model = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        )
        
        # Define prompts
        self.serving_size_prompt = """Would you please specify how much of each item should be in a serving size for {} people for this recipe?

Recipe Information:
{recipe_info}""".format(self.DEFAULT_SERVING_SIZE, recipe_info="{recipe_info}")

        self.nutrition_info_prompt = """You are a JSON generator. Your task is to create a valid JSON object containing nutritional information based on the serving sizes provided.

Rules:
1. Return ONLY the JSON object, no other text
2. The JSON must start with '{{' and end with '}}'
3. Include ALL ingredients from the recipe
4. Use realistic nutritional values
5. Include all required fields for each ingredient
6. No comments, no explanations, just the JSON

Required JSON structure:
{{
  "ingredients": [
    {{
      "name": "Ingredient Name",
      "amount": number,
      "amountDescription": "description",
      "calories": number,
      "fat": number,
      "carbs": number,
      "protein": number,
      "fiber": number
    }}
  ]
}}

Serving Sizes:
{serving_sizes}"""

    @traceable
    async def get_serving_sizes(self, recipe_info: str) -> Dict[str, Any]:
        """
        Determine serving sizes for 4 people based on recipe information.
        
        Args:
            recipe_info (str): Complete recipe information including ingredients and directions
            
        Returns:
            Dict[str, Any]: Serving size analysis results
        """
        try:
            # Create message for serving size analysis
            message = HumanMessage(
                content=self.serving_size_prompt.format(recipe_info=recipe_info)
            )
            
            # Get serving size analysis
            logger.info("Analyzing serving sizes...")
            response = self.chat_model.invoke([message])
            logger.info(f"Serving sizes response received: {response.content[:200]}...")
            
            return {
                "success": True,
                "serving_sizes": response.content
            }
            
        except Exception as e:
            logger.error(f"Error analyzing serving sizes: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    @traceable
    async def get_nutrition_info(self, serving_sizes: str) -> Dict[str, Any]:
        """
        Get nutritional information based on serving sizes.
        
        Args:
            serving_sizes (str): Serving size information for the recipe
            
        Returns:
            Dict[str, Any]: Nutritional information analysis results
        """
        try:
            # Create message for nutrition analysis
            message = HumanMessage(
                content=self.nutrition_info_prompt.format(serving_sizes=serving_sizes)
            )
            
            # Get nutrition analysis
            logger.info("Analyzing nutritional information...")
            response = self.chat_model.invoke([message])
            
            # Log the raw response for debugging
            logger.info("Raw response received:")
            logger.info("-" * 80)
            logger.info(response.content)
            logger.info("-" * 80)
            
            # Parse the response as JSON
            try:
                # Clean up the response
                cleaned_content = response.content.strip()
                
                # Remove any markdown formatting
                if cleaned_content.startswith('```'):
                    cleaned_content = cleaned_content.split('```')[1]
                    if cleaned_content.startswith('json'):
                        cleaned_content = cleaned_content[4:]
                    cleaned_content = cleaned_content.strip()
                
                # Remove any quotes around the entire JSON
                cleaned_content = cleaned_content.strip('"')
                
                # Remove any leading/trailing whitespace or newlines
                cleaned_content = cleaned_content.strip()
                
                logger.info("Cleaned content for JSON parsing:")
                logger.info("-" * 80)
                logger.info(cleaned_content)
                logger.info("-" * 80)
                
                nutrition_data = json.loads(cleaned_content)
                logger.info("Successfully parsed JSON")
                
                # Validate the structure
                if not isinstance(nutrition_data, dict):
                    raise ValueError("Response is not a JSON object")
                if 'ingredients' not in nutrition_data:
                    raise ValueError("Response is missing required 'ingredients' array")
                if not isinstance(nutrition_data['ingredients'], list):
                    raise ValueError("'ingredients' must be an array")
                
                return {
                    "success": True,
                    "nutrition_info": nutrition_data
                }
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error at position {e.pos}: {e.msg}")
                logger.error(f"Error context: {cleaned_content[max(0, e.pos-50):min(len(cleaned_content), e.pos+50)]}")
                return {
                    "success": False,
                    "error": f"Invalid JSON response: {str(e)}"
                }
            except Exception as e:
                logger.error(f"Error processing nutrition data: {str(e)}")
                return {
                    "success": False,
                    "error": str(e)
                }
            
        except Exception as e:
            logger.error(f"Error analyzing nutritional information: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    @traceable
    async def analyze_recipe_nutrition(self, recipe_info: str) -> Dict[str, Any]:
        """
        Complete nutrition analysis workflow - get serving sizes and nutritional information.
        
        Args:
            recipe_info (str): Complete recipe information including ingredients and directions
            
        Returns:
            Dict[str, Any]: Complete nutrition analysis results with total nutrition values
        """
        try:
            # Step 1: Get serving sizes
            serving_sizes_result = await self.get_serving_sizes(recipe_info)
            if not serving_sizes_result["success"]:
                return serving_sizes_result
                
            # Step 2: Get nutritional information based on serving sizes
            nutrition_info_result = await self.get_nutrition_info(serving_sizes_result["serving_sizes"])
            if not nutrition_info_result["success"]:
                return nutrition_info_result

            # Step 3: Calculate total nutrition values
            ingredients = nutrition_info_result["nutrition_info"]["ingredients"]
            total_nutrition = {
                "calories": sum(ing["calories"] for ing in ingredients),
                "fat": sum(ing["fat"] for ing in ingredients),
                "carbs": sum(ing["carbs"] for ing in ingredients),
                "protein": sum(ing["protein"] for ing in ingredients),
                "fiber": sum(ing["fiber"] for ing in ingredients)
            }
                
            return {
                "success": True,
                "serving_sizes": self.DEFAULT_SERVING_SIZE,
                # Include both total nutrition and ingredient details
                "nutrition_info": {
                    **total_nutrition,  # Total nutrition values at the top level
                    "ingredients": ingredients  # Individual ingredient details
                }
            }
            
        except Exception as e:
            logger.error(f"Error in nutrition analysis workflow: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 