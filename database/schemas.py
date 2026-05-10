from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

#  ÜRÜN 

class ProductBase(BaseModel):
    name: str
    category: Optional[str] = None
    price: float
    stock_quantity: int
    low_stock_threshold: int = 10

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    is_active: bool
    is_low_stock: bool          # hesaplanmış alan
    created_at: str

class StockUpdateRequest(BaseModel):
    quantity_change: int        # pozitif = ekle, negatif = azalt
    reason: Optional[str] = None

#  SİPARİŞ 

class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    subtotal: float

class OrderResponse(BaseModel):
    id: int
    customer_name: str
    customer_phone: Optional[str]
    status: str
    cargo_tracking_code: Optional[str]
    cargo_company: Optional[str]
    total_price: Optional[float]
    notes: Optional[str]
    items: List[OrderItemResponse]
    created_at: str
    updated_at: str

class OrderStatusUpdate(BaseModel):
    status: str                 # hazırlanıyor | kargoda | teslim_edildi | iptal
    cargo_tracking_code: Optional[str] = None
    cargo_company: Optional[str] = None

class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    notes: Optional[str] = None
    items: List[dict]           # [{product_id, quantity}]

#  ÖZET 

class DailySummary(BaseModel):
    date: str
    total_orders: int
    by_status: dict
    total_revenue: float
    low_stock_products: List[dict]
    pending_shipments: int
