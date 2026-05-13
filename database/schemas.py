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
    description: Optional[str] = None
    ingredients: Optional[str] = None
    allergens: Optional[str] = None
    size_guide: Optional[str] = None
    advisory_notes: Optional[str] = None

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


class ProductPatch(BaseModel):
    """Kısmi ürün güncellemesi (tablo üzerinden düzenleme)."""
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock_quantity: Optional[int] = None
    low_stock_threshold: Optional[int] = None
    description: Optional[str] = None
    ingredients: Optional[str] = None
    allergens: Optional[str] = None
    size_guide: Optional[str] = None
    advisory_notes: Optional[str] = None

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


class OrderItemInput(BaseModel):
    product_id: int
    quantity: int


class OrderPatch(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None  # SQLite yerel: YYYY-MM-DD HH:MM:SS veya datetime-local T ile
    items: Optional[List[OrderItemInput]] = None


class CargoShipmentCreate(BaseModel):
    """Kargoda yeni sipariş + takip (tenant JWT). Ürün kalemi isteğe bağlı."""
    customer_name: str
    customer_phone: Optional[str] = None
    notes: Optional[str] = None
    cargo_tracking_code: str
    cargo_company: str
    items: Optional[List[OrderItemInput]] = None
    estimated_delivery: Optional[str] = None
    last_update: Optional[str] = None


class CargoShipmentPatch(BaseModel):
    """Kargodaki sipariş ve isteğe bağlı cargo_tracking alanları."""
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    cargo_tracking_code: Optional[str] = None
    cargo_company: Optional[str] = None
    cargo_status: Optional[str] = None
    estimated_delivery: Optional[str] = None
    last_update: Optional[str] = None

#  ÖZET

class DailySummary(BaseModel):
    date: str
    total_orders: int
    by_status: dict
    total_revenue: float
    low_stock_products: List[dict]
    pending_shipments: int

#  BİLET

class TicketCreate(BaseModel):
    type: str                       # cargo_delay | stock_alert | cancellation_request | telegram_order_request | ...
    title: str
    description: Optional[str] = None
    priority: str = "normal"        # low | normal | high | critical
    llm_content: Optional[str] = None
    related_order_id: Optional[int] = None
    related_product_id: Optional[int] = None

class TicketStatusUpdate(BaseModel):
    status: str                     # open | in_progress | resolved
    resolution: Optional[str] = None  # approve|reject (telegram_order_request); approve_cancel (cancellation_request)

class TicketResponse(BaseModel):
    id: int
    type: str
    priority: str
    status: str
    title: str
    description: Optional[str]
    llm_content: Optional[str]
    related_order_id: Optional[int]
    related_product_id: Optional[int]
    created_at: str
    resolved_at: Optional[str]

#  GÜNLÜK RAPOR

class ReportResponse(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    date: str
    report_text: str
    raw_data: Optional[str] = None
    briefing_json: Optional[str] = None
    model_version: Optional[str] = None
    source: Optional[str] = None
    created_at: str
