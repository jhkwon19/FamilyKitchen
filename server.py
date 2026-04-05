import os
import uuid
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus, urljoin, urlparse
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
import httpx
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, MetaData, String, Text, create_engine, func
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
    response_model=IngredientOut | List[IngredientOut],
)
@app.api_route(
    "/api/recipes/{recipe_id}/ingredients/",
    methods=["GET", "POST"],
    response_model=IngredientOut | List[IngredientOut],
)
def ingredients_endpoint(recipe_id: str, db: Session = Depends(get_db), payload: IngredientIn | None = None):
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


def _dedupe_keep_order(values: list[str], limit: int | None = None) -> list[str]:
    seen = set()
    items: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        items.append(value)
        if limit is not None and len(items) >= limit:
            break
    return items


def _looks_like_noise(text: str) -> bool:
    lowered = text.lower()
    noise_markers = [
        "copyright",
        "advertisement",
        "광고",
        "댓글",
        "공유",
        "좋아요",
        "구독",
        "이전",
        "다음",
        "category",
    ]
    return any(marker in lowered for marker in noise_markers)


def _extract_article(html: str, base_url: str = "") -> dict:
    meta = _extract_meta(html, base_url=base_url)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, svg, header, footer, nav, aside"):
        tag.decompose()

    candidates = [
        ".se-main-container",
        "#postViewArea",
        ".post-view",
        ".tt_article_useless_p_margin",
        ".entry-content",
        ".article-view",
        ".article_view",
        ".contents_style",
        ".post-content",
        ".post_content",
        ".article-body",
        ".article_body",
        "article",
        "main",
        "#content",
        ".content",
    ]
    article_root = None
    for selector in candidates:
        found = soup.select_one(selector)
        if found and len(found.get_text(" ", strip=True)) > 120:
            article_root = found
            break

    if article_root is None:
        article_root = soup.body or soup

    blocks: list[str] = []
    for node in article_root.select("p, li, h2, h3"):
        text = _clean_text(str(node))
        if len(text) < 20 or _looks_like_noise(text):
            continue
        blocks.append(text)

    if not blocks:
        for node in article_root.select("div"):
            text = _clean_text(str(node))
            if len(text) < 60 or _looks_like_noise(text):
                continue
            blocks.append(text)

    paragraphs = _dedupe_keep_order(blocks, limit=80)

    return {
        "title": meta["title"],
        "description": meta["description"],
        "image": meta["image"],
        "snippet": meta["snippet"],
        "paragraphs": paragraphs,
    }


async def _fetch_html(url: str) -> tuple[str, httpx.URL, str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        resp = await client.get(
            url,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
    return resp.text, resp.url, resp.headers.get("content-type", "")


async def _resolve_article_html(url: str) -> tuple[str, str, str]:
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


@app.get("/api/article")
async def article(url: HttpUrl):
    try:
        text, ctype, final_url = await _resolve_article_html(str(url))
        if "text/html" not in ctype:
            return {
                "title": "",
                "description": "",
                "site": urlparse(final_url).netloc,
                "image": "",
                "snippet": "",
                "paragraphs": [],
            }
        text = text[:500000]
        article_data = _extract_article(text, base_url=final_url)
        return {
            "title": article_data["title"],
            "description": article_data["description"],
            "image": article_data["image"],
            "snippet": article_data["snippet"],
            "paragraphs": article_data["paragraphs"],
            "site": urlparse(final_url).netloc,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "title": "",
            "description": "",
            "site": "",
            "image": "",
            "snippet": "",
            "paragraphs": [],
        }


# Serve static front-end files after API routes
@app.get("/pc")
def pc_page():
    return FileResponse(BASE_DIR / "pc.html")


@app.get("/m")
def mobile_page():
    return FileResponse(BASE_DIR / "m.html")


@app.get("/")
def root():
    return RedirectResponse(url="/pc")

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")
# Request headers
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
