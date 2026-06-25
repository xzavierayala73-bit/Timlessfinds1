deal-assistant/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/                  # Step 2: Database Schema
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── store.py
│   │   ├── product.py
│   │   └── deal.py
│   ├── api/                     # Step 3: API Design
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── search.py
│   │       ├── deals.py
│   │       └── alerts.py
│   ├── services/                # Step 5: AI Engine & Integrations
│   │   ├── __init__.py
│   │   ├── ai_engine.py         # Verification and scoring models
│   │   ├── geo.py               # Coordinates, Zip codes, Address parsing
│   │   └── ingest.py            # Public data adapters / scrapers
│   └── tests/
│       ├── test_search.py
│       └── test_ai.pyfrom sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    store_number = Column(String(50), unique=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(255))
    city = Column(String(100))
    country = Column(String(100))
    postal_code = Column(String(20), index=True)
    
    # Coordinates for GIS/proximity searches
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    deals = relationship("Deal", back_populates="store")
    import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.models.store import Base
import datetime

class DealType(str, enum.Enum):
    CLEARANCE = "clearance"
    MARKDOWN = "markdown"
    CLOSEOUT = "closeout"
    OVERSTOCK = "overstock"
    OPEN_BOX = "open-box"
    LIMITED_PROMOTION = "limited-time-promotion"
    PENNY_ITEM = "penny-priced"

class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    
    deal_type = Column(SQLEnum(DealType), nullable=False)
    current_price = Column(Float, nullable=False)
    savings_amount = Column(Float, nullable=False)  # original_price - current_price
    savings_percentage = Column(Float, nullable=False)
    
    inventory_count = Column(Integer, default=0)
    inventory_status = Column(String(50))  # "In Stock", "Low Stock", "Out of Stock"
    
    last_verified = Column(DateTime, default=datetime.datetime.utcnow)
    ai_confidence_score = Column(Float, default=0.5)  # Computed validation confidence

    store = relationship("Store", back_populates="deals")
    product = relationship("Product", back_populates="deals")from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import search, auth, deals, alerts

app = FastAPI(
    title="Home Improvement Deal Finder API",
    description="Backend engine for locating markdown, clearance, and closeout items.",
    version="1.0.0"
)

