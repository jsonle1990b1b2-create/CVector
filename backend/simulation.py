from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass
from datetime import date as Date, datetime, time as Time, timedelta
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# --------- App and CORS ---------
app = FastAPI(title="Virtual Energy Trading API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------- Storage ---------
DATA_DIR = Path(__file__).resolve().parent
ORDERS_FILE = DATA_DIR / "orders.json"


def _read_orders_file() -> Dict[str, List[dict]]:
    if not ORDERS_FILE.exists():
        return {}
    try:
        with ORDERS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        return {}


def _write_orders_file(data: Dict[str, List[dict]]) -> None:
    tmp = ORDERS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(ORDERS_FILE)


# --------- Models ---------
Side = Literal["buy", "sell"]


class OrderIn(BaseModel):
    date: str = Field(..., description="Trading date YYYY-MM-DD (day-ahead delivery date)")
    hour: int = Field(..., ge=0, le=23, description="Hour ending in local time [0-23]")
    side: Side
    price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0, description="MWh")


class OrderOut(OrderIn):
    id: str
    created_at: str


class PnLItem(BaseModel):
    order_id: str
    date: str
    hour: int
    side: Side
    quantity: float
    bid_price: float
    day_ahead_price: float
    real_time_price: float
    filled: bool
    pnl: float


class PnLSummary(BaseModel):
    date: str
    currency: str = "USD"
    total_pnl: float
    details: List[PnLItem]


# --------- Utilities ---------
def _now_local() -> datetime:
    # Naive local time per system clock
    return datetime.now()


def _parse_date_yyyy_mm_dd(value: str) -> Date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD")


def _submission_deadline_for_date(trade_date: Date) -> datetime:
    # Simplified: bids must be submitted before 11:00 local on the day before the trade_date
    day_before = trade_date - timedelta(days=1)
    return datetime.combine(day_before, Time(hour=11, minute=0))


def _require_before_deadline(trade_date: Date) -> None:
    deadline = _submission_deadline_for_date(trade_date)
    if _now_local() >= deadline:
        raise HTTPException(
            status_code=400,
            detail=f"Submission closed for {trade_date.isoformat()}. Deadline was {deadline.strftime('%Y-%m-%d %H:%M')} local.",
        )


def _seed_with_date(seed_date: Date) -> random.Random:
    # Deterministic seed from date to make synthetic prices stable across runs
    return random.Random(int(seed_date.strftime("%Y%m%d")))


def _generate_day_ahead_prices_synthetic(trade_date: Date) -> List[Dict[str, float]]:
    rng = _seed_with_date(trade_date)
    base = 45.0
    peak_add = 30.0
    noise_amp = 3.0
    prices = []
    for h in range(24):
        # Simple load-shaped price curve: off-peak low, morning ramp, evening peak
        # Use two humps across the day
        morning_factor = max(0.0, (h - 6) * (12 - h)) / 18.0  # peaks ~9-10
        evening_factor = max(0.0, (h - 14) * (22 - h)) / 16.0  # peaks ~18-19
        shape = morning_factor + evening_factor
        price = base + peak_add * shape + rng.uniform(-noise_amp, noise_amp)
        prices.append({"hour": h, "price": round(max(5.0, price), 2)})
    return prices


def _generate_real_time_prices_synthetic(trade_date: Date, da_prices: List[Dict[str, float]]) -> List[Dict[str, float]]:
    rng = _seed_with_date(trade_date + timedelta(days=7))  # different seed for RT
    prices = []
    for item in da_prices:
        base = item["price"]
        # Real-time deviates from DA around +/- $5-$10 typically
        rt = base + rng.uniform(-7.0, 7.0)
        prices.append({"hour": item["hour"], "price": round(max(0.0, rt), 2)})
    return prices


def _try_fetch_external_prices(_: Date) -> Optional[List[Dict[str, float]]]:
    """Placeholder for integrating a real API like GridStatus.io.

    To enable, set GRIDSTATUS_DAY_AHEAD_URL env var to a full endpoint that returns
    a JSON array of objects: [{"hour": 0-23, "price": number}, ...]. If unset or fails,
    return None so the caller can fall back to synthetic prices.
    """
    import requests  # local import to keep module import light

    url = os.environ.get("GRIDSTATUS_DAY_AHEAD_URL")
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and all("hour" in x and "price" in x for x in data):
            # Basic validation
            return [
                {"hour": int(x["hour"]), "price": float(x["price"])}
                for x in data
                if 0 <= int(x["hour"]) <= 23
            ]
        return None
    except Exception:
        return None


# --------- Endpoints ---------


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/prices/day-ahead")
def get_day_ahead_prices(date: str) -> Dict[str, object]:
    trade_date = _parse_date_yyyy_mm_dd(date)
    external = _try_fetch_external_prices(trade_date)
    if external is not None and len(external) == 24:
        source = "external"
        series = external
    else:
        source = "synthetic"
        series = _generate_day_ahead_prices_synthetic(trade_date)
    return {"date": trade_date.isoformat(), "source": source, "series": series}


