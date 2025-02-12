import logging
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import json

logger = logging.getLogger(__name__)

class RecipeGenerator:
    def __init__(self):
        """Initialize the RecipeGenerator with LangChain configuration."""
        self.chat_model = ChatOpenAI(
            model="gpt-4",
            temperature=0.7
        )
        
        # Define prompts
        self.recipe_prompt = """Generate a detailed recipe for {prompt}. Return the response as a JSON object with the following structure:

{
    "title": "Recipe title",
    "description": "Brief description of the dish",
    "servings": "Number of servings",
    "prepTime": "Preparation time in minutes",
    "cookTime": "Cooking time in minutes",
    "ingredients": [
        {
            "name": "Ingredient name",
            "amount": number,
            "amountDescription": "unit of measurement"
        }
    ],
    "instructions": [
        {
            "step": number,
            "text": "Step instruction"
        }
    ],
    "tips": ["Cooking tips and suggestions"]
}

Make sure the recipe is practical, delicious, and includes all necessary ingredients and clear instructions."""

        self.update_prompt = """Update the following recipe based on these changes: {updates}

Current Recipe:
{current_recipe}

Return the updated recipe in the same JSON format as the original."""

    async def generate_recipe(self, prompt: str) -> Dict[str, Any]:
        """Generate a complete recipe from a simple prompt."""
        try:
            logger.info(f"Generating recipe for prompt: {prompt}")
            
            # Create message for recipe generation
            message = HumanMessage(
                content=self.recipe_prompt.format(prompt=prompt)
            )
            
            # Get recipe generation
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
                
                recipe_data = json.loads(cleaned_content)
                
                return {
                    "success": True,
                    **recipe_data
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing recipe JSON: {str(e)}")
                return {
                    "success": False,
                    "error": f"Invalid recipe format: {str(e)}"
                }
            
        except Exception as e:
            logger.error(f"Error generating recipe: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def update_recipe(self, current_recipe: Dict[str, Any], updates: str) -> Dict[str, Any]:
        """Update an existing recipe based on user feedback."""
        try:
            logger.info(f"Updating recipe with changes: {updates}")
            
            # Create message for recipe update
            message = HumanMessage(
                content=self.update_prompt.format(
                    updates=updates,
                    current_recipe=json.dumps(current_recipe, indent=2)
                )
            )
            
            # Get recipe update
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
                
                updated_recipe = json.loads(cleaned_content)
                
                return {
                    "success": True,
                    **updated_recipe
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing updated recipe JSON: {str(e)}")
                return {
                    "success": False,
                    "error": f"Invalid recipe format: {str(e)}"
                }
            
        except Exception as e:
            logger.error(f"Error updating recipe: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 