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
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, MetaData, String, Text, create_engine, func, or_
from sqlalchemy.orm import Session, declarative_base, relationship, selectinload, sessionmaker

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


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    target_year = Column(Integer, nullable=True, index=True)
    target_month = Column(Integer, nullable=True, index=True)
    budget = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="draft", index=True)
    notes = Column(Text, nullable=True)
    source_list_id = Column(String(36), ForeignKey("shopping_lists.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ShoppingItem",
        cascade="all, delete-orphan",
        back_populates="shopping_list",
        order_by="ShoppingItem.sort_order.asc(), ShoppingItem.created_at.asc()",
    )
    source_list = relationship("ShoppingList", remote_side=[id], uselist=False)


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id = Column(String(36), primary_key=True, index=True)
    list_id = Column(String(36), ForeignKey("shopping_lists.id", ondelete="CASCADE"), nullable=False, index=True)
    product_name = Column(String(255), nullable=False)
    product_url = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    costco_product_id = Column(String(64), nullable=True, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    expected_price = Column(Integer, nullable=False, default=0)
    price_text = Column(String(64), nullable=True)
    original_price = Column(Integer, nullable=True)
    original_price_text = Column(String(64), nullable=True)
    discount_amount = Column(Integer, nullable=True)
    discount_text = Column(String(64), nullable=True)
    discount_period_text = Column(String(64), nullable=True)
    member_only = Column(Boolean, nullable=False, default=False)
    is_checked = Column(Boolean, nullable=False, default=False, index=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    shopping_list = relationship("ShoppingList", back_populates="items")


class CostcoProduct(Base):
    __tablename__ = "costco_products"

    id = Column(String(64), primary_key=True)
    product_name = Column(String(255), nullable=False, index=True)
    product_url = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    category_path = Column(Text, nullable=True)
    category_text = Column(Text, nullable=True)
    price = Column(Integer, nullable=True)
    price_text = Column(String(64), nullable=True)
    original_price = Column(Integer, nullable=True)
    original_price_text = Column(String(64), nullable=True)
    discount_amount = Column(Integer, nullable=True)
    discount_text = Column(String(64), nullable=True)
    discount_period_text = Column(String(64), nullable=True)
    member_only = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


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


class ShoppingItemBase(BaseModel):
    product_name: str = Field(..., max_length=255)
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    costco_product_id: Optional[str] = Field(default=None, max_length=64)
    quantity: int = Field(default=1, ge=1)
    expected_price: int = Field(default=0, ge=0)
    price_text: Optional[str] = Field(default=None, max_length=64)
    original_price: Optional[int] = Field(default=None, ge=0)
    original_price_text: Optional[str] = Field(default=None, max_length=64)
    discount_amount: Optional[int] = Field(default=None, ge=0)
    discount_text: Optional[str] = Field(default=None, max_length=64)
    discount_period_text: Optional[str] = Field(default=None, max_length=64)
    member_only: bool = False
    is_checked: bool = False
    note: Optional[str] = None
    sort_order: int = Field(default=0, ge=0)


class ShoppingItemIn(ShoppingItemBase):
    pass


class ShoppingItemOut(ShoppingItemBase):
    id: str
    list_id: str
    checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShoppingListBase(BaseModel):
    title: str = Field(..., max_length=255)
    target_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    target_month: Optional[int] = Field(default=None, ge=1, le=12)
    budget: int = Field(default=0, ge=0)
    status: str = Field(default="draft", max_length=24)
    notes: Optional[str] = None


class ShoppingListIn(ShoppingListBase):
    source_list_id: Optional[str] = None
    items: List[ShoppingItemIn] = Field(default_factory=list)


class ShoppingListUpdateIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    target_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    target_month: Optional[int] = Field(default=None, ge=1, le=12)
    budget: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, max_length=24)
    notes: Optional[str] = None


class ShoppingListOut(ShoppingListBase):
    id: str
    source_list_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    items: List[ShoppingItemOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ShoppingListSummaryOut(ShoppingListBase):
    id: str
    source_list_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    item_count: int = 0
    checked_count: int = 0
    estimated_total: int = 0
    picked_total: int = 0

    model_config = ConfigDict(from_attributes=True)


class ShoppingHistoryMonthOut(BaseModel):
    target_year: int
    target_month: int
    list_count: int
    latest_updated_at: datetime


class ShoppingItemUpdateIn(BaseModel):
    product_name: Optional[str] = Field(default=None, max_length=255)
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    costco_product_id: Optional[str] = Field(default=None, max_length=64)
    quantity: Optional[int] = Field(default=None, ge=1)
    expected_price: Optional[int] = Field(default=None, ge=0)
    price_text: Optional[str] = Field(default=None, max_length=64)
    original_price: Optional[int] = Field(default=None, ge=0)
    original_price_text: Optional[str] = Field(default=None, max_length=64)
    discount_amount: Optional[int] = Field(default=None, ge=0)
    discount_text: Optional[str] = Field(default=None, max_length=64)
    discount_period_text: Optional[str] = Field(default=None, max_length=64)
    member_only: Optional[bool] = None
    is_checked: Optional[bool] = None
    note: Optional[str] = None
    sort_order: Optional[int] = Field(default=None, ge=0)


RecipeIn.update_forward_refs()
RecipeOut.update_forward_refs()


def _read_int_env(name: str, default: int, min_value: int, max_value: Optional[int] = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    value = max(min_value, value)
    return min(value, max_value) if max_value is not None else value


MAX_USER_PHOTO_BYTES = 8 * 1024 * 1024
COSTCO_SHOPPING_CACHE_TTL = timedelta(minutes=30)
COSTCO_SHOPPING_CACHE = {"items": [], "fetched_at": None}
COSTCO_SHOPPING_SITEMAP_CACHE = {"entries": [], "fetched_at": None}
COSTCO_SHOPPING_PRODUCT_CACHE_TTL = timedelta(hours=12)
COSTCO_SHOPPING_PRODUCT_CACHE = {}
COSTCO_PRODUCTS_AUTO_SYNC_ENABLED = os.environ.get("COSTCO_PRODUCTS_AUTO_SYNC", "1").lower() not in {"0", "false", "no"}
COSTCO_PRODUCTS_AUTO_SYNC_BATCH_SIZE = _read_int_env("COSTCO_PRODUCTS_AUTO_SYNC_BATCH_SIZE", 30, 1, 100)
COSTCO_PRODUCTS_AUTO_SYNC_INTERVAL_SECONDS = _read_int_env("COSTCO_PRODUCTS_AUTO_SYNC_INTERVAL_SECONDS", 600, 60)
COSTCO_PRODUCTS_SITEMAP_SYNC_INTERVAL_SECONDS = _read_int_env("COSTCO_PRODUCTS_SITEMAP_SYNC_INTERVAL_SECONDS", 86400, 3600)
COSTCO_PRODUCTS_AUTO_SYNC_START_DELAY_SECONDS = _read_int_env("COSTCO_PRODUCTS_AUTO_SYNC_START_DELAY_SECONDS", 5, 0)
COSTCO_PRODUCTS_AUTO_SYNC_TASK = None
KST = timezone(timedelta(hours=9))
COSTCO_SHOPPING_FALLBACK_URLS = [
    "https://www.costco.co.kr/p/692714",
    "https://www.costco.co.kr/Appliances/Seasonal-Appliances/FansAir-Circulator/Dyson-HotCool-Fan-Heater-AM09/p/672973",
    "https://www.costco.co.kr/ClothingBagsAccessories/Clothing-for-Men/Pants-for-Men/Guess-Mens-Jeans/p/677768",
    "https://www.costco.co.kr/Foods/SaucesCondiments/SaucesDressings/De-Nigris-Organic-Apple-Cider-Vinegar-15ml-x-50/p/690444",
]
VALID_SHOPPING_LIST_STATUSES = {"draft", "active", "done", "archived"}


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


def normalize_shopping_list_status(value: Optional[str]) -> str:
    lowered = (value or "draft").strip().lower()
    if lowered not in VALID_SHOPPING_LIST_STATUSES:
        raise HTTPException(status_code=400, detail="유효하지 않은 장보기 리스트 상태입니다.")
    return lowered


def serialize_shopping_item(item: ShoppingItem) -> ShoppingItemOut:
    return ShoppingItemOut(
        id=item.id,
        list_id=item.list_id,
        product_name=item.product_name,
        product_url=item.product_url,
        image_url=item.image_url,
        costco_product_id=item.costco_product_id,
        quantity=item.quantity,
        expected_price=item.expected_price or 0,
        price_text=item.price_text,
        original_price=item.original_price,
        original_price_text=item.original_price_text,
        discount_amount=item.discount_amount,
        discount_text=item.discount_text,
        discount_period_text=item.discount_period_text,
        member_only=bool(item.member_only),
        is_checked=bool(item.is_checked),
        checked_at=item.checked_at,
        note=item.note,
        sort_order=item.sort_order or 0,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _shopping_list_totals(shopping_list: ShoppingList) -> Tuple[int, int, int, int]:
    item_count = len(shopping_list.items)
    checked_count = sum(1 for item in shopping_list.items if item.is_checked)
    estimated_total = sum((item.expected_price or 0) * max(item.quantity or 1, 1) for item in shopping_list.items)
    picked_total = sum(
        (item.expected_price or 0) * max(item.quantity or 1, 1)
        for item in shopping_list.items
        if item.is_checked
    )
    return item_count, checked_count, estimated_total, picked_total


def serialize_shopping_list_summary(shopping_list: ShoppingList) -> ShoppingListSummaryOut:
    item_count, checked_count, estimated_total, picked_total = _shopping_list_totals(shopping_list)
    return ShoppingListSummaryOut(
        id=shopping_list.id,
        title=shopping_list.title,
        target_year=shopping_list.target_year,
        target_month=shopping_list.target_month,
        budget=shopping_list.budget or 0,
        status=shopping_list.status,
        notes=shopping_list.notes,
        source_list_id=shopping_list.source_list_id,
        created_at=shopping_list.created_at,
        updated_at=shopping_list.updated_at,
        completed_at=shopping_list.completed_at,
        item_count=item_count,
        checked_count=checked_count,
        estimated_total=estimated_total,
        picked_total=picked_total,
    )


def serialize_shopping_list(shopping_list: ShoppingList) -> ShoppingListOut:
    return ShoppingListOut(
        id=shopping_list.id,
        title=shopping_list.title,
        target_year=shopping_list.target_year,
        target_month=shopping_list.target_month,
        budget=shopping_list.budget or 0,
        status=shopping_list.status,
        notes=shopping_list.notes,
        source_list_id=shopping_list.source_list_id,
        created_at=shopping_list.created_at,
        updated_at=shopping_list.updated_at,
        completed_at=shopping_list.completed_at,
        items=[serialize_shopping_item(item) for item in shopping_list.items],
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
async def startup():
    global COSTCO_PRODUCTS_AUTO_SYNC_TASK
    Base.metadata.create_all(bind=engine)
    if COSTCO_PRODUCTS_AUTO_SYNC_ENABLED and COSTCO_PRODUCTS_AUTO_SYNC_TASK is None:
        COSTCO_PRODUCTS_AUTO_SYNC_TASK = asyncio.create_task(_costco_products_auto_sync_loop())


@app.on_event("shutdown")
async def shutdown():
    global COSTCO_PRODUCTS_AUTO_SYNC_TASK
    if COSTCO_PRODUCTS_AUTO_SYNC_TASK:
        COSTCO_PRODUCTS_AUTO_SYNC_TASK.cancel()
        COSTCO_PRODUCTS_AUTO_SYNC_TASK = None


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


@app.get("/api/shopping/lists/history", response_model=List[ShoppingHistoryMonthOut])
def list_shopping_history_months(db: Session = Depends(get_db)):
    rows = (
        db.query(
            ShoppingList.target_year,
            ShoppingList.target_month,
            func.count(ShoppingList.id).label("list_count"),
            func.max(ShoppingList.updated_at).label("latest_updated_at"),
        )
        .filter(ShoppingList.target_year.isnot(None), ShoppingList.target_month.isnot(None))
        .group_by(ShoppingList.target_year, ShoppingList.target_month)
        .order_by(ShoppingList.target_year.desc(), ShoppingList.target_month.desc())
        .all()
    )
    return [
        ShoppingHistoryMonthOut(
            target_year=row.target_year,
            target_month=row.target_month,
            list_count=row.list_count,
            latest_updated_at=row.latest_updated_at,
        )
        for row in rows
    ]


@app.get("/api/shopping/lists", response_model=List[ShoppingListSummaryOut])
def list_shopping_lists(
    year: Optional[int] = None,
    month: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(ShoppingList).options(selectinload(ShoppingList.items))
    if year is not None:
        query = query.filter(ShoppingList.target_year == year)
    if month is not None:
        query = query.filter(ShoppingList.target_month == month)
    if status:
        query = query.filter(ShoppingList.status == normalize_shopping_list_status(status))

    items = (
        query.order_by(
            ShoppingList.target_year.desc(),
            ShoppingList.target_month.desc(),
            ShoppingList.updated_at.desc(),
            ShoppingList.created_at.desc(),
        ).all()
    )
    return [serialize_shopping_list_summary(item) for item in items]


@app.get("/api/shopping/lists/{list_id}", response_model=ShoppingListOut)
def get_shopping_list(list_id: str, db: Session = Depends(get_db)):
    shopping_list = (
        db.query(ShoppingList)
        .options(selectinload(ShoppingList.items))
        .filter(ShoppingList.id == list_id)
        .first()
    )
    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")
    return serialize_shopping_list(shopping_list)


@app.post("/api/shopping/lists", response_model=ShoppingListOut)
def create_shopping_list(payload: ShoppingListIn, db: Session = Depends(get_db)):
    shopping_list = ShoppingList(
        id=str(uuid.uuid4()),
        title=payload.title.strip(),
        target_year=payload.target_year,
        target_month=payload.target_month,
        budget=payload.budget,
        status=normalize_shopping_list_status(payload.status),
        notes=payload.notes.strip() if payload.notes else None,
        source_list_id=payload.source_list_id,
    )
    db.add(shopping_list)
    db.flush()

    for index, item in enumerate(payload.items):
        db.add(
            ShoppingItem(
                id=str(uuid.uuid4()),
                list_id=shopping_list.id,
                product_name=item.product_name.strip(),
                product_url=item.product_url.strip() if item.product_url else None,
                image_url=item.image_url.strip() if item.image_url else None,
                costco_product_id=item.costco_product_id.strip() if item.costco_product_id else None,
                quantity=item.quantity,
                expected_price=item.expected_price,
                price_text=item.price_text.strip() if item.price_text else None,
                original_price=item.original_price,
                original_price_text=item.original_price_text.strip() if item.original_price_text else None,
                discount_amount=item.discount_amount,
                discount_text=item.discount_text.strip() if item.discount_text else None,
                discount_period_text=item.discount_period_text.strip() if item.discount_period_text else None,
                member_only=item.member_only,
                is_checked=item.is_checked,
                checked_at=datetime.now(timezone.utc) if item.is_checked else None,
                note=item.note.strip() if item.note else None,
                sort_order=item.sort_order if item.sort_order else index,
            )
        )

    db.commit()
    created = (
        db.query(ShoppingList)
        .options(selectinload(ShoppingList.items))
        .filter(ShoppingList.id == shopping_list.id)
        .first()
    )
    if not created:
        raise HTTPException(status_code=500, detail="Shopping list was not persisted")
    return serialize_shopping_list(created)


@app.patch("/api/shopping/lists/{list_id}", response_model=ShoppingListOut)
def update_shopping_list(list_id: str, payload: ShoppingListUpdateIn, db: Session = Depends(get_db)):
    shopping_list = (
        db.query(ShoppingList)
        .options(selectinload(ShoppingList.items))
        .filter(ShoppingList.id == list_id)
        .first()
    )
    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    if payload.title is not None:
        shopping_list.title = payload.title.strip()
    if payload.target_year is not None:
        shopping_list.target_year = payload.target_year
    if payload.target_month is not None:
        shopping_list.target_month = payload.target_month
    if payload.budget is not None:
        shopping_list.budget = payload.budget
    if payload.notes is not None:
        shopping_list.notes = payload.notes.strip() if payload.notes else None
    if payload.status is not None:
        shopping_list.status = normalize_shopping_list_status(payload.status)
        shopping_list.completed_at = datetime.now(timezone.utc) if shopping_list.status == "done" else None

    db.add(shopping_list)
    db.commit()
    db.refresh(shopping_list)
    return serialize_shopping_list(shopping_list)


@app.delete("/api/shopping/lists/{list_id}", status_code=204)
def delete_shopping_list(list_id: str, db: Session = Depends(get_db)):
    shopping_list = db.get(ShoppingList, list_id)
    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    db.delete(shopping_list)
    db.commit()
    return None


@app.delete("/api/shopping/lists/{list_id}/items", status_code=204)
def reset_shopping_list_items(list_id: str, db: Session = Depends(get_db)):
    shopping_list = db.get(ShoppingList, list_id)
    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    db.query(ShoppingItem).filter(ShoppingItem.list_id == list_id).delete()
    db.commit()
    return None


@app.put("/api/shopping/lists/{list_id}/items", response_model=ShoppingListOut)
def replace_shopping_list_items(list_id: str, payload: List[ShoppingItemIn], db: Session = Depends(get_db)):
    shopping_list = db.get(ShoppingList, list_id)
    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    db.query(ShoppingItem).filter(ShoppingItem.list_id == list_id).delete()
    for index, item in enumerate(payload):
        db.add(
            ShoppingItem(
                id=str(uuid.uuid4()),
                list_id=list_id,
                product_name=item.product_name.strip(),
                product_url=item.product_url.strip() if item.product_url else None,
                image_url=item.image_url.strip() if item.image_url else None,
                costco_product_id=item.costco_product_id.strip() if item.costco_product_id else None,
                quantity=item.quantity,
                expected_price=item.expected_price,
                price_text=item.price_text.strip() if item.price_text else None,
                original_price=item.original_price,
                original_price_text=item.original_price_text.strip() if item.original_price_text else None,
                discount_amount=item.discount_amount,
                discount_text=item.discount_text.strip() if item.discount_text else None,
                discount_period_text=item.discount_period_text.strip() if item.discount_period_text else None,
                member_only=item.member_only,
                is_checked=item.is_checked,
                checked_at=datetime.now(timezone.utc) if item.is_checked else None,
                note=item.note.strip() if item.note else None,
                sort_order=item.sort_order if item.sort_order else index,
            )
        )

    db.commit()
    updated = (
        db.query(ShoppingList)
        .options(selectinload(ShoppingList.items))
        .filter(ShoppingList.id == list_id)
        .first()
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Shopping list was not persisted")
    return serialize_shopping_list(updated)


@app.post("/api/shopping/lists/{list_id}/items", response_model=ShoppingItemOut)
def create_shopping_item(list_id: str, payload: ShoppingItemIn, db: Session = Depends(get_db)):
    shopping_list = db.get(ShoppingList, list_id)
    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    max_sort_order = (
        db.query(func.max(ShoppingItem.sort_order))
        .filter(ShoppingItem.list_id == list_id)
        .scalar()
    )
    item = ShoppingItem(
        id=str(uuid.uuid4()),
        list_id=list_id,
        product_name=payload.product_name.strip(),
        product_url=payload.product_url.strip() if payload.product_url else None,
        image_url=payload.image_url.strip() if payload.image_url else None,
        costco_product_id=payload.costco_product_id.strip() if payload.costco_product_id else None,
        quantity=payload.quantity,
        expected_price=payload.expected_price,
        price_text=payload.price_text.strip() if payload.price_text else None,
        original_price=payload.original_price,
        original_price_text=payload.original_price_text.strip() if payload.original_price_text else None,
        discount_amount=payload.discount_amount,
        discount_text=payload.discount_text.strip() if payload.discount_text else None,
        discount_period_text=payload.discount_period_text.strip() if payload.discount_period_text else None,
        member_only=payload.member_only,
        is_checked=payload.is_checked,
        checked_at=datetime.now(timezone.utc) if payload.is_checked else None,
        note=payload.note.strip() if payload.note else None,
        sort_order=(max_sort_order + 1) if max_sort_order is not None and payload.sort_order == 0 else payload.sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_shopping_item(item)


@app.patch("/api/shopping/items/{item_id}", response_model=ShoppingItemOut)
def update_shopping_item(item_id: str, payload: ShoppingItemUpdateIn, db: Session = Depends(get_db)):
    item = db.get(ShoppingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Shopping item not found")

    if payload.product_name is not None:
        item.product_name = payload.product_name.strip()
    if payload.product_url is not None:
        item.product_url = payload.product_url.strip() if payload.product_url else None
    if payload.image_url is not None:
        item.image_url = payload.image_url.strip() if payload.image_url else None
    if payload.costco_product_id is not None:
        item.costco_product_id = payload.costco_product_id.strip() if payload.costco_product_id else None
    if payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.expected_price is not None:
        item.expected_price = payload.expected_price
    if payload.price_text is not None:
        item.price_text = payload.price_text.strip() if payload.price_text else None
    if payload.original_price is not None:
        item.original_price = payload.original_price
    if payload.original_price_text is not None:
        item.original_price_text = payload.original_price_text.strip() if payload.original_price_text else None
    if payload.discount_amount is not None:
        item.discount_amount = payload.discount_amount
    if payload.discount_text is not None:
        item.discount_text = payload.discount_text.strip() if payload.discount_text else None
    if payload.discount_period_text is not None:
        item.discount_period_text = payload.discount_period_text.strip() if payload.discount_period_text else None
    if payload.member_only is not None:
        item.member_only = payload.member_only
    if payload.note is not None:
        item.note = payload.note.strip() if payload.note else None
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    if payload.is_checked is not None:
        item.is_checked = payload.is_checked
        item.checked_at = datetime.now(timezone.utc) if payload.is_checked else None

    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_shopping_item(item)


@app.delete("/api/shopping/items/{item_id}", status_code=204)
def delete_shopping_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(ShoppingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Shopping item not found")

    db.delete(item)
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


COSTCO_CATEGORY_ROOTS = {
    "Appliances",
    "BabyKidsToysPets",
    "BeautyHouseholdPersonal-Care",
    "ClothingBagsAccessories",
    "ElectronicsComputers",
    "Food",
    "Foods",
    "FurnitureBeddingHome",
    "Gift-Cards-Tickets",
    "GrillsAccessories",
    "HardwareAutomotive",
    "HealthSupplement",
    "HomeKitchen",
    "JewelryWatchesAccessories",
    "PatioLawnGarden",
    "SportsFitnessCamping",
    "StationeryOffice-Supplies",
    "TiresAutomotive",
}

COSTCO_CATEGORY_ROOT_ORDER = [
    "Foods",
    "Food",
    "BeautyHouseholdPersonal-Care",
    "HomeKitchen",
    "Appliances",
    "ElectronicsComputers",
    "FurnitureBeddingHome",
    "ClothingBagsAccessories",
    "BabyKidsToysPets",
    "SportsFitnessCamping",
    "PatioLawnGarden",
    "HardwareAutomotive",
    "TiresAutomotive",
    "StationeryOffice-Supplies",
    "HealthSupplement",
    "JewelryWatchesAccessories",
    "Gift-Cards-Tickets",
    "GrillsAccessories",
]

COSTCO_CATEGORY_LABELS = {
    "Appliances": "가전",
    "Seasonal-Appliances": "계절가전",
    "FansAir-Circulator": "선풍기/공기순환기",
    "Air-ConditionersCooling": "에어컨/냉방",
    "Kitchen-Miscellaneous": "주방 소형가전",
    "Beauty-ToolsHealth-Care": "뷰티/건강가전",
    "Refrigerators": "냉장고",
    "Home-Appliances": "생활가전",
    "WashersDryersClothing-Care-System": "세탁기/건조기/의류관리기",
    "Air-Treatment": "공기관리",
    "Appliance-Packages": "가전 패키지",
    "Commercial-Appliances": "상업용 가전",
    "Foods": "식품",
    "Food": "식품",
    "Processed-Food": "가공식품",
    "Snack": "스낵",
    "Fresh-Foods": "신선식품",
    "MeatSeafood": "정육/해산물",
    "MeatEggs": "정육/계란",
    "FruitVegetables": "과일/채소",
    "Bakery": "베이커리",
    "SaucesCondiments": "소스/양념",
    "SaucesDressings": "소스/드레싱",
    "CondimentsSpices": "양념/향신료",
    "Beverages": "음료",
    "CoffeeTeaDrink": "커피/차/음료",
    "Frozen-Foods": "냉동식품",
    "Chilled-Foods": "냉장식품",
    "Dried-Products": "건조식품",
    "RiceGrains": "쌀/곡물",
    "Instant-Food": "즉석식품",
    "PastaNoodles": "파스타/면",
    "Canned-Goods": "통조림",
    "CookieCracker": "쿠키/크래커",
    "CandyGum": "캔디/껌",
    "Chocolates-Bars": "초콜릿/바",
    "SoftConcentrated-Drinks": "탄산/농축음료",
    "Juice": "주스",
    "Capsule-Coffee": "캡슐커피",
    "TeaLiquid-Tea": "차/액상차",
    "FurnitureBeddingHome": "가구/침구/홈",
    "Living-Room": "거실",
    "Living-Room-Furniture": "거실가구",
    "Sofas": "소파",
    "Home-Decor": "홈데코",
    "CarpetsRugs": "카펫/러그",
    "MirrorsCandlesFramesDecor-Accessories": "거울/캔들/액자/장식소품",
    "Curtains": "커튼",
    "Towels": "타월",
    "Blinds": "블라인드",
    "BathKitchen-Mats": "욕실/주방 매트",
    "Sofa-Pads": "소파패드",
    "Bedding": "침구",
    "Toppers-Pads-Spreads": "토퍼/패드/스프레드",
    "Pillows": "베개",
    "ComfortersBlanketsThrows": "이불/담요/스로우",
    "CushionAccessories": "쿠션/액세서리",
    "Bedroom-Furniture": "침실가구",
    "Beds-Mattresses": "침대/매트리스",
    "Beds": "침대",
    "StoneLoess-Beds": "돌/황토침대",
    "Drawer": "서랍장",
    "KitchenDining-Furniture": "주방/다이닝 가구",
    "Dining-Table-Sets": "식탁세트",
    "Office-Furniture": "사무용 가구",
    "Office-Chairs": "사무용 의자",
    "Lighting": "조명",
    "InfantKids-Furniture": "유아동 가구",
    "ClothingBagsAccessories": "의류/가방/잡화",
    "Clothing-for-Men": "남성의류",
    "Clothing-for-Women": "여성의류",
    "Pants-for-Men": "남성 바지",
    "PantsSkirtDress-for-Women": "여성 바지/스커트/원피스",
    "ShirtsBlouseTop-for-Women": "여성 셔츠/블라우스/상의",
    "ShirtsTopKnit-for-Men": "남성 셔츠/상의/니트",
    "Activewear-for-Women": "여성 액티브웨어",
    "Knitwear-for-Women": "여성 니트웨어",
    "Outerwear-for-Women": "여성 아우터",
    "Outerwear-for-Men": "남성 아우터",
    "Loungewear-for-Women": "여성 라운지웨어",
    "Underwear-for-Women": "여성 언더웨어",
    "Underwear-for-Men": "남성 언더웨어",
    "Underwear-TopSet-for-Women": "여성 언더웨어 상의/세트",
    "SocksHosiery-for-Women": "여성 양말/스타킹",
    "Socks-for-Men": "남성 양말",
    "Womens-Shoes": "여성 신발",
    "Casual-Shoes-For-Women": "여성 캐주얼화",
    "SlippersSandal-for-Women": "여성 슬리퍼/샌들",
    "Athletic-Shoes-for-Women": "여성 운동화",
    "Boots-for-Women": "여성 부츠",
    "Shoes-for-Men": "남성 신발",
    "Casual-Shoes-for-Men": "남성 캐주얼화",
    "SlippersSandal-for-Men": "남성 슬리퍼/샌들",
    "Athletic-Shoes-for-Men": "남성 운동화",
    "Kids-ClothingUnderwear": "아동 의류/언더웨어",
    "Kids-Basic": "아동 기본의류",
    "Kids-Top": "아동 상의",
    "Kids-Bottom": "아동 하의",
    "Kids-TopBottomDress": "아동 상하의/원피스",
    "Kids-Outerwear": "아동 아우터",
    "Childrens-Shoes": "아동 신발",
    "Basics": "기본 잡화",
    "HatMufflers": "모자/머플러",
    "Fashion-Accessories": "패션잡화",
    "Luggages": "여행가방",
    "Checked-Luggage": "위탁수하물 가방",
    "Backpacks-Bags": "백팩/가방",
    "Optical": "안경/옵티컬",
    "ElectronicsComputers": "컴퓨터/전자제품",
    "Televisions": "TV",
    "204cm-TV": "204cm TV",
    "178-203cm-TV": "178-203cm TV",
    "Apple": "애플",
    "MonitorsPrinters": "모니터/프린터",
    "Monitors": "모니터",
    "AudioVideo": "오디오/비디오",
    "AudioSpeakers": "오디오/스피커",
    "Mobile": "모바일",
    "Computer-Accessories": "컴퓨터 액세서리",
    "KeyboardsComputer-Mice": "키보드/마우스",
    "Musical-Instruments": "악기",
    "Game": "게임",
    "Cameras": "카메라",
    "Security-Cameras": "보안카메라",
    "LaptopsDesktops": "노트북/데스크탑",
    "Tablets": "태블릿",
    "BeautyHouseholdPersonal-Care": "뷰티/생활/개인용품",
    "Beauty": "뷰티",
    "CleansingRemover": "클렌징/리무버",
    "LotionCream": "로션/크림",
    "EssenceSerumAmpoule": "에센스/세럼/앰플",
    "PackMask": "팩/마스크",
    "BathBodyOral-Care": "욕실/바디/구강용품",
    "Oral-Care": "구강용품",
    "Body-Wash": "바디워시",
    "Hair-Care": "헤어케어",
    "ShampooConditioner": "샴푸/컨디셔너",
    "TreatmentDyeing": "트리트먼트/염색",
    "Feminine-HygieneIncontinence": "여성위생/요실금용품",
    "BathFacial-Tissue": "화장지/티슈",
    "Baby-BodyOral-Care": "유아 바디/구강용품",
    "BabyKidsToysPets": "유아동/완구/반려동물",
    "Pet-Supplies": "반려동물용품",
    "Dog-Foods": "강아지 사료",
    "Cat-Foods": "고양이 사료",
    "Toys": "완구",
    "Building-SetsBlocks": "블록/조립완구",
    "InfantKids-Care": "영유아 케어",
    "Playmat": "놀이매트",
    "Diapers": "기저귀",
    "Kids-ClothingAccessories": "아동 의류/잡화",
    "HomeKitchen": "홈/주방",
    "Dining": "다이닝",
    "Thermal": "보온/보냉용품",
    "Dinnerware": "식기",
    "BowlsPlates": "볼/접시",
    "CupMugWater-Bottle": "컵/머그/물병",
    "Kitchen-Accessories": "주방용품",
    "Kitchen-AccessoriesUtensils": "주방도구/용품",
    "Plastic-Wraps": "랩/호일",
    "Coffe-AccessoriesBakeware": "커피용품/베이킹웨어",
    "CutleryCutting-Board": "커트러리/도마",
    "Cookware": "조리도구",
    "Frying-Pan-Grill": "프라이팬/그릴",
    "Cleaning-Products": "청소용품",
    "Laundry-Detergent": "세탁세제",
    "Cleaning-Chemicals": "청소세제",
    "Bathroom-Organization": "욕실 정리용품",
    "HardwareAutomotive": "공구/자동차",
    "Automotive": "자동차용품",
    "Auto-Accessories": "자동차 액세서리",
    "WashWax": "세차/왁스",
    "StorageOrganization": "수납/정리",
    "Household-Storage": "생활수납",
    "Shelving": "선반",
    "Home-Improvement": "홈 인테리어/보수",
    "FlooringCeilingWallpaperDIYs": "바닥/천장/벽지/DIY",
    "Power-ToolsWork-Equipment": "전동공구/작업장비",
    "Work-ToolsSafety-Supplies": "작업공구/안전용품",
    "Security": "보안",
    "Safes": "금고",
    "Batteries": "배터리",
    "LightbulbsOutdoor-Lighting": "전구/야외조명",
    "TiresAutomotive": "타이어/자동차",
    "Tires": "타이어",
    "Event-Tires": "행사 타이어",
    "PatioLawnGarden": "정원/야외",
    "Garden-ToolsEquipment": "정원 공구/장비",
    "HoseAccessories": "호스/액세서리",
    "Patio-Furniture": "야외가구",
    "TablesChair": "테이블/의자",
    "Flower-BouquetsLive-Plants": "꽃다발/생화식물",
    "Live-Plants": "생화식물",
    "GardeningDecor": "정원 장식",
    "Outdoor-Storage": "야외 수납",
    "Outdoor-Structures": "야외 구조물",
    "ParasolsShade-Sails": "파라솔/그늘막",
    "Outdoor-Power-Equipment": "야외 전동장비",
    "SportsFitnessCamping": "스포츠/피트니스/캠핑",
    "Golf": "골프",
    "Golf-Accessories": "골프 액세서리",
    "Camping": "캠핑",
    "BoatingWater-Sports": "보트/수상스포츠",
    "HikingTrekking": "하이킹/트레킹",
    "FitnessExercise": "피트니스/운동",
    "BikesScootersRide-Ons": "자전거/스쿠터/승용완구",
    "Outdoor-Sports": "야외스포츠",
    "StationeryOffice-Supplies": "문구/사무용품",
    "WritingStationeries": "필기/문구",
    "SketchbooksNotebooks": "스케치북/노트",
    "Pens": "펜",
    "Office-Supplies": "사무용품",
    "Storage-Solutions": "수납 솔루션",
    "Machines": "사무기기",
    "Office-Papers": "사무용지",
    "HealthSupplement": "건강/영양제",
    "Other-Health-Supplement": "기타 건강보조식품",
    "Other-Health-Supplements": "기타 건강보조식품",
    "Home-Health-CareFirst-Aid": "가정 건강관리/응급처치",
    "Home-Health-Care": "가정 건강관리",
    "VitaminMineral": "비타민/미네랄",
    "Health": "건강",
    "Probiotics": "유산균",
    "DietBeauty-Supplement": "다이어트/뷰티 영양제",
    "Omega-3Krill-Oil": "오메가3/크릴오일",
    "Kids-Supplement": "어린이 영양제",
    "Joint": "관절",
    "JewelryWatchesAccessories": "주얼리/시계/잡화",
    "Necklaces": "목걸이",
    "Gold-Necklaces": "골드 목걸이",
    "Rings": "반지",
    "Gold-Rings": "골드 반지",
    "Diamond-Rings": "다이아몬드 반지",
    "Bracelets": "팔찌",
    "Gold-Bracelets": "골드 팔찌",
    "Earrings": "귀걸이",
    "24K-Gold-Silver": "24K 골드/실버",
    "Fashion-Jewelry": "패션 주얼리",
    "Womens-Watches": "여성 시계",
    "One-of-a-Kind-Jewelry": "원오브어카인드 주얼리",
    "Gift-Cards-Tickets": "상품권/티켓",
    "Gift-Cards": "상품권",
    "Tickets": "티켓",
    "GrillsAccessories": "그릴/액세서리",
    "Charcoal-Grill": "숯불 그릴",
    "GasElectric-Grill": "가스/전기 그릴",
    "Grill-Accessories": "그릴 액세서리",
}

COSTCO_CATEGORY_TOKEN_LABELS = {
    "accessories": "액세서리",
    "activewear": "액티브웨어",
    "aid": "응급처치",
    "air": "공기",
    "apple": "애플",
    "appliances": "가전",
    "audio": "오디오",
    "auto": "자동차",
    "automotive": "자동차",
    "baby": "유아",
    "bags": "가방",
    "bath": "욕실",
    "batteries": "배터리",
    "beauty": "뷰티",
    "bedding": "침구",
    "beverages": "음료",
    "bikes": "자전거",
    "blankets": "담요",
    "blouse": "블라우스",
    "body": "바디",
    "camping": "캠핑",
    "care": "케어",
    "casual": "캐주얼",
    "cat": "고양이",
    "chairs": "의자",
    "chilled": "냉장",
    "cleaning": "청소",
    "clothing": "의류",
    "coffee": "커피",
    "computer": "컴퓨터",
    "computers": "컴퓨터",
    "cookware": "조리도구",
    "dining": "다이닝",
    "dog": "강아지",
    "dress": "원피스",
    "drink": "음료",
    "electronics": "전자제품",
    "equipment": "장비",
    "fashion": "패션",
    "fitness": "피트니스",
    "food": "식품",
    "foods": "식품",
    "for": "",
    "frozen": "냉동",
    "furniture": "가구",
    "garden": "정원",
    "gift": "선물",
    "gold": "골드",
    "golf": "골프",
    "grill": "그릴",
    "hardware": "공구",
    "health": "건강",
    "home": "홈",
    "household": "생활",
    "infant": "영유아",
    "jewelry": "주얼리",
    "kids": "아동",
    "kitchen": "주방",
    "lawn": "잔디",
    "men": "남성",
    "mobile": "모바일",
    "office": "사무",
    "oral": "구강",
    "outdoor": "야외",
    "pants": "바지",
    "patio": "파티오",
    "pet": "반려동물",
    "pets": "반려동물",
    "personal": "개인",
    "power": "전동",
    "processed": "가공",
    "room": "룸",
    "seasonal": "계절",
    "security": "보안",
    "shoes": "신발",
    "sports": "스포츠",
    "storage": "수납",
    "supplement": "영양제",
    "supplies": "용품",
    "tea": "차",
    "tires": "타이어",
    "tools": "공구",
    "toys": "완구",
    "video": "비디오",
    "watches": "시계",
    "women": "여성",
    "womens": "여성",
    "work": "작업",
}


def _costco_slug_to_korean_label(slug: str) -> str:
    if slug in COSTCO_CATEGORY_LABELS:
        return COSTCO_CATEGORY_LABELS[slug]
    label = slug.replace("-", " ").replace("_", " ").replace("+", " ")
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
    translated_parts = []
    for token in re.split(r"[^0-9A-Za-z]+", label):
        if not token:
            continue
        if token.isdigit():
            translated_parts.append(token)
            continue
        translated = COSTCO_CATEGORY_TOKEN_LABELS.get(token.lower())
        if translated:
            translated_parts.append(translated)
    return " ".join(translated_parts) if translated_parts else "기타"


def _costco_url_category_parts(url: str) -> List[str]:
    path = unquote(urlparse(url).path or "")
    parts = [part for part in path.split("/") if part]
    category_parts = []
    for part in parts:
        if part == "p":
            break
        category_parts.append(part)
    return category_parts[:-1] if len(category_parts) > 1 else []


def _costco_url_to_category_key(url: str) -> str:
    parts = _costco_url_category_parts(url)
    return parts[0] if parts else ""


def _costco_url_to_category_path(url: str) -> str:
    return "/".join(_costco_url_category_parts(url))


def _costco_url_to_category_text(url: str) -> str:
    return " > ".join(_costco_slug_to_korean_label(part) for part in _costco_url_category_parts(url) if part.strip())


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
                "category_key": _costco_url_to_category_key(url),
                "category_path": _costco_url_to_category_path(url),
                "category_text": _costco_url_to_category_text(url),
                "search_blob": _normalize_costco_text(search_blob),
                "search_compact": _compact_costco_text(search_blob),
            }
        )
        seen_urls.add(url)

    return entries


def _costco_category_sort_key(node: dict) -> Tuple[int, str]:
    root = (node.get("key") or "").split("/", 1)[0]
    root_index = COSTCO_CATEGORY_ROOT_ORDER.index(root) if root in COSTCO_CATEGORY_ROOT_ORDER else len(COSTCO_CATEGORY_ROOT_ORDER)
    return root_index, node.get("label") or ""


def _build_costco_category_tree(entries: List[dict]) -> List[dict]:
    root_nodes = {}

    for entry in entries:
        category_path = entry.get("category_path") or _costco_url_to_category_path(entry.get("url", ""))
        parts = category_path.split("/")
        parts = [part for part in parts if part]
        if not parts or parts[0] not in COSTCO_CATEGORY_ROOTS:
            continue

        siblings = root_nodes
        current_path = []
        for part in parts:
            current_path.append(part)
            key = "/".join(current_path)
            if key not in siblings:
                siblings[key] = {
                    "key": key,
                    "label": _costco_slug_to_korean_label(part),
                    "children": {},
                }
            siblings = siblings[key]["children"]

    def serialize(nodes: dict) -> List[dict]:
        serialized = []
        for node in nodes.values():
            serialized.append(
                {
                    "key": node["key"],
                    "label": node["label"],
                    "children": serialize(node["children"]),
                }
            )
        serialized.sort(key=_costco_category_sort_key)
        return serialized

    return serialize(root_nodes)


def _build_costco_category_tree_from_db(db: Session) -> Tuple[List[dict], int]:
    entries = []
    rows = (
        db.query(CostcoProduct.product_url, CostcoProduct.category_path, CostcoProduct.category_text)
        .filter(CostcoProduct.is_active.is_(True))
        .all()
    )

    for product_url, category_path, category_text in rows:
        path = (category_path or _costco_url_to_category_path(product_url or "")).strip("/")
        if not path:
            continue
        entries.append(
            {
                "url": product_url or "",
                "category_path": path,
                "category_text": category_text or "",
            }
        )

    return _build_costco_category_tree(entries), len(rows)


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
                "category_key": _costco_url_to_category_key(url),
                "category_path": _costco_url_to_category_path(url),
                "category_text": _costco_url_to_category_text(url),
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
        "category_key": _costco_url_to_category_key(final_url),
        "category_path": _costco_url_to_category_path(final_url),
        "category_text": _costco_url_to_category_text(final_url),
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
    absolute_product_url = urljoin("https://www.costco.co.kr", product_url)
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
        "url": absolute_product_url,
        "category_key": _costco_url_to_category_key(absolute_product_url),
        "category_path": _costco_url_to_category_path(absolute_product_url),
        "category_text": _costco_url_to_category_text(absolute_product_url),
        "image_url": image_url,
        "member_only": member_only,
        "source": "official-search",
    }


def _matches_costco_category(item: dict, category: str) -> bool:
    if not category:
        return True
    category_path = category.strip().strip("/")
    item_path = item.get("category_path") or ""
    if not item_path and item.get("url"):
        item_path = _costco_url_to_category_path(item["url"])
    item_path = (item_path or item.get("category_key") or "").strip().strip("/")
    return item_path == category_path or item_path.startswith(f"{category_path}/")


async def _search_costco_official_catalog(query: str, limit: int = 12, category: str = "") -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        response = await client.get(
            "https://www.costco.co.kr/rest/v2/korea/products/search",
            params={
                "query": query.strip(),
                "fields": "FULL",
                "currentPage": 0,
                "pageSize": max(limit * 4, limit) if category else limit,
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
        if item and _matches_costco_category(item, category):
            items.append(item)

    pagination = payload.get("pagination") or {}
    matched_count = pagination.get("totalResults")
    if category:
        matched_count = len(items)
    elif not isinstance(matched_count, int):
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
        "category_key": entry.get("category_key") or _costco_url_to_category_key(entry["url"]),
        "category_path": entry.get("category_path") or _costco_url_to_category_path(entry["url"]),
        "category_text": _costco_url_to_category_text(entry["url"]),
        "image_url": "",
        "member_only": False,
        "source": "sitemap",
    }


def _costco_product_to_search_item(product: CostcoProduct) -> dict:
    has_discount = bool(
        product.price is not None
        and product.original_price is not None
        and product.original_price > product.price
    )
    category_path = product.category_path or _costco_url_to_category_path(product.product_url)
    return {
        "id": product.id,
        "title": product.product_name,
        "price_text": product.price_text or (_format_costco_won(product.price) if product.price is not None else "가격 정보 없음"),
        "price_value": product.price,
        "original_price_text": product.original_price_text if has_discount else "",
        "original_price_value": product.original_price if has_discount else None,
        "discount_text": product.discount_text if has_discount else "",
        "discount_value": product.discount_amount if has_discount else None,
        "has_discount": has_discount,
        "discount_period_text": product.discount_period_text if has_discount else "",
        "url": product.product_url,
        "category_key": category_path.split("/", 1)[0] if category_path else "",
        "category_path": category_path,
        "category_text": product.category_text or _costco_url_to_category_text(product.product_url),
        "image_url": product.image_url or "",
        "member_only": bool(product.member_only),
        "source": "db-cache",
    }


def _upsert_costco_product_from_entry(db: Session, entry: dict, seen_at: datetime) -> CostcoProduct:
    product = db.get(CostcoProduct, entry["id"])
    if not product:
        product = CostcoProduct(id=entry["id"], product_name=entry["label"] or entry["id"], product_url=entry["url"])
    product.product_name = product.product_name or entry["label"] or entry["id"]
    product.product_url = entry["url"]
    product.category_path = entry.get("category_path") or _costco_url_to_category_path(entry["url"])
    product.category_text = entry.get("category_text") or _costco_url_to_category_text(entry["url"])
    product.is_active = True
    product.last_seen_at = seen_at
    db.add(product)
    return product


def _upsert_costco_product_from_item(db: Session, item: dict, synced_at: datetime) -> CostcoProduct:
    product = db.get(CostcoProduct, str(item["id"]))
    if not product:
        product = CostcoProduct(id=str(item["id"]), product_name=item["title"], product_url=item["url"])
    product.product_name = item["title"]
    product.product_url = item["url"]
    product.image_url = item.get("image_url") or None
    product.category_path = item.get("category_path") or _costco_url_to_category_path(item["url"])
    product.category_text = item.get("category_text") or _costco_url_to_category_text(item["url"])
    product.price = int(float(item["price_value"])) if item.get("price_value") is not None else None
    product.price_text = item.get("price_text") or None
    product.original_price = int(float(item["original_price_value"])) if item.get("original_price_value") is not None else None
    product.original_price_text = item.get("original_price_text") or None
    product.discount_amount = int(float(item["discount_value"])) if item.get("discount_value") is not None else None
    product.discount_text = item.get("discount_text") or None
    product.discount_period_text = item.get("discount_period_text") or None
    product.member_only = bool(item.get("member_only"))
    product.is_active = True
    product.last_seen_at = synced_at
    product.last_synced_at = synced_at
    db.add(product)
    return product


def _search_costco_products_db(db: Session, query: str, limit: int, category: str) -> Optional[dict]:
    active_query = db.query(CostcoProduct).filter(CostcoProduct.is_active.is_(True))
    total_count = active_query.count()
    if total_count == 0:
        return {
            "items": [],
            "matched_count": 0,
            "total_catalog_count": 0,
            "fetched_at": None,
            "mode": "db-cache-empty",
            "message": "코스트코 상품 DB를 동기화하는 중입니다. 잠시 후 다시 시도해보세요.",
        }

    filtered = active_query
    category_path = category.strip().strip("/")
    if category_path:
        filtered = filtered.filter(
            or_(
                CostcoProduct.category_path == category_path,
                CostcoProduct.category_path.like(f"{category_path}/%"),
            )
        )

    query_tokens = _tokenize_costco_text(query)
    for token in query_tokens:
        pattern = f"%{token}%"
        filtered = filtered.filter(
            or_(
                CostcoProduct.product_name.like(pattern),
                CostcoProduct.product_url.like(pattern),
                CostcoProduct.category_text.like(pattern),
                CostcoProduct.id.like(pattern),
            )
        )

    matched_count = filtered.count()
    products = (
        filtered.order_by(
            CostcoProduct.last_synced_at.desc(),
            CostcoProduct.updated_at.desc(),
            CostcoProduct.product_name.asc(),
        )
        .limit(limit)
        .all()
    )
    return {
        "items": [_costco_product_to_search_item(product) for product in products],
        "matched_count": matched_count,
        "total_catalog_count": total_count,
        "fetched_at": None,
        "mode": "db-cache",
        "message": "저장된 코스트코 상품 DB에서 검색했습니다."
        if matched_count
        else "저장된 코스트코 상품 DB에서 일치하는 상품이 없습니다.",
    }


async def _search_costco_shopping_catalog(query: str, limit: int = 12, refresh: bool = False, category: str = "") -> dict:
    entries = await _load_costco_shopping_sitemap(force_refresh=refresh)
    fetched_at = COSTCO_SHOPPING_SITEMAP_CACHE["fetched_at"]
    category_entries = [entry for entry in entries if _matches_costco_category(entry, category)] if category else entries

    if not query.strip() and not category:
        featured = await _load_costco_shopping_catalog(force_refresh=refresh)
        return {
            "items": featured[:limit],
            "matched_count": len(featured),
            "total_catalog_count": len(entries),
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
            "mode": "featured",
            "message": "공식몰 상품 목록을 불러왔습니다.",
        }

    if not query.strip() and category:
        candidates = category_entries[:limit]
        items = []
        if refresh:
            enriched_results = await asyncio.gather(
                *[_load_costco_product_details(entry["url"]) for entry in candidates],
                return_exceptions=True,
            )
        else:
            enriched_results = [
                COSTCO_SHOPPING_PRODUCT_CACHE.get(entry["url"], {}).get("item")
                for entry in candidates
            ]

        for entry, result in zip(candidates, enriched_results):
            if not result or isinstance(result, Exception):
                items.append(_fallback_costco_item(entry))
            else:
                items.append(result)

        return {
            "items": items,
            "matched_count": len(category_entries),
            "total_catalog_count": len(entries),
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
            "mode": "category",
            "message": "선택한 카테고리의 상품 후보를 불러왔습니다.",
        }

    try:
        payload = await _search_costco_official_catalog(query, limit=limit, category=category)
        if category and not payload.get("items"):
            raise ValueError("No official search items matched selected category.")
        payload["total_catalog_count"] = len(entries)
        payload["fetched_at"] = fetched_at.isoformat() if fetched_at else None
        return payload
    except Exception:
        scored = []
        for entry in category_entries:
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


@app.get("/api/shopping/categories")
async def shopping_categories(refresh: bool = False, db: Session = Depends(get_db)):
    try:
        if not refresh:
            items, count = _build_costco_category_tree_from_db(db)
            return {
                "items": items,
                "count": count,
                "fetched_at": None,
                "mode": "db-cache" if count else "db-cache-empty",
            }

        entries = await _load_costco_shopping_sitemap(force_refresh=refresh)
        fetched_at = COSTCO_SHOPPING_SITEMAP_CACHE["fetched_at"]
        return {
            "items": _build_costco_category_tree(entries),
            "count": len(entries),
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
            "mode": "sitemap",
        }
    except Exception:
        return {
            "items": [],
            "count": 0,
            "fetched_at": None,
            "mode": "error",
        }


async def _sync_costco_products_sitemap_db(db: Session, refresh: bool = False) -> dict:
    entries = await _load_costco_shopping_sitemap(force_refresh=refresh)
    seen_at = datetime.now(timezone.utc)
    for index, entry in enumerate(entries, start=1):
        _upsert_costco_product_from_entry(db, entry, seen_at)
        if index % 500 == 0:
            db.commit()
            await asyncio.sleep(0)
    db.commit()
    return {
        "total": len(entries),
        "synced_at": seen_at.isoformat(),
    }


async def _sync_costco_products_details_db(db: Session, limit: int = 20, refresh: bool = False) -> dict:
    safe_limit = max(1, min(limit, 100))
    products = (
        db.query(CostcoProduct.id, CostcoProduct.product_url)
        .filter(CostcoProduct.is_active.is_(True))
        .order_by(CostcoProduct.last_synced_at.asc(), CostcoProduct.updated_at.asc())
        .limit(safe_limit)
        .all()
    )
    db.commit()
    synced_at = datetime.now(timezone.utc)
    synced = 0
    failed = 0
    for product_id, product_url in products:
        item = await _load_costco_product_details(product_url, force_refresh=refresh)
        if not item:
            failed += 1
            continue
        _upsert_costco_product_from_item(db, item, synced_at)
        synced += 1
        if synced % 10 == 0:
            db.commit()
        await asyncio.sleep(0.15)
    db.commit()
    return {
        "requested": safe_limit,
        "synced": synced,
        "failed": failed,
        "synced_at": synced_at.isoformat(),
    }


async def _costco_products_auto_sync_loop():
    await asyncio.sleep(COSTCO_PRODUCTS_AUTO_SYNC_START_DELAY_SECONDS)
    while True:
        db = SessionLocal()
        try:
            total_count = db.query(CostcoProduct).count()
            latest_seen_at = db.query(func.max(CostcoProduct.last_seen_at)).scalar()
            now = datetime.now(timezone.utc)
            latest_seen_at_utc = (
                latest_seen_at.astimezone(timezone.utc)
                if latest_seen_at and latest_seen_at.tzinfo
                else latest_seen_at.replace(tzinfo=timezone.utc)
                if latest_seen_at
                else None
            )
            should_sync_sitemap = (
                total_count == 0
                or latest_seen_at is None
                or now - latest_seen_at_utc > timedelta(seconds=COSTCO_PRODUCTS_SITEMAP_SYNC_INTERVAL_SECONDS)
            )
            if should_sync_sitemap:
                await _sync_costco_products_sitemap_db(db, refresh=total_count == 0)

            await _sync_costco_products_details_db(
                db,
                limit=COSTCO_PRODUCTS_AUTO_SYNC_BATCH_SIZE,
                refresh=False,
            )
        except asyncio.CancelledError:
            db.close()
            raise
        except Exception:
            db.rollback()
        finally:
            db.close()

        await asyncio.sleep(COSTCO_PRODUCTS_AUTO_SYNC_INTERVAL_SECONDS)


@app.get("/api/shopping/products/status")
def shopping_products_status(db: Session = Depends(get_db)):
    total_count = db.query(CostcoProduct).count()
    active_count = db.query(CostcoProduct).filter(CostcoProduct.is_active.is_(True)).count()
    synced_count = db.query(CostcoProduct).filter(CostcoProduct.last_synced_at.isnot(None)).count()
    latest_synced_at = db.query(func.max(CostcoProduct.last_synced_at)).scalar()
    latest_seen_at = db.query(func.max(CostcoProduct.last_seen_at)).scalar()
    return {
        "total_count": total_count,
        "active_count": active_count,
        "synced_count": synced_count,
        "latest_synced_at": latest_synced_at.isoformat() if latest_synced_at else None,
        "latest_seen_at": latest_seen_at.isoformat() if latest_seen_at else None,
    }


@app.post("/api/shopping/products/sync-sitemap")
async def sync_costco_products_sitemap(refresh: bool = False, db: Session = Depends(get_db)):
    result = await _sync_costco_products_sitemap_db(db, refresh=refresh)
    return {
        "total": result["total"],
        "synced_at": result["synced_at"],
        "message": "코스트코 sitemap 상품 URL을 DB에 저장했습니다.",
    }


@app.post("/api/shopping/products/sync-details")
async def sync_costco_products_details(limit: int = 20, refresh: bool = False, db: Session = Depends(get_db)):
    result = await _sync_costco_products_details_db(db, limit=limit, refresh=refresh)
    return {
        "requested": result["requested"],
        "synced": result["synced"],
        "failed": result["failed"],
        "synced_at": result["synced_at"],
        "message": "코스트코 상품 상세 정보를 DB에 갱신했습니다.",
    }


@app.get("/api/shopping/search")
async def shopping_search(
    q: str = "",
    limit: int = 12,
    refresh: bool = False,
    category: str = "",
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(limit, 24))
    try:
        if not refresh:
            db_payload = _search_costco_products_db(db, q, safe_limit, category.strip())
            if db_payload is not None:
                return {
                    "items": db_payload["items"],
                    "count": len(db_payload["items"]),
                    "total_catalog_count": db_payload["total_catalog_count"],
                    "matched_count": db_payload["matched_count"],
                    "fetched_at": db_payload["fetched_at"],
                    "message": db_payload["message"],
                    "mode": db_payload["mode"],
                    "query": q,
                }

        payload = await _search_costco_shopping_catalog(q, limit=safe_limit, refresh=refresh, category=category.strip())
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
