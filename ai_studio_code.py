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
    product = relationship("Product", back_populates="deals")