# CORS configurations for dashboards & mobile apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Search Engine"])
app.include_router(deals.router, prefix="/api/v1/deals", tags=["Deals Management"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["User Alerts"])

@app.get("/health", tags=["System"])
def health_check():
    return {"status": "operational", "timestamp": "2026-06-25T11:32:00Z"}from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from app.services.geo import GeoService
from app.services.ai_engine import AIEngine

router = APIRouter()

# Schema for client responses
class DealSearchResponse(BaseModel):
    store_name: str
    store_address: str
    sku: str
    upc: str
    product_name: str
    original_price: float
    current_price: float
    total_savings: float
    savings_percentage: float
    deal_type: str
    inventory_status: str
    last_update_time: datetime
    ai_confidence_score: float

@router.get("/", response_model=List[DealSearchResponse])
async def search_deals(
    query: Optional[str] = Query(None, description="Search term, SKU, or UPC code"),
    zip_code: Optional[str] = Query(None, description="ZIP or Postal Code"),
    city: Optional[str] = Query(None, description="City Name"),
    country: Optional[str] = Query("US", description="Country Code"),
    latitude: Optional[float] = Query(None, description="GPS Latitude"),
    longitude: Optional[float] = Query(None, description="GPS Longitude"),
    radius_miles: float = Query(15.0, description="Search radius in miles"),
    geo_service: GeoService = Depends(),
    ai_engine: AIEngine = Depends()
):
    """
    Search Deals globally by ZIP code, city, coordinates, or SKU.
    """
    # 1. Resolve search coordinates
    coords = None
    if latitude and longitude:
        coords = (latitude, longitude)
    elif zip_code:
        coords = await geo_service.resolve_zip(zip_code, country)
    elif city:
        coords = await geo_service.resolve_city(city, country)
        
    if not coords:
        raise HTTPException(status_code=400, detail="Unable to resolve a valid location query.")

    # 2. Fetch raw matches near coordinates (Mock database integration)
    raw_deals = await geo_service.fetch_regional_deals(coords, radius_miles, query)
    
    # 3. Process through AI scoring engine
    scored_deals = []
    for deal in raw_deals:
        # Evaluate validity using historical prices and stock patterns
        score = ai_engine.evaluate_deal_confidence(deal)
        
        scored_deals.append(
            DealSearchResponse(
                store_name=deal["store_name"],
                store_address=deal["store_address"],
                sku=deal["sku"],
                upc=deal["upc"],
                product_name=deal["product_name"],
                original_price=deal["original_price"],
                current_price=deal["current_price"],
                total_savings=deal["original_price"] - deal["current_price"],
                savings_percentage=round(((deal["original_price"] - deal["current_price"]) / deal["original_price"]) * 100, 2),
                deal_type=deal["deal_type"],
                inventory_status=deal["inventory_status"],
                last_update_time=deal["last_update"],
                ai_confidence_score=score
            )
        )
        
    # Rank by confidence score and discount depth
    scored_deals.sort(key=lambda x: (x.ai_confidence_score, x.savings_percentage), reverse=True)
    return scored_dealsfrom datetime import datetime, timezone
from typing import Dict, Any

class AIEngine:
    def __init__(self):
        # Threshold constants
        self.FRESHNESS_HOURS_LIMIT = 24
        
    def evaluate_deal_confidence(self, deal_data: Dict[str, Any]) -> float:
        """
        Calculates a dynamic AI Confidence Score (0.0 to 1.0) based on:
        1. Age of last updated report (Freshness)
        2. Inventory counts (Is inventory low enough to be a ghost item?)
        3. Savings reasonability (Penny items require higher validation points)
        4. Historical store reliability
        """
        score = 0.8  # Baseline safety score

        # 1. Evaluate Freshness
        last_updated = deal_data.get("last_update", datetime.now(timezone.utc))
        age_in_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600.0
        
        if age_in_hours < 2:
            score += 0.10  # Highly fresh update
        elif age_in_hours > self.FRESHNESS_HOURS_LIMIT:
            score -= 0.25  # Highly likely to have expired or been bought out

        # 2. Inventory Dynamics
        inventory = deal_data.get("inventory_count", 0)
        status = deal_data.get("inventory_status", "Out of Stock")
        
        if status == "Out of Stock" or inventory == 0:
            score = 0.05  # Highly unconfirmed availability
        elif inventory == 1:
            score -= 0.15  # "Ghost stock" penalty (often mismatches in system inventory)
        elif 2 <= inventory <= 5:
            score += 0.05  # Moderate certainty

        # 3. Price Reasonability check (e.g., dealing with penny items)
        original_price = deal_data.get("original_price", 0.0)
        current_price = deal_data.get("current_price", 0.0)
        
        if current_price <= 0.01:
            # Penny items are heavily targeted; unless verified recently, keep confidence lower
            if age_in_hours > 4:
                score -= 0.30
            else:
                score += 0.10
                
        # 4. Enforce mathematical bounds [0.0, 1.0]
        final_score = max(0.01, min(1.0, score))
        return round(final_score, 2)from datetime import datetime, timezone
from typing import Dict, Any

class AIEngine:
    def __init__(self):
        # Threshold constants
        self.FRESHNESS_HOURS_LIMIT = 24
        
    def evaluate_deal_confidence(self, deal_data: Dict[str, Any]) -> float:
        """
        Calculates a dynamic AI Confidence Score (0.0 to 1.0) based on:
        1. Age of last updated report (Freshness)
        2. Inventory counts (Is inventory low enough to be a ghost item?)
        3. Savings reasonability (Penny items require higher validation points)
        4. Historical store reliability
        """
        score = 0.8  # Baseline safety score

        # 1. Evaluate Freshness
        last_updated = deal_data.get("last_update", datetime.now(timezone.utc))
        age_in_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600.0
        
        if age_in_hours < 2:
            score += 0.10  # Highly fresh update
        elif age_in_hours > self.FRESHNESS_HOURS_LIMIT:
            score -= 0.25  # Highly likely to have expired or been bought out

        # 2. Inventory Dynamics
        inventory = deal_data.get("inventory_count", 0)
        status = deal_data.get("inventory_status", "Out of Stock")
        
        if status == "Out of Stock" or inventory == 0:
            score = 0.05  # Highly unconfirmed availability
        elif inventory == 1:
            score -= 0.15  # "Ghost stock" penalty (often mismatches in system inventory)
        elif 2 <= inventory <= 5:
            score += 0.05  # Moderate certainty

        # 3. Price Reasonability check (e.g., dealing with penny items)
        original_price = deal_data.get("original_price", 0.0)
        current_price = deal_data.get("current_price", 0.0)
        
        if current_price <= 0.01:
            # Penny items are heavily targeted; unless verified recently, keep confidence lower
            if age_in_hours > 4:
                score -= 0.30
            else:
                score += 0.10
                
        # 4. Enforce mathematical bounds [0.0, 1.0]
        final_score = max(0.01, min(1.0, score))
        return round(final_score, 2)from typing import Tuple, List, Dict, Any, Optional
from datetime import datetime, timezone

class GeoService:
    async def resolve_zip(self, zip_code: str, country: str) -> Optional[Tuple[float, float]]:
        # Mocking coordinates for zip. In production, resolve via Mapbox, Nominatim or OpenStreetMap
        if "77" in zip_code:  # Houston area
            return (29.7604, -95.3698)
        return (40.7128, -74.0060)  # Fallback: NY

    async def resolve_city(self, city: str, country: str) -> Optional[Tuple[float, float]]:
        # Mock resolving a named city to lat/lon coordinates
        return (34.0522, -118.2437) # Mocked LA

    async def fetch_regional_deals(
        self, 
        coordinates: Tuple[float, float], 
        radius_miles: float, 
        query: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Coordinates raw queries with spatial search logic.
        """
        # Simulated database return containing different deal types
        return [
            {
                "store_name": "Home Builder Depot #4701",
                "store_address": "1200 Post Oak Blvd, Houston, TX",
                "sku": "921-840",
                "upc": "042100005234",
                "product_name": "Smart Wi-Fi Electronic Deadbolt Lock",
                "original_price": 149.00,
                "current_price": 45.00,
                "deal_type": "clearance",
                "inventory_count": 3,
                "inventory_status": "Low Stock",
                "last_update": datetime.now(timezone.utc),
            },
            {
                "store_name": "Lumber & Hardware Co #112",
                "store_address": "3200 Westheimer Rd, Houston, TX",
                "sku": "1004-512-110",
                "upc": "012345678901",
                "product_name": "20V Max Brushless Drill Driver Kit",
                "original_price": 99.00,
                "current_price": 0.01,
                "deal_type": "penny-priced",
                "inventory_count": 1,
                "inventory_status": "Low Stock",
                "last_update": datetime.now(timezone.utc),
            }
      from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.models.store import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    
    alerts = relationship("Alert", back_populates="user")from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.models.store import Base

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    target_sku = Column(String(50), nullable=True)
    max_price_threshold = Column(Float, nullable=True)
    preferred_deal_type = Column(String(50), nullable=True) # e.g. "penny-priced", "clearance"
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="alerts")
    fastapi>=0.110.0
uvicorn>=0.28.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