@app.get("/api/prices/real-time")
def get_real_time_prices(date: str) -> Dict[str, object]:
    trade_date = _parse_date_yyyy_mm_dd(date)
    da = _generate_day_ahead_prices_synthetic(trade_date)
    rt = _generate_real_time_prices_synthetic(trade_date, da)
    return {"date": trade_date.isoformat(), "source": "synthetic", "series": rt}


@app.get("/api/orders")
def list_orders(date: str) -> Dict[str, object]:
    trade_date = _parse_date_yyyy_mm_dd(date)
    all_orders = _read_orders_file()
    orders = all_orders.get(trade_date.isoformat(), [])
    return {"date": trade_date.isoformat(), "orders": orders}


@app.post("/api/orders", status_code=201)
def create_order(order: OrderIn) -> OrderOut:
    trade_date = _parse_date_yyyy_mm_dd(order.date)
    _require_before_deadline(trade_date)

    all_orders = _read_orders_file()
    day_key = trade_date.isoformat()
    day_orders = all_orders.get(day_key, [])

    # Enforce per-hour limit: up to 10 bids per hour timeslot
    count_this_hour = sum(1 for o in day_orders if int(o.get("hour")) == order.hour)
    if count_this_hour >= 10:
        raise HTTPException(status_code=400, detail=f"Hour {order.hour}: bid limit reached (10)")

    oid = f"{int(_now_local().timestamp()*1000)}-{random.randint(1000,9999)}"
    created = _now_local().isoformat(timespec="seconds")
    record = {
        "id": oid,
        "date": day_key,
        "hour": order.hour,
        "side": order.side,
        "price": float(order.price),
        "quantity": float(order.quantity),
        "created_at": created,
    }

    day_orders.append(record)
    all_orders[day_key] = day_orders
    _write_orders_file(all_orders)

    return OrderOut(**record)


@app.delete("/api/orders/{order_id}")
def delete_order(order_id: str, date: str) -> Dict[str, str]:
    trade_date = _parse_date_yyyy_mm_dd(date)
    _require_before_deadline(trade_date)

    all_orders = _read_orders_file()
    day_key = trade_date.isoformat()
    day_orders = all_orders.get(day_key, [])
    new_orders = [o for o in day_orders if o.get("id") != order_id]
    if len(new_orders) == len(day_orders):
        raise HTTPException(status_code=404, detail="Order not found")
    all_orders[day_key] = new_orders
    _write_orders_file(all_orders)
    return {"status": "deleted"}


@app.get("/api/pnl")
def get_pnl(date: str) -> PnLSummary:
    trade_date = _parse_date_yyyy_mm_dd(date)
    all_orders = _read_orders_file()
    day_key = trade_date.isoformat()
    orders = all_orders.get(day_key, [])

    # Prices
    da_series = _generate_day_ahead_prices_synthetic(trade_date)
    rt_series = _generate_real_time_prices_synthetic(trade_date, da_series)
    da_by_hour = {x["hour"]: x["price"] for x in da_series}
    rt_by_hour = {x["hour"]: x["price"] for x in rt_series}

    details: List[PnLItem] = []
    total = 0.0
    for o in orders:
        hour = int(o["hour"])  # type: ignore[index]
        side: Side = o["side"]  # type: ignore[index]
        qty = float(o["quantity"])  # type: ignore[index]
        bid_price = float(o["price"])  # type: ignore[index]
        da_price = float(da_by_hour.get(hour, 0.0))
        rt_price = float(rt_by_hour.get(hour, da_price))

        # Fill rule: small player, fills if bid crosses/matches DA clearing price
        if side == "buy":
            filled = bid_price >= da_price
            signed_qty = qty
        else:  # sell
            filled = bid_price <= da_price
            signed_qty = -qty

        pnl = signed_qty * (rt_price - da_price) if filled else 0.0
        total += pnl

        details.append(
            PnLItem(
                order_id=o["id"],
                date=day_key,
                hour=hour,
                side=side,
                quantity=qty,
                bid_price=bid_price,
                day_ahead_price=da_price,
                real_time_price=rt_price,
                filled=bool(filled),
                pnl=round(pnl, 2),
            )
        )

    return PnLSummary(date=day_key, total_pnl=round(total, 2), details=details)


# Convenience: run with `uvicorn backend.simulation:app --reload`

if __name__ == "__main__":
    # Allows: `python simulation.py` (use the project's venv python)
    try:
        import uvicorn  # type: ignore
    except Exception as exc:
        raise SystemExit(
            "Uvicorn is not installed in this interpreter. Use ./venv/bin/python or install uvicorn."
        ) from exc

    uvicorn.run("simulation:app", host="127.0.0.1", port=8000, reload=True)

