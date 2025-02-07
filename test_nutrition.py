import asyncio
import logging
import json
import os
from nutrition import NutritionAnalyzer

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test recipe data
TEST_RECIPE = """**Ingredients:**

- Potatoes, diced
- Zucchini, diced
- Red bell peppers, diced
- Cherry tomatoes
- Eggplant
- Chickpeas (canned)
- Whole garlic bulb
- Garlic cloves
- Onion
- Roasted or cooked onions
- Fresh parsley or cilantro (for garnish)
- Fresh cilantro
- Red chili peppers
- Lemon juice
- Yogurt
- Feta cheese
- Cream cheese
- Milk
- Paprika
- Salt
- Black pepper
- Orange-colored sauce or puree (possibly containing roasted red peppers, spices, or a creamy base such as yogurt or mayonnaise)
- Hummus (as a base)

---

**Directions:**

1. **Preparation:**
   - Preheat your oven to 400°F (200°C).
   - Line a baking tray with parchment paper.

2. **Chop and Arrange Vegetables:**
   - Dice the potatoes, zucchini, red bell peppers, and eggplant into cubes.
   - Arrange the diced vegetables, cherry tomatoes, and canned chickpeas on the prepared baking tray.
   - Add a whole garlic bulb to the tray.

3. **Season:**
   - Season the vegetables and chickpeas with salt and black pepper.
   - Optionally, add paprika for extra flavor.

4. **Roast:**
   - Roast the vegetables and chickpeas in the preheated oven for about 25-30 minutes, or until the vegetables are tender and slightly caramelized.

5. **Prepare the Sauce:**
   - In a blender or food processor, combine yogurt, feta cheese, cream cheese, milk, paprika, roasted garlic cloves (squeezed out of their skins), parsley, and lemon juice.
   - Blend until smooth to create a creamy sauce.

6. **Assemble the Dish:**
   - Spread a layer of hummus or the prepared orange-colored sauce on a serving plate or bowl.
   - Spoon the roasted vegetables and chickpeas over the sauce.
   - Garnish with fresh parsley or cilantro.

7. **Serve:**
   - Serve the dish warm as a main course or a hearty side dish."""

async def main():
    # Initialize the nutrition analyzer
    nutrition_analyzer = NutritionAnalyzer()
    
    try:
        logger.info("Starting nutrition analysis...")
        
        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)
        
        # Analyze the recipe
        logger.info("Calling analyze_recipe_nutrition...")
        nutrition_result = await nutrition_analyzer.analyze_recipe_nutrition(TEST_RECIPE)
        logger.info(f"Got result with success={nutrition_result.get('success', False)}")
        
        if nutrition_result['success']:
            logger.info("\nServing Sizes (for 4 people):")
            print(nutrition_result['serving_sizes'])
            logger.info("\nNutritional Information:")
            
            # Log the type and content of nutrition_info
            logger.info(f"nutrition_info type: {type(nutrition_result['nutrition_info'])}")
            logger.info(f"nutrition_info content: {nutrition_result['nutrition_info']}")
            
            print(json.dumps(nutrition_result['nutrition_info'], indent=2))
            
            # Write results to a file
            logger.info("Writing results to file...")
            with open('output/nutrition_analysis.txt', 'w') as f:
                f.write("Recipe Nutrition Analysis\n")
                f.write("=" * 50 + "\n\n")
                f.write("Serving Sizes (for 4 people):\n")
                f.write(nutrition_result['serving_sizes'])
                f.write("\n\nNutritional Information:\n")
                if isinstance(nutrition_result['nutrition_info'], dict):
                    f.write(json.dumps(nutrition_result['nutrition_info'], indent=2))
                else:
                    f.write(str(nutrition_result['nutrition_info']))
            logger.info("Results written to output/nutrition_analysis.txt")
        else:
            logger.error(f"Nutrition analysis failed: {nutrition_result.get('error', 'Unknown error')}")
            if 'error' in nutrition_result:
                logger.error(f"Full error details: {nutrition_result['error']}")
            
    except Exception as e:
        logger.error(f"Error running nutrition test: {str(e)}", exc_info=True)

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main()) 