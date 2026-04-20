"""
/api/orders — 수동 주문 실행
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from kis import rest_client as kis

router = APIRouter(prefix="/api/orders", tags=["orders"])


class OrderRequest(BaseModel):
    stock_code: str
    quantity:   int
    price:      int = 0   # 0 = 시장가


@router.post("/buy")
def manual_buy(body: OrderRequest):
    try:
        result = kis.place_order(body.stock_code, "BUY", body.quantity, body.price)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/sell")
def manual_sell(body: OrderRequest):
    try:
        result = kis.place_order(body.stock_code, "SELL", body.quantity, body.price)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/{order_no}")
def cancel_order(order_no: str, stock_code: str, quantity: int):
    try:
        result = kis.cancel_order(order_no, stock_code, quantity)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))
