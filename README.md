# Virtual Energy Trading App

A small app that simulates a trader in a Day-Ahead electricity market. View day-ahead (DA) and real-time (RT) prices, place up to 10 buy/sell bids per hour, and see fills and PnL.

## Features
- View DA and RT hourly prices (24 hours)
- Submit up to 10 buy/sell bids per hour (MWh, $/MWh)
- Submission deadline: 11:00 local time on the day before delivery
- Synthetic prices by default; optional external DA data
- PnL per order and total, assuming trader is a small player

## Tech Stack
- Backend: FastAPI (`backend/simulation.py`)
- Frontend: React (CRA) (`frontend/`)
- Storage: JSON file (`backend/orders.json`)

## Prerequisites
- Python 3.10+
- Node.js 16+

A Python virtual environment is included at `backend/venv`.

## Running Locally
### 1) Backend (FastAPI)
From the `backend` directory:
```bash
cd backend
./venv/bin/python -m uvicorn simulation:app --reload
```
Health check:
```bash
curl http://127.0.0.1:8000/health
```
Alternative (activate venv):
```bash
cd backend
source ./venv/bin/activate
python -m uvicorn simulation:app --reload
```
Or run the file directly (requires uvicorn installed in this interpreter):
```bash
cd backend
python simulation.py
```

### 2) Frontend (React)
From the `frontend` directory:
```bash
cd frontend
npm start
```
Open `http://localhost:3000` if the browser doesn’t open.

### 3) Point frontend to a different backend (optional)
```bash
REACT_APP_API_BASE="http://your-backend:8000" npm start
```

## Configuration (Backend)
- `GRIDSTATUS_DAY_AHEAD_URL` (optional): If set, backend tries to fetch DA prices from this URL. Expected response:
```json
[
  {"hour": 0, "price": 52.0},
  {"hour": 1, "price": 50.3}
  // ... through hour 23
]
```
If unset or failing, synthetic DA prices are used.

## API Overview
Base: `http://127.0.0.1:8000`

- `GET /health` → `{ "status": "ok" }`
- `GET /api/prices/day-ahead?date=YYYY-MM-DD` → `{ date, source, series: [{ hour, price }] }`
- `GET /api/prices/real-time?date=YYYY-MM-DD` → `{ date, source: "synthetic", series: [{ hour, price }] }`
- `GET /api/orders?date=YYYY-MM-DD` → `{ date, orders: [...] }`
- `POST /api/orders` body `{ date, hour (0-23), side (buy|sell), price, quantity }`
- `DELETE /api/orders/{id}?date=YYYY-MM-DD`
- `GET /api/pnl?date=YYYY-MM-DD` → `{ date, currency, total_pnl, details: [...] }`

### Example
```bash
# DA prices for tomorrow (macOS date)
curl "http://127.0.0.1:8000/api/prices/day-ahead?date=$(date -v+1d +%F)"

# Place an order
curl -X POST "http://127.0.0.1:8000/api/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2025-01-01",
    "hour": 8,
    "side": "buy",
    "price": 60,
    "quantity": 1.5
  }'

# Get PnL
curl "http://127.0.0.1:8000/api/pnl?date=2025-01-01"
```

## Market Logic (Simplified)
- Deadline: 11:00 local time on the day before delivery
- Max 10 bids per hour
- Fill rule:
  - Buy fills if `bid_price ≥ DA price`
  - Sell fills if `bid_price ≤ DA price`
- PnL if filled:
  - Buy: `qty × (RT − DA)`
  - Sell: `−qty × (RT − DA)`

## Structure
```
CVector/
  backend/
    simulation.py
    orders.json        # created at runtime
    venv/
  frontend/
    src/App.js
    package.json
```

## Troubleshooting
- Bad interpreter for `uvicorn`: run `./venv/bin/python -m uvicorn simulation:app --reload` instead of the `uvicorn` script.
- `python simulation.py` requires `uvicorn` in the same interpreter; use the venv’s `python`.

## Future Improvements
- Real price integration (official client, ISO-specific endpoints)
- Timezone/holiday calendars
- Partial fills and merit order
- Auth and multi-user isolation
- DB persistence and migrations
- Docker for one-command startup
