#!/usr/bin/env python3
"""
Build the Ingredientdle answer key and embed it into index.html.

Sources (open / permissive only):
  1. TheMealDB (free API)            --mealdb "Pad Thai" --mealdb "Shakshuka"
  2. Any recipe page with schema.org Recipe JSON-LD (most food blogs)  --url https://...
     Pages are only fetched if the site's robots.txt allows it.

Examples:
  python3 scrape.py --mealdb "Pad Thai" --mealdb "Beef Wellington"
  python3 scrape.py --url https://minimalistbaker.com/some-recipe/ --urls-file urls.txt
  python3 scrape.py --mealdb-random 20

Existing dishes in dishes.json are kept (deduped by name). Photos are saved into images/ (small JPEGs).
Output: dishes.json + images/ + index.html updated. For smaller photos run once: pip3 install pillow
Stdlib only. NOTE: please respect each site's terms; this deliberately skips NYT Cooking (paywalled, copyrighted).
"""
import argparse, html, json, re, sys, urllib.parse, urllib.request, urllib.robotparser
from pathlib import Path

HERE = Path(__file__).parent
UA = "Mozilla/5.0 (compatible; IngredientdleBot/1.0)"
MIN_ING, MAX_ING = 4, 16

# Pantry basics that make the game trivial / unfair: stripped from answer keys.
SKIP = {"salt", "pepper", "black pepper", "water", "ice", "kosher salt", "sea salt", "cooking spray"}

# Canonical names so the same ingredient is always spelled one way.
ALIASES = {
    "coriander": "cilantro", "fresh coriander": "cilantro", "coriander leaves": "cilantro",
    "scallions": "spring onions", "scallion": "spring onions", "green onions": "spring onions", "green onion": "spring onions",
    "corn flour": "cornstarch", "cornflour": "cornstarch", "corn starch": "cornstarch",
    "chilli": "chili", "chilli powder": "chili powder", "chilli flakes": "chili flakes", "red pepper flakes": "chili flakes",
    "red chilli": "red chili", "green chilli": "green chili", "chile": "chili",
    "tomato": "tomatoes", "chopped tomatoes": "tomatoes", "cherry tomatoes": "tomatoes", "plum tomatoes": "tomatoes",
    "egg": "eggs", "large eggs": "eggs", "egg yolk": "egg yolks",
    "parmesan cheese": "parmesan", "parmigiano-reggiano": "parmesan", "parmigiano reggiano": "parmesan",
    "parma ham": "prosciutto", "caster sugar": "sugar", "granulated sugar": "sugar", "muscovado sugar": "sugar", "white sugar": "sugar",
    "prawns": "prawns", "tiger prawns": "prawns", "shrimp": "prawns",
    "double cream": "heavy cream", "whipping cream": "heavy cream", "heavy whipping cream": "heavy cream",
    "garlic clove": "garlic", "garlic cloves": "garlic", "cloves garlic": "garlic",
    "sesame seed oil": "sesame oil", "extra virgin olive oil": "olive oil", "extra-virgin olive oil": "olive oil",
    "red onions": "red onion", "onions": "onion", "yellow onion": "onion", "mushroom": "mushrooms",
    "yoghurt": "yogurt", "greek yogurt": "yogurt", "plain yogurt": "yogurt", "bowtie pasta": "pasta", "spaghetti": "spaghetti",
    "sweet chilli sauce": "sweet chili sauce", "fenugreek leaves": "fenugreek", "ground cumin": "cumin", "cumin seeds": "cumin",
    "ginger paste": "ginger", "fresh ginger": "ginger", "plain flour": "flour", "all-purpose flour": "flour", "all purpose flour": "flour",
    "unsalted butter": "butter", "bean sprouts": "bean sprouts", "beansprouts": "bean sprouts",
}

