import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus, urljoin
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
import httpx
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import Column, DateTime, ForeignKey, MetaData, String, Text, create_engine, func
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
    ingredients: List["IngredientIn"] = Field(default_factory=list)


class RecipeOut(RecipeIn):
    id: str
    created_at: datetime
    ingredients: List["IngredientOut"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class IngredientIn(BaseModel):
    name: str = Field(..., max_length=255)
    amount: Optional[str] = Field(default=None, max_length=255)


class IngredientOut(IngredientIn):
    id: str

    model_config = ConfigDict(from_attributes=True)


RecipeIn.update_forward_refs()
RecipeOut.update_forward_refs()


def tags_to_string(tags: List[str]) -> str:
    return ",".join([t.strip() for t in tags if t.strip()])


def tags_to_list(tag_string: Optional[str]) -> List[str]:
    if not tag_string:
        return []
    return [t for t in (tag_string or "").split(",") if t]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    return [
        RecipeOut(
            id=item.id,
            title=item.title,
            url=item.url,
            notes=item.notes,
            tags=tags_to_list(item.tags),
            source=item.source,
            created_at=item.created_at,
            ingredients=[
                IngredientOut(id=ing.id, name=ing.name, amount=ing.amount) for ing in item.ingredients
            ],
        )
        for item in items
    ]


@app.post("/api/recipes", response_model=RecipeOut)
def create_recipe(payload: RecipeIn, db: Session = Depends(get_db)):
    recipe = Recipe(
        id=str(uuid.uuid4()),
        title=payload.title.strip(),
        url=str(payload.url).strip(),
        notes=payload.notes.strip() if payload.notes else None,
        tags=tags_to_string(payload.tags),
        source=payload.source,
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
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        url=recipe.url,
        notes=recipe.notes,
        tags=tags_to_list(recipe.tags),
        source=recipe.source,
        created_at=recipe.created_at,
        ingredients=[
            IngredientOut(id=ing.id, name=ing.name, amount=ing.amount) for ing in recipe.ingredients
        ],
    )


@app.put("/api/recipes/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: str, payload: RecipeIn, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe.title = payload.title.strip()
    recipe.url = str(payload.url).strip()
    recipe.notes = payload.notes.strip() if payload.notes else None
    recipe.tags = tags_to_string(payload.tags)
    recipe.source = payload.source
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        url=recipe.url,
        notes=recipe.notes,
        tags=tags_to_list(recipe.tags),
        source=recipe.source,
        created_at=recipe.created_at,
        ingredients=[
            IngredientOut(id=ing.id, name=ing.name, amount=ing.amount) for ing in recipe.ingredients
        ],
    )


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


@app.get("/api/preview")
async def preview(url: HttpUrl):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
            resp = await client.get(
                str(url),
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
        ctype = resp.headers.get("content-type", "")
        if "text/html" not in ctype:
            return {"title": "", "description": "", "site": resp.url.host, "image": "", "snippet": ""}
        text = resp.text[:50000]  # limit
        meta = _extract_meta(text, base_url=str(resp.url))
        return {
            "title": meta["title"],
            "description": meta["description"],
            "image": meta["image"],
            "snippet": meta["snippet"],
            "site": resp.url.host,
        }
    except Exception as exc:  # noqa: BLE001
        return {"title": "", "description": "", "site": "", "image": "", "snippet": ""}


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
