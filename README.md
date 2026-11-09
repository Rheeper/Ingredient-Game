# Ingredientdle

A daily guessing game: see a dish, guess its ingredients before you run out of hearts.

- One heart per 3 ingredients (rounded down)
- The grid shows 2.5x as many options as there are real ingredients
- A new dish every day

## Run it
Open `index.html` in a browser. No build step.

## Add more dishes
```
pip3 install pillow
python3 scrape.py --mealdb-random 20
```
This updates `dishes.json`, saves small photos into `images/` and rebuilds `index.html`.

## Credits
Recipe data and photos via [TheMealDB](https://www.themealdb.com) and linked recipe sources.
