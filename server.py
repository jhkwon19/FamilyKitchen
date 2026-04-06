import os
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import List, Optional, Tuple, Union
from urllib.parse import quote_plus, urljoin, urlparse, unquote
import re

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
import httpx
from fastapi.responses import FileResponse
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, LargeBinary, MetaData, String, Text, create_engine, func
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# Directories
BASE_DIR = Path(__file__).parent

# Database setup
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "Wnsgh1219@")
DB_HOST = os.environ.get("DB_HOST", "172.18.0.4")
DB_PORT = os.environ.get("DB_PORT", "3306")
DB_NAME = os.environ.get("DB_NAME", "FamilyKitchen")

# percent-encode password to safely handle special chars like @
DB_PASSWORD_ESC = quote_plus(DB_PASSWORD)

DB_URL = os.environ.get(
    "DATABASE_URL",
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD_ESC}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4",
)

engine = create_engine(DB_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
metadata = MetaData()
Base = declarative_base(metadata=metadata)


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)  # comma-separated
    source = Column(String(32), nullable=False, default="other")
    cuisine = Column(String(32), nullable=False, default="other")
    is_favorite = Column(Boolean, nullable=False, default=False)
    user_photo = Column(LargeBinary, nullable=True)
    user_photo_mime = Column(String(50), nullable=True)
    user_photo_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ingredients = relationship("Ingredient", cascade="all, delete-orphan", back_populates="recipe")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(String(36), primary_key=True, index=True)
    recipe_id = Column(String(36), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    amount = Column(String(255), nullable=True)
    recipe = relationship("Recipe", back_populates="ingredients")


class RecipeIn(BaseModel):
    title: str = Field(..., max_length=255)
    url: HttpUrl
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source: str = "other"
    cuisine: str = "auto"
    ingredients: List["IngredientIn"] = Field(default_factory=list)


class RecipeOut(RecipeIn):
    id: str
    cuisine: str = "other"
    is_favorite: bool = False
    has_user_photo: bool = False
    user_photo_url: Optional[str] = None
    created_at: datetime
    ingredients: List["IngredientOut"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class IngredientIn(BaseModel):
    name: str = Field(..., max_length=255)
    amount: Optional[str] = Field(default=None, max_length=255)


class IngredientOut(IngredientIn):
    id: str

    model_config = ConfigDict(from_attributes=True)


class RecipeFavoriteIn(BaseModel):
    is_favorite: bool


RecipeIn.update_forward_refs()
RecipeOut.update_forward_refs()

MAX_USER_PHOTO_BYTES = 8 * 1024 * 1024
COSTCO_SHOPPING_CACHE_TTL = timedelta(minutes=30)
COSTCO_SHOPPING_CACHE = {"items": [], "fetched_at": None}
COSTCO_SHOPPING_SITEMAP_CACHE = {"entries": [], "fetched_at": None}
COSTCO_SHOPPING_PRODUCT_CACHE_TTL = timedelta(hours=12)
COSTCO_SHOPPING_PRODUCT_CACHE = {}
KST = timezone(timedelta(hours=9))
COSTCO_SHOPPING_FALLBACK_URLS = [
    "https://www.costco.co.kr/p/692714",
    "https://www.costco.co.kr/Appliances/Seasonal-Appliances/FansAir-Circulator/Dyson-HotCool-Fan-Heater-AM09/p/672973",
    "https://www.costco.co.kr/ClothingBagsAccessories/Clothing-for-Men/Pants-for-Men/Guess-Mens-Jeans/p/677768",
    "https://www.costco.co.kr/Foods/SaucesCondiments/SaucesDressings/De-Nigris-Organic-Apple-Cider-Vinegar-15ml-x-50/p/690444",
]


VALID_CUISINES = {
    "korean",
    "chinese",
    "japanese",
    "western",
    "asian",
    "dessert",
    "snack",
    "fusion",
    "other",
}


CUISINE_KEYWORDS = {
    "korean": [
        "김치", "된장", "고추장", "비빔", "국밥", "찌개", "불고기", "갈비", "전", "볶음밥", "냉면", "잡채",
        "제육", "순두부", "떡국", "사골", "수육", "삼계탕", "비빔국수", "닭갈비", "감자탕", "부대찌개",
    ],
    "chinese": [
        "마라", "짜장", "짬뽕", "탕수육", "깐풍", "고추잡채", "유산슬", "볶음면", "딤섬", "양장피", "훠궈",
        "마파", "멘보샤", "굴소스", "춘장", "라조장", "지삼선",
    ],
    "japanese": [
        "초밥", "스시", "우동", "소바", "가츠", "돈카츠", "돈부리", "오니기리", "미소", "사케동", "오코노미야키",
        "타코야키", "규동", "라멘", "텐동", "가라아게", "일본식",
    ],
    "western": [
        "파스타", "리조또", "스테이크", "그라탕", "샐러드", "오믈렛", "스프", "토마토소스", "바질", "크림",
        "까르보나라", "라자냐", "피자", "감바스", "브런치", "샌드위치", "햄버거",
    ],
    "asian": [
        "쌀국수", "팟타이", "나시고렝", "분짜", "카오", "커리", "톰얌", "똠얌", "반미", "월남쌈", "동남아",
    ],
    "dessert": [
        "케이크", "쿠키", "브라우니", "타르트", "푸딩", "디저트", "아이스크림", "머핀", "스콘", "파르페",
        "와플", "팬케이크", "도넛", "크레이프",
    ],
    "snack": [
        "떡볶이", "토스트", "주먹밥", "간식", "핫도그", "호떡", "붕어빵", "샌드", "에그마요", "길거리",
    ],
}


def tags_to_string(tags: List[str]) -> str:
    return ",".join([t.strip() for t in tags if t.strip()])


def tags_to_list(tag_string: Optional[str]) -> List[str]:
    if not tag_string:
        return []
    return [t for t in (tag_string or "").split(",") if t]


def normalize_cuisine(value: Optional[str]) -> str:
    if not value:
        return "auto"
    lowered = value.strip().lower()
    return lowered if lowered in VALID_CUISINES else "auto"


def infer_cuisine(title: str, notes: Optional[str], tags: List[str], ingredients: List[str]) -> str:
    corpus = " ".join(
        [
            title or "",
            notes or "",
            " ".join(tags or []),
            " ".join(ingredients or []),
        ]
    ).lower()

    if not corpus.strip():
        return "other"

    scores = {name: 0 for name in CUISINE_KEYWORDS}
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in corpus:
                scores[cuisine] += 1

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "other"

    if scores[best] > 0 and any(score == scores[best] for name, score in scores.items() if name != best):
        return "fusion"
    return best


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_recipe(recipe: Recipe) -> RecipeOut:
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        url=recipe.url,
        notes=recipe.notes,
        tags=tags_to_list(recipe.tags),
        source=recipe.source,
        cuisine=recipe.cuisine or "other",
        is_favorite=bool(recipe.is_favorite),
        has_user_photo=bool(recipe.user_photo),
        user_photo_url=f"/api/recipes/{recipe.id}/photo" if recipe.user_photo else None,
        created_at=recipe.created_at,
        ingredients=[
            IngredientOut(id=ing.id, name=ing.name, amount=ing.amount) for ing in recipe.ingredients
        ],
    )


app = FastAPI(title="FamilyKitchen")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # same origin in practice; kept open for LAN/mobile
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/api/recipes", response_model=List[RecipeOut])
def list_recipes(db: Session = Depends(get_db)):
    items = db.query(Recipe).order_by(Recipe.created_at.desc()).all()
    return [serialize_recipe(item) for item in items]


@app.post("/api/recipes", response_model=RecipeOut)
def create_recipe(payload: RecipeIn, db: Session = Depends(get_db)):
    normalized_cuisine = normalize_cuisine(payload.cuisine)
    ingredient_names = [ing.name.strip() for ing in payload.ingredients if ing.name and ing.name.strip()]
    resolved_cuisine = (
        infer_cuisine(payload.title, payload.notes, payload.tags, ingredient_names)
        if normalized_cuisine == "auto"
        else normalized_cuisine
    )
    recipe = Recipe(
        id=str(uuid.uuid4()),
        title=payload.title.strip(),
        url=str(payload.url).strip(),
        notes=payload.notes.strip() if payload.notes else None,
        tags=tags_to_string(payload.tags),
        source=payload.source,
        cuisine=resolved_cuisine,
        is_favorite=False,
    )
    db.add(recipe)
    for ing in payload.ingredients:
        ingredient = Ingredient(
            id=str(uuid.uuid4()),
            recipe_id=recipe.id,
            name=ing.name.strip(),
            amount=ing.amount.strip() if ing.amount else None,
        )
        db.add(ingredient)
    db.commit()
    db.refresh(recipe)
    return serialize_recipe(recipe)


@app.put("/api/recipes/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: str, payload: RecipeIn, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    normalized_cuisine = normalize_cuisine(payload.cuisine)
    ingredient_names = [
        ing.name.strip() for ing in payload.ingredients if ing.name and ing.name.strip()
    ] or [
        ing.name.strip() for ing in recipe.ingredients if ing.name and ing.name.strip()
    ]
    resolved_cuisine = (
        infer_cuisine(payload.title, payload.notes, payload.tags, ingredient_names)
        if normalized_cuisine == "auto"
        else normalized_cuisine
    )
    recipe.title = payload.title.strip()
    recipe.url = str(payload.url).strip()
    recipe.notes = payload.notes.strip() if payload.notes else None
    recipe.tags = tags_to_string(payload.tags)
    recipe.source = payload.source
    recipe.cuisine = resolved_cuisine
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return serialize_recipe(recipe)


@app.api_route("/api/recipes/{recipe_id}/favorite", methods=["PATCH", "PUT", "POST"], response_model=RecipeOut)
def toggle_recipe_favorite(recipe_id: str, payload: RecipeFavoriteIn, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe.is_favorite = payload.is_favorite
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return serialize_recipe(recipe)


@app.post("/api/recipes/{recipe_id}/photo", response_model=RecipeOut)
async def upload_recipe_photo(recipe_id: str, photo: UploadFile = File(...), db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다.")

    contents = await photo.read()
    if not contents:
        raise HTTPException(status_code=400, detail="업로드할 이미지가 비어 있습니다.")
    if len(contents) > MAX_USER_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="이미지는 8MB 이하만 업로드할 수 있습니다.")

    recipe.user_photo = contents
    recipe.user_photo_mime = photo.content_type
    recipe.user_photo_name = photo.filename or "photo"
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return serialize_recipe(recipe)


@app.get("/api/recipes/{recipe_id}/photo")
def get_recipe_photo(recipe_id: str, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe or not recipe.user_photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    headers = {
        "Cache-Control": "no-store",
    }
    if recipe.user_photo_name:
        headers["Content-Disposition"] = f'inline; filename="{recipe.user_photo_name}"'

    return Response(
        content=recipe.user_photo,
        media_type=recipe.user_photo_mime or "application/octet-stream",
        headers=headers,
    )


@app.delete("/api/recipes/{recipe_id}/photo", response_model=RecipeOut)
def delete_recipe_photo(recipe_id: str, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe.user_photo = None
    recipe.user_photo_mime = None
    recipe.user_photo_name = None
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return serialize_recipe(recipe)


@app.delete("/api/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: str, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    db.delete(recipe)
    db.commit()
    return None


@app.api_route(
    "/api/recipes/{recipe_id}/ingredients",
    methods=["GET", "POST"],
    response_model=Union[IngredientOut, List[IngredientOut]],
)
@app.api_route(
    "/api/recipes/{recipe_id}/ingredients/",
    methods=["GET", "POST"],
    response_model=Union[IngredientOut, List[IngredientOut]],
)
def ingredients_endpoint(recipe_id: str, db: Session = Depends(get_db), payload: Optional[IngredientIn] = None):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if payload is None:
        return [IngredientOut(id=ing.id, name=ing.name, amount=ing.amount) for ing in recipe.ingredients]
    ing = Ingredient(
        id=str(uuid.uuid4()),
        recipe_id=recipe_id,
        name=payload.name.strip(),
        amount=payload.amount.strip() if payload.amount else None,
    )
    db.add(ing)
    db.commit()
    db.refresh(ing)
    return IngredientOut(id=ing.id, name=ing.name, amount=ing.amount)


@app.put("/api/ingredients/{ingredient_id}", response_model=IngredientOut)
@app.put("/api/ingredients/{ingredient_id}/", response_model=IngredientOut)
def update_ingredient(ingredient_id: str, payload: IngredientIn, db: Session = Depends(get_db)):
    ing = db.get(Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    ing.name = payload.name.strip()
    ing.amount = payload.amount.strip() if payload.amount else None
    db.add(ing)
    db.commit()
    db.refresh(ing)
    return IngredientOut(id=ing.id, name=ing.name, amount=ing.amount)


@app.delete("/api/ingredients/{ingredient_id}", status_code=204)
@app.delete("/api/ingredients/{ingredient_id}/", status_code=204)
def delete_ingredient(ingredient_id: str, db: Session = Depends(get_db)):
    ing = db.get(Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    db.delete(ing)
    db.commit()
    return None


def _extract_meta(html: str, base_url: str = "") -> dict:
    title = ""
    desc = ""
    image = ""
    snippet = ""
    lower = html.lower()
    # naive extraction to avoid heavy deps
    if "<title" in lower:
        start = lower.find("<title")
        start = lower.find(">", start)
        end = lower.find("</title>", start)
        if start != -1 and end != -1:
            title = html[start + 1:end].strip()
    # description meta
    for key in ['name="description"', "property=\"og:description\"", "property='og:description'"]:
        idx = lower.find(key)
        if idx != -1:
            content_idx = lower.find('content=', idx)
            if content_idx != -1:
                quote = lower[content_idx + 8]
                end_idx = lower.find(quote, content_idx + 9)
                if end_idx != -1:
                    desc = html[content_idx + 9:end_idx].strip().replace("\n", " ")
                    break
    # og:image
    for key in ['property="og:image"', "property='og:image'", 'name="twitter:image"']:
        idx = lower.find(key)
        if idx != -1:
            content_idx = lower.find('content=', idx)
            if content_idx != -1:
                quote = lower[content_idx + 8]
                end_idx = lower.find(quote, content_idx + 9)
                if end_idx != -1:
                    image = html[content_idx + 9:end_idx].strip()
                    break
    # first <img> fallback if no image yet
    if not image:
        # try src or data-src / data-original
        img_match = re.search(
            r'<img[^>]+(?:data-original|data-src|src)=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        if img_match:
            img_src = img_match.group(1)
            if img_src.startswith("//"):
                image = "https:" + img_src
            elif img_src.startswith("http"):
                image = img_src
            elif base_url:
                image = urljoin(base_url, img_src)
    # first paragraph as snippet
    match = re.search(r"<p[^>]*>(.*?)</p>", html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        snippet = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return {
        "title": title[:200],
        "description": desc[:300],
        "image": image[:500],
        "snippet": snippet[:400],
    }


def _clean_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_costco_price(value: str) -> Optional[int]:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def _normalize_costco_text(value: str) -> str:
    text = unescape(value or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compact_costco_text(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", _normalize_costco_text(value))


def _tokenize_costco_text(value: str) -> List[str]:
    return [token for token in re.split(r"[^0-9a-z가-힣]+", _normalize_costco_text(value)) if token]


def _costco_slug_to_label(url: str) -> str:
    path = unquote(urlparse(url).path or "")
    parts = [part for part in path.split("/") if part]
    product_parts = []
    for part in parts:
        if part == "p":
            break
        product_parts.append(part)

    slug = product_parts[-1] if product_parts else path
    label = slug.replace("-", " ").replace("_", " ").replace("+", " ")
    return re.sub(r"\s+", " ", label).strip()


def _build_costco_sitemap_entries(xml_text: str) -> List[dict]:
    urls = re.findall(r"<loc>(https://www\.costco\.co\.kr[^<]+/p/[^<]+)</loc>", xml_text)
    entries = []
    seen_urls = set()

    for url in urls:
        if url in seen_urls:
            continue

        product_id_match = re.search(r"/p/([^/?#]+)", url)
        product_id = product_id_match.group(1) if product_id_match else url
        label = _costco_slug_to_label(url)
        search_blob = " ".join([label, product_id, url])
        entries.append(
            {
                "id": product_id,
                "url": url,
                "label": label,
                "search_blob": _normalize_costco_text(search_blob),
                "search_compact": _compact_costco_text(search_blob),
            }
        )
        seen_urls.add(url)

    return entries


def _extract_costco_homepage_items(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_urls = set()

    for card in soup.select("div.item.product-item"):
        link = card.select_one(".item-name a[href]")
        if not link:
            continue

        href = (link.get("href") or "").strip()
        if not href:
            continue

        url = urljoin("https://www.costco.co.kr", href)
        if url in seen_urls:
            continue

        title = _clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        price_el = card.select_one(".product-price-amount .notranslate")
        price_text = _clean_text(price_el.get_text(" ", strip=True)) if price_el else ""
        image_el = card.select_one("img[src]")
        image_url = ""
        if image_el and image_el.get("src"):
            image_url = urljoin("https://www.costco.co.kr", image_el.get("src"))

        product_id_match = re.search(r"/p/([^/?#]+)", url)
        product_id = product_id_match.group(1) if product_id_match else url
        member_only = "회원 전용 아이템" in _clean_text(str(card))

        items.append(
            {
                "id": product_id,
                "title": title,
                "price_text": price_text or ("회원 전용" if member_only else ""),
                "price_value": _parse_costco_price(price_text),
                "url": url,
                "image_url": image_url,
                "member_only": member_only,
                "source": "homepage",
            }
        )
        seen_urls.add(url)

        if len(items) >= 36:
            break

    return items


def _extract_costco_product_item(html: str, final_url: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""

    if soup.title:
        title = _clean_text(soup.title.get_text(" ", strip=True))
        title = re.sub(r"\s*\|\s*코스트코 코리아\s*$", "", title)

    if not title:
        title_el = soup.select_one("h1")
        title = _clean_text(title_el.get_text(" ", strip=True)) if title_el else ""

    if not title:
        return None

    price_el = soup.select_one(".product-price-amount .notranslate")
    price_text = _clean_text(price_el.get_text(" ", strip=True)) if price_el else ""

    meta = _extract_meta(html, base_url=final_url)
    image_url = meta.get("image", "")
    if not image_url:
        image_el = soup.select_one("img[src]")
        if image_el and image_el.get("src"):
            image_url = urljoin(final_url, image_el.get("src"))

    member_only = "회원 전용 아이템" in _clean_text(html[:20000])
    product_id_match = re.search(r"/p/([^/?#]+)", final_url)
    product_id = product_id_match.group(1) if product_id_match else final_url

    return {
        "id": product_id,
        "title": title,
        "price_text": price_text or ("회원 전용" if member_only else ""),
        "price_value": _parse_costco_price(price_text),
        "url": final_url,
        "image_url": image_url,
        "member_only": member_only,
        "source": "fallback",
    }


def _pick_costco_image_url(images: list, fallback_url: str = "") -> str:
    preferred_formats = ("product", "zoom", "desktop", "thumbnail", "cartIcon")

    for preferred in preferred_formats:
        for image in images:
            if image.get("format") == preferred and image.get("url"):
                return urljoin("https://www.costco.co.kr", image["url"])

    for image in images:
        if image.get("url"):
            return urljoin("https://www.costco.co.kr", image["url"])

    return fallback_url


def _format_costco_won(value: Optional[Union[int, float]]) -> str:
    if value is None:
        return ""
    return f"{int(round(float(value))):,}원"


def _format_costco_discount_period(start_at: str, end_at: str) -> str:
    def _to_kst_date(value: str) -> str:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%Y.%m.%d")

    if not start_at or not end_at:
        return ""

    try:
        return f"{_to_kst_date(start_at)} - {_to_kst_date(end_at)}"
    except ValueError:
        return ""


def _build_costco_search_api_item(product: dict) -> Optional[dict]:
    title = _clean_text(product.get("name") or product.get("englishName") or "")
    if not title:
        return None

    price = product.get("price") or product.get("basePrice") or {}
    price_text = _clean_text(price.get("formattedValue") or price.get("formattedPrice") or "")
    price_value = price.get("value")
    if price_value is None and price_text:
        price_value = _parse_costco_price(price_text)

    base_price = product.get("basePrice") or {}
    original_price_text = _clean_text(base_price.get("formattedValue") or base_price.get("formattedPrice") or "")
    original_price_value = base_price.get("value")
    if original_price_value is None and original_price_text:
        original_price_value = _parse_costco_price(original_price_text)

    discount = product.get("couponDiscount") or {}
    hide_discount = bool(discount.get("hideDiscountCalculation"))
    discount_start_at = discount.get("discountStartDate") or ""
    discount_end_at = discount.get("discountEndDate") or ""
    discount_text = _clean_text(discount.get("formattedDiscountValue") or "")
    discount_value = discount.get("discountValue")
    if discount_value is None and discount_text:
        discount_value = _parse_costco_price(discount_text)

    if (
        original_price_value is None
        and price_value is not None
        and discount_value not in (None, 0)
    ):
        original_price_value = float(price_value) + float(discount_value)

    if (
        discount_value in (None, 0)
        and original_price_value is not None
        and price_value is not None
        and float(original_price_value) > float(price_value)
    ):
        discount_value = float(original_price_value) - float(price_value)

    has_discount = bool(
        not hide_discount
        and original_price_value is not None
        and price_value is not None
        and float(original_price_value) > float(price_value)
    )

    if not price_text and price_value is not None:
        price_text = _format_costco_won(price_value)
    if has_discount and not original_price_text and original_price_value is not None:
        original_price_text = _format_costco_won(original_price_value)
    if has_discount and not discount_text and discount_value not in (None, 0):
        discount_text = _format_costco_won(discount_value)
    if not has_discount:
        original_price_text = ""
        original_price_value = None
        discount_text = ""
        discount_value = None
        discount_start_at = ""
        discount_end_at = ""

    discount_period_text = _format_costco_discount_period(discount_start_at, discount_end_at) if has_discount else ""

    member_only = bool(
        product.get("hidePriceValue")
        or product.get("warehouseHidePriceValue")
        or product.get("membershipRestrictionApplied")
    )
    if not price_text and member_only:
        price_text = "회원 전용"

    product_url = product.get("url") or ""
    image_url = _pick_costco_image_url(product.get("images") or [])

    return {
        "id": str(product.get("code") or product_url or title),
        "title": title,
        "price_text": price_text,
        "price_value": price_value,
        "original_price_text": original_price_text,
        "original_price_value": original_price_value,
        "discount_text": discount_text,
        "discount_value": discount_value,
        "has_discount": has_discount,
        "discount_start_at": discount_start_at,
        "discount_end_at": discount_end_at,
        "discount_period_text": discount_period_text,
        "url": urljoin("https://www.costco.co.kr", product_url),
        "image_url": image_url,
        "member_only": member_only,
        "source": "official-search",
    }


async def _search_costco_official_catalog(query: str, limit: int = 12) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        response = await client.get(
            "https://www.costco.co.kr/rest/v2/korea/products/search",
            params={
                "query": query.strip(),
                "fields": "FULL",
                "currentPage": 0,
                "pageSize": limit,
            },
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "application/json,text/plain,*/*",
            },
        )
        response.raise_for_status()
        payload = response.json()

    items = []
    for product in payload.get("products") or []:
        item = _build_costco_search_api_item(product)
        if item:
            items.append(item)

    pagination = payload.get("pagination") or {}
    matched_count = pagination.get("totalResults")
    if not isinstance(matched_count, int):
        matched_count = len(items)

    return {
        "items": items[:limit],
        "matched_count": matched_count,
        "mode": "search",
        "message": "공식몰 전체 검색 결과를 바로 불러와 가격과 제품 정보를 예산 확인용으로 보여줍니다.",
    }


async def _load_costco_shopping_sitemap(force_refresh: bool = False) -> List[dict]:
    fetched_at = COSTCO_SHOPPING_SITEMAP_CACHE["fetched_at"]
    if (
        not force_refresh
        and COSTCO_SHOPPING_SITEMAP_CACHE["entries"]
        and fetched_at
        and datetime.utcnow() - fetched_at < COSTCO_SHOPPING_CACHE_TTL
    ):
        return COSTCO_SHOPPING_SITEMAP_CACHE["entries"]

    sitemap_text, _, content_type = await _fetch_html("https://www.costco.co.kr/sitemap_korea_product.xml")
    entries = _build_costco_sitemap_entries(sitemap_text if "xml" in content_type or sitemap_text else sitemap_text)
    COSTCO_SHOPPING_SITEMAP_CACHE["entries"] = entries
    COSTCO_SHOPPING_SITEMAP_CACHE["fetched_at"] = datetime.utcnow()
    return entries


async def _load_costco_shopping_catalog(force_refresh: bool = False) -> List[dict]:
    fetched_at = COSTCO_SHOPPING_CACHE["fetched_at"]
    if (
        not force_refresh
        and COSTCO_SHOPPING_CACHE["items"]
        and fetched_at
        and datetime.utcnow() - fetched_at < COSTCO_SHOPPING_CACHE_TTL
    ):
        return COSTCO_SHOPPING_CACHE["items"]

    items: List[dict] = []
    homepage_html, final_url, content_type = await _fetch_html("https://www.costco.co.kr/")
    if "text/html" in content_type:
        items = _extract_costco_homepage_items(homepage_html)

    if len(items) < 8:
        fallback_items = []
        for url in COSTCO_SHOPPING_FALLBACK_URLS:
            try:
                html, resolved_url, ctype = await _fetch_html(url)
                if "text/html" not in ctype:
                    continue
                item = _extract_costco_product_item(html, str(resolved_url))
                if item:
                    fallback_items.append(item)
            except Exception:
                continue

        existing_urls = {item["url"] for item in items}
        for item in fallback_items:
            if item["url"] not in existing_urls:
                items.append(item)

    COSTCO_SHOPPING_CACHE["items"] = items
    COSTCO_SHOPPING_CACHE["fetched_at"] = datetime.utcnow()
    return items


async def _load_costco_product_details(url: str, force_refresh: bool = False) -> Optional[dict]:
    cached = COSTCO_SHOPPING_PRODUCT_CACHE.get(url)
    if cached and not force_refresh and datetime.utcnow() - cached["fetched_at"] < COSTCO_SHOPPING_PRODUCT_CACHE_TTL:
        return cached["item"]

    try:
        html, final_url, content_type = await _fetch_html(url)
        if "text/html" not in content_type:
            return cached["item"] if cached else None
        item = _extract_costco_product_item(html, str(final_url))
        if not item:
            return cached["item"] if cached else None
        COSTCO_SHOPPING_PRODUCT_CACHE[url] = {"item": item, "fetched_at": datetime.utcnow()}
        return item
    except Exception:
        return cached["item"] if cached else None


def _score_costco_entry(entry: dict, query: str) -> int:
    query_normalized = _normalize_costco_text(query)
    query_compact = _compact_costco_text(query)
    query_tokens = _tokenize_costco_text(query)
    if not query_compact and not query_tokens:
        return 0

    search_blob = entry.get("search_blob", "")
    search_compact = entry.get("search_compact", "")
    cached = COSTCO_SHOPPING_PRODUCT_CACHE.get(entry["url"])
    if cached:
        cached_title = cached["item"].get("title", "")
        search_blob = f"{search_blob} {_normalize_costco_text(cached_title)}"
        search_compact = f"{search_compact}{_compact_costco_text(cached_title)}"

    score = 0
    if query_compact and query_compact in search_compact:
        score += 120
        if search_compact.startswith(query_compact):
            score += 80

    token_hits = 0
    for token in query_tokens:
        if token in search_blob:
            token_hits += 1
            score += 18

    if query_tokens and token_hits != len(query_tokens) and not (query_compact and query_compact in search_compact):
        return -1

    return score


def _fallback_costco_item(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "title": entry["label"] or entry["id"],
        "price_text": "가격은 결과 클릭 시 확인",
        "price_value": None,
        "url": entry["url"],
        "image_url": "",
        "member_only": False,
        "source": "sitemap",
    }


async def _search_costco_shopping_catalog(query: str, limit: int = 12, refresh: bool = False) -> dict:
    entries = await _load_costco_shopping_sitemap(force_refresh=refresh)
    fetched_at = COSTCO_SHOPPING_SITEMAP_CACHE["fetched_at"]

    if not query.strip():
        featured = await _load_costco_shopping_catalog(force_refresh=refresh)
        return {
            "items": featured[:limit],
            "matched_count": len(featured),
            "total_catalog_count": len(entries),
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
            "mode": "featured",
            "message": "전체 상품 수는 sitemap으로 확인하고, 기본 화면은 공식몰 메인에 노출된 상품 일부를 먼저 보여줍니다.",
        }

    try:
        payload = await _search_costco_official_catalog(query, limit=limit)
        payload["total_catalog_count"] = len(entries)
        payload["fetched_at"] = fetched_at.isoformat() if fetched_at else None
        return payload
    except Exception:
        scored = []
        for entry in entries:
            score = _score_costco_entry(entry, query)
            if score >= 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: (-item[0], item[1]["label"]))
        matched_count = len(scored)
        candidates = [entry for _, entry in scored[: max(limit * 2, 24)]]

        tasks = [_load_costco_product_details(entry["url"]) for entry in candidates[:limit]]
        enriched_results = await asyncio.gather(*tasks, return_exceptions=True)

        items = []
        for entry, result in zip(candidates[:limit], enriched_results):
            if isinstance(result, Exception) or not result:
                items.append(_fallback_costco_item(entry))
            else:
                items.append(result)

        return {
            "items": items,
            "matched_count": matched_count,
            "total_catalog_count": len(entries),
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
            "mode": "search-fallback",
            "message": "공식 검색 응답이 불안정해 sitemap 후보와 상품 페이지 보강 방식으로 임시 전환했습니다.",
        }


async def _fetch_html(url: str) -> Tuple[str, httpx.URL, str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        resp = await client.get(
            url,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
    return resp.text, resp.url, resp.headers.get("content-type", "")


async def _resolve_article_html(url: str) -> Tuple[str, str, str]:
    text, final_url, content_type = await _fetch_html(url)
    parsed = urlparse(str(final_url))

    # Naver blog often serves the actual post inside mainFrame.
    if "blog.naver.com" in parsed.netloc and 'id="mainFrame"' in text:
        iframe_match = re.search(r'id="mainFrame"[^>]+src="([^"]+)"', text, flags=re.IGNORECASE)
        if iframe_match:
            inner_url = urljoin(str(final_url), iframe_match.group(1))
            text, final_url, content_type = await _fetch_html(inner_url)

    return text, content_type, str(final_url)


@app.get("/api/preview")
async def preview(url: HttpUrl):
    try:
        text, ctype, final_url = await _resolve_article_html(str(url))
        if "text/html" not in ctype:
            return {
                "title": "",
                "description": "",
                "site": urlparse(final_url).netloc,
                "image": "",
                "snippet": "",
            }
        text = text[:50000]
        meta = _extract_meta(text, base_url=final_url)
        return {
            "title": meta["title"],
            "description": meta["description"],
            "image": meta["image"],
            "snippet": meta["snippet"],
            "site": urlparse(final_url).netloc,
        }
    except Exception as exc:  # noqa: BLE001
        return {"title": "", "description": "", "site": "", "image": "", "snippet": ""}


@app.get("/api/shopping/catalog")
async def shopping_catalog(refresh: bool = False):
    try:
        payload = await _search_costco_shopping_catalog("", limit=24, refresh=refresh)
        return {
            "items": payload["items"],
            "count": len(payload["items"]),
            "total_catalog_count": payload["total_catalog_count"],
            "matched_count": payload["matched_count"],
            "fetched_at": payload["fetched_at"],
            "message": payload["message"],
            "mode": payload["mode"],
        }
    except Exception:
        return {
            "items": [],
            "count": 0,
            "total_catalog_count": 0,
            "matched_count": 0,
            "fetched_at": None,
            "message": "공식몰 상품 목록을 불러오지 못했습니다.",
            "mode": "error",
        }


@app.get("/api/shopping/search")
async def shopping_search(q: str = "", limit: int = 12, refresh: bool = False):
    safe_limit = max(1, min(limit, 24))
    try:
        payload = await _search_costco_shopping_catalog(q, limit=safe_limit, refresh=refresh)
        return {
            "items": payload["items"],
            "count": len(payload["items"]),
            "total_catalog_count": payload["total_catalog_count"],
            "matched_count": payload["matched_count"],
            "fetched_at": payload["fetched_at"],
            "message": payload["message"],
            "mode": payload["mode"],
            "query": q,
        }
    except Exception:
        return {
            "items": [],
            "count": 0,
            "total_catalog_count": 0,
            "matched_count": 0,
            "fetched_at": None,
            "message": "공식몰 검색 결과를 불러오지 못했습니다.",
            "mode": "error",
            "query": q,
        }


# Serve static front-end files after API routes
@app.get("/shopping")
def shopping_page():
    return FileResponse(BASE_DIR / "shopping.html")


@app.get("/pc")
def pc_page():
    return FileResponse(BASE_DIR / "pc.html")


@app.get("/m")
def mobile_page():
    return FileResponse(BASE_DIR / "m.html")


def _is_mobile_request(request: Request) -> bool:
    user_agent = request.headers.get("user-agent", "").lower()
    mobile_tokens = ("iphone", "android", "mobile", "ipad", "ipod")
    return any(token in user_agent for token in mobile_tokens)


@app.get("/recipes")
def recipes_page(request: Request):
    return FileResponse(BASE_DIR / ("m.html" if _is_mobile_request(request) else "pc.html"))


@app.get("/")
def root():
    return FileResponse(BASE_DIR / "home.html")

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")
# Request headers
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
