import logging
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import json

logger = logging.getLogger(__name__)

class ManualNutritionAnalyzer:
    # Class constant for serving size
    DEFAULT_SERVING_SIZE = 4

    def __init__(self):
        """Initialize the ManualNutritionAnalyzer with LangChain configuration."""
        self.chat_model = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        )
        
        # Define prompts
        self.nutrition_prompt = """Analyze the nutritional content of this recipe and return a JSON object with the following structure:

{{
    "calories": number,
    "fat": number (in grams),
    "carbs": number (in grams),
    "protein": number (in grams),
    "fiber": number (in grams),
    "ingredients": [
        {{
            "name": "Ingredient name",
            "amount": number,
            "amountDescription": "unit of measurement",
            "calories": number,
            "fat": number,
            "carbs": number,
            "protein": number,
            "fiber": number
        }}
    ],
    "serving_sizes": number
}}

Recipe to analyze:
{recipe}

Notes:
1. All nutritional values should be realistic and based on standard USDA guidelines
2. Calculate values for {servings} servings
3. Include all ingredients from the recipe
4. Round numbers to one decimal place
5. serving_sizes should be set to {servings}
6. Return ONLY the JSON object, no additional text"""

    async def analyze_recipe(self, recipe_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze the nutritional content of a recipe."""
        try:
            logger.info("Starting nutrition analysis for recipe")
            
            # Format recipe data for the prompt
            recipe_text = json.dumps(recipe_data, indent=2)
            
            # Create message for nutrition analysis
            message = HumanMessage(
                content=self.nutrition_prompt.format(
                    recipe=recipe_text,
                    servings=self.DEFAULT_SERVING_SIZE
                )
            )
            
            # Get nutrition analysis
            response = self.chat_model.invoke([message])
            
            # Parse the response as JSON
            try:
                # Clean up the response
                cleaned_content = response.content.strip()
                if cleaned_content.startswith('```'):
                    cleaned_content = cleaned_content.split('```')[1]
                    if cleaned_content.startswith('json'):
                        cleaned_content = cleaned_content[4:]
                    cleaned_content = cleaned_content.strip()
                
                nutrition_data = json.loads(cleaned_content)
                
                # Validate the structure
                required_fields = ['calories', 'fat', 'carbs', 'protein', 'fiber', 'ingredients']
                for field in required_fields:
                    if field not in nutrition_data:
                        raise ValueError(f"Missing required field: {field}")
                
                # Validate ingredients
                if not isinstance(nutrition_data['ingredients'], list):
                    raise ValueError("Ingredients must be an array")
                
                for ingredient in nutrition_data['ingredients']:
                    ingredient_fields = ['name', 'amount', 'amountDescription', 'calories', 'fat', 'carbs', 'protein', 'fiber']
                    for field in ingredient_fields:
                        if field not in ingredient:
                            raise ValueError(f"Ingredient missing required field: {field}")
                
                return {
                    "success": True,
                    **nutrition_data
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing nutrition JSON: {str(e)}")
                return {
                    "success": False,
                    "error": f"Invalid nutrition data format: {str(e)}"
                }
            except ValueError as e:
                logger.error(f"Validation error: {str(e)}")
                return {
                    "success": False,
                    "error": str(e)
                }
            
        except Exception as e:
            logger.error(f"Error analyzing recipe nutrition: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 