UNITS = r"(?:cups?|tablespoons?|tbsps?|tbs|teaspoons?|tsps?|pounds?|lbs?|ounces?|oz|grams?|g|kg|ml|l|liters?|litres?|pinch(?:es)?|dash(?:es)?|cloves?|cans?|tins?|packages?|bunch(?:es)?|handfuls?|slices?|sprigs?|stalks?|heads?|pieces?|large|medium|small|whole|fresh|freshly|dried|ground|chopped|minced|diced|sliced|grated|shredded|crushed|finely|roughly|thinly|boneless|skinless|cooked|uncooked|peeled|ripe|extra|good|quality|optional|plus|more|for|to|serve|garnish|taste|of|a|an|the|and|or)"


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def allowed(url):
    p = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt"); rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def clean(raw):
    s = html.unescape(str(raw)).lower().strip()
    s = re.sub(r"\(.*?\)", " ", s)          # drop parentheticals
    s = re.sub(r"extra[- ]virgin\s*", "", s)
    s = re.sub(r"\b(?:juice|zest)\s+of\b", " ", s)
    s = re.sub(r"\b(limes|lemons|oranges)\b", lambda m: m.group(1)[:-1], s)
    s = re.sub(r"\bchicken (?:breasts?|thighs?)\b", "chicken", s)
    s = s.split(",")[0]                     # drop prep notes after comma
    s = re.sub(r"[\d¼½¾⅓⅔⅛/.\-–]+", " ", s)  # quantities
    for _ in range(3):                      # peel off units / descriptors from the front
        s = re.sub(rf"^\s*{UNITS}\b\s*", "", s)
    s = re.sub(rf"\b(?:finely|roughly|freshly|chopped|minced|diced|sliced|grated|crushed|fresh|dried|to taste|for serving|for garnish)\b", " ", s)
    s = re.sub(r"[^a-z' ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def finalize(name, cuisine, image, source, raw_ings):
    seen, out = set(), []
    for r in raw_ings:
        c = clean(r)
        if not c or c in SKIP or len(c) < 3 or len(c) > 30 or c in seen:
            continue
        seen.add(c); out.append(c)
    if not image or not (MIN_ING <= len(out) <= MAX_ING):
        return None
    return {"name": name.strip(), "cuisine": cuisine or "", "image": image, "source": source, "ingredients": out}


# ---------- TheMealDB ----------
def from_mealdb_obj(m):
    raw = [m.get(f"strIngredient{i}") for i in range(1, 21)]
    raw = [x for x in raw if x and x.strip()]
    return finalize(m["strMeal"], m.get("strArea", ""), m["strMealThumb"],
                    m.get("strSource") or f"https://www.themealdb.com/meal/{m['idMeal']}", raw)


def mealdb_search(q):
    d = json.loads(fetch("https://www.themealdb.com/api/json/v1/1/search.php?s=" + urllib.parse.quote(q)))
    return [x for x in (from_mealdb_obj(m) for m in (d.get("meals") or [])) if x]


def mealdb_random(n):
    out, tries = [], 0
    while len(out) < n and tries < n * 4:
        tries += 1
        d = json.loads(fetch("https://www.themealdb.com/api/json/v1/1/random.php"))
        x = from_mealdb_obj(d["meals"][0])
        if x and x["name"] not in {o["name"] for o in out}:
            out.append(x)
    return out


# ---------- schema.org JSON-LD ----------
def iter_recipes(node):
    if isinstance(node, list):
        for n in node: yield from iter_recipes(n)
    elif isinstance(node, dict):
        t = node.get("@type")
        if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
            yield node
        for k in ("@graph", "mainEntity", "itemListElement"):
            if k in node: yield from iter_recipes(node[k])


def first_image(img):
    if isinstance(img, list): img = img[0] if img else None
    if isinstance(img, dict): img = img.get("url")
    return img if isinstance(img, str) else None


def from_url(url):
    if not allowed(url):
        print(f"  skipped (robots.txt): {url}", file=sys.stderr); return None
    page = fetch(url)
    for blob in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for r in iter_recipes(data):
            cuisine = r.get("recipeCuisine")
            if isinstance(cuisine, list): cuisine = cuisine[0] if cuisine else ""
            x = finalize(html.unescape(r.get("name", "")), cuisine or "", first_image(r.get("image")), url, r.get("recipeIngredient", []))
            if x: return x
    print(f"  no usable Recipe markup: {url}", file=sys.stderr)
    return None


def download_image(url, name):
    """Save a photo into images/ (resized to 960px wide JPEG if Pillow is installed) and return its relative path."""
    import io, unicodedata
    folder = HERE / "images"; folder.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-")[:48] or "dish"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB"); img.thumbnail((960, 960))
        img.save(folder / f"{slug}.jpg", "JPEG", quality=74, optimize=True, progressive=True)
    except ImportError:
        (folder / f"{slug}.jpg").write_bytes(raw)
    return f"images/{slug}.jpg"


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mealdb", action="append", default=[], help="TheMealDB search term (repeatable)")
    ap.add_argument("--mealdb-random", type=int, default=0, help="add N random TheMealDB dishes")
    ap.add_argument("--url", action="append", default=[], help="recipe page URL (repeatable)")
    ap.add_argument("--urls-file", help="text file with one recipe URL per line")
    ap.add_argument("--fresh", action="store_true", help="ignore existing dishes.json")
    a = ap.parse_args()

    jf = HERE / "dishes.json"
    dishes = [] if (a.fresh or not jf.exists()) else json.loads(jf.read_text())
    if not dishes:  # seed from the dishes already embedded in index.html
        m = re.search(r"/\*DISHES_START\*/\s*const DISHES = (.*?);\s*/\*DISHES_END\*/", (HERE / "index.html").read_text(), re.S)
        if m and not a.fresh: dishes = json.loads(m.group(1))
    have = {d["name"].lower() for d in dishes}

    new = []
    for q in a.mealdb: new += mealdb_search(q)
    if a.mealdb_random: new += mealdb_random(a.mealdb_random)
    urls = list(a.url)
    if a.urls_file: urls += [l.strip() for l in Path(a.urls_file).read_text().splitlines() if l.strip() and not l.startswith("#")]
    for u in urls:
        print("fetching", u)
        try:
            x = from_url(u)
            if x: new.append(x)
        except Exception as e:
            print("  failed:", e, file=sys.stderr)

    added = 0
    for d in new:
        if d["name"].lower() not in have:
            dishes.append(d); have.add(d["name"].lower()); added += 1

    for d in dishes:   # save any photo that is still a web link into images/ (no hotlinking)
        if d["image"].startswith("http"):
            try:
                d["image"] = download_image(d["image"], d["name"])
            except Exception as e:
                print(f"  image failed for {d['name']}: {e}", file=sys.stderr)

    jf.write_text(json.dumps(dishes, indent=1, ensure_ascii=False))
    idx = HERE / "index.html"
    src = idx.read_text()
    body = "/*DISHES_START*/\nconst DISHES = " + json.dumps(dishes, ensure_ascii=False) + ";\n/*DISHES_END*/"
    idx.write_text(re.sub(r"/\*DISHES_START\*/.*?/\*DISHES_END\*/", lambda _: body, src, flags=re.S))
    print(f"Added {added} dishes; {len(dishes)} total. index.html updated.")


if __name__ == "__main__":
    main()
