import React, { useEffect, useMemo, useState } from 'react';
import { Line } from '@ant-design/charts';
import './App.css';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://127.0.0.1:8000';

function toISODateInputString(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function App() {
  const [tradeDate, setTradeDate] = useState(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return toISODateInputString(tomorrow);
  });

  const [da, setDa] = useState([]);
  const [rt, setRt] = useState([]);
  const [orders, setOrders] = useState([]);
  const [pnl, setPnl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const daByHour = useMemo(() => Object.fromEntries(da.map((x) => [x.hour, x.price])), [da]);

  async function loadAll(date) {
    setLoading(true);
    setError('');
    try {
      const [daRes, rtRes, ordRes, pnlRes] = await Promise.all([
        fetch(`${API_BASE}/api/prices/day-ahead?date=${date}`),
        fetch(`${API_BASE}/api/prices/real-time?date=${date}`),
        fetch(`${API_BASE}/api/orders?date=${date}`),
        fetch(`${API_BASE}/api/pnl?date=${date}`),
      ]);
      const daJson = await daRes.json();
      const rtJson = await rtRes.json();
      const ordJson = await ordRes.json();
      const pnlJson = await pnlRes.json();
      setDa(daJson.series || []);
      setRt(rtJson.series || []);
      setOrders(ordJson.orders || []);
      setPnl(pnlJson || null);
    } catch (e) {
      setError('Failed to load data. Is the backend running on 8000?');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll(tradeDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradeDate]);

  async function submitOrder(e) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const hour = Number(form.get('hour'));
    const side = form.get('side');
    const price = Number(form.get('price'));
    const quantity = Number(form.get('quantity'));
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: tradeDate, hour, side, price, quantity }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Order rejected');
      }
      await loadAll(tradeDate);
      e.currentTarget.reset();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function deleteOrder(id) {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/orders/${id}?date=${tradeDate}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Delete failed');
      }
      await loadAll(tradeDate);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="App">
      <header className="App-header" style={{ minHeight: 'unset', padding: 16 }}>
        <h2>Virtual Energy Trading</h2>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
          <label>
            Trade Date:&nbsp;
            <input type="date" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} />
          </label>
          {loading && <span>Loading…</span>}
          {error && <span style={{ color: 'salmon' }}>{error}</span>}
        </div>
      </header>

      <main style={{ padding: 16 }}>
        <section style={{ marginBottom: 16 }}>
          <h3>Price Chart</h3>
          <Line
            data={[
              ...da.map((x) => ({ hour: x.hour, price: x.price, type: 'Day-Ahead' })),
              ...rt.map((x) => ({ hour: x.hour, price: x.price, type: 'Real-Time' })),
            ]}
            xField="hour"
            yField="price"
            seriesField="type"
            smooth
            xAxis={{ title: { text: 'Hour' }, tickCount: 24, tickInterval: 1 }}
            yAxis={{ title: { text: '$/MWh' } }}
            height={260}
            padding={[12, 24, 24, 36]}
          />
        </section>

        <section style={{ marginBottom: 16 }}>
          <h3>Day-Ahead Prices</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
            {da.map((x) => (
              <div key={`da-${x.hour}`} style={{ border: '1px solid #e0e0e0', borderRadius: 6, padding: 8 }}>
                <div>HE {x.hour}</div>
                <div>${x.price.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </section>

        <section style={{ marginBottom: 16 }}>
          <h3>Real-Time Prices</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
            {rt.map((x) => (
              <div key={`rt-${x.hour}`} style={{ border: '1px solid #e0e0e0', borderRadius: 6, padding: 8 }}>
                <div>HE {x.hour}</div>
                <div>${x.price.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </section>

        <section style={{ marginBottom: 16 }}>
          <h3>Enter Order (Day-Ahead)</h3>
          <form onSubmit={submitOrder} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <label>
              Hour
              <select name="hour" defaultValue="0">
                {Array.from({ length: 24 }).map((_, h) => (
                  <option key={h} value={h}>{h}</option>
                ))}
              </select>
            </label>
            <label>
              Side
              <select name="side" defaultValue="buy">
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>
            <label>
              Price ($/MWh)
              <input name="price" type="number" step="0.01" min="0.01" placeholder={daByHour[0] || 50} required />
            </label>
            <label>
              Quantity (MWh)
              <input name="quantity" type="number" step="0.1" min="0.1" defaultValue="1" required />
            </label>
            <button type="submit">Submit</button>
          </form>
        </section>

        <section style={{ marginBottom: 16 }}>
          <h3>Orders</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>ID</th>
                  <th>Hour</th>
                  <th>Side</th>
                  <th>Price</th>
                  <th>Qty</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td style={{ fontFamily: 'monospace' }}>{o.id}</td>
                    <td style={{ textAlign: 'center' }}>{o.hour}</td>
                    <td style={{ textAlign: 'center' }}>{o.side}</td>
                    <td style={{ textAlign: 'right' }}>${Number(o.price).toFixed(2)}</td>
                    <td style={{ textAlign: 'right' }}>{Number(o.quantity).toFixed(2)}</td>
                    <td>{o.created_at}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button onClick={() => deleteOrder(o.id)}>Delete</button>
                    </td>
                  </tr>
                ))}
                {orders.length === 0 && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', color: '#999' }}>No orders yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3>PnL</h3>
          {pnl && (
            <div>
              <div style={{ marginBottom: 8 }}><strong>Total:</strong> ${pnl.total_pnl.toFixed(2)} {pnl.currency}</div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th>Hour</th>
                      <th>Side</th>
                      <th>Qty</th>
                      <th>Bid</th>
                      <th>DA</th>
                      <th>RT</th>
                      <th>Filled</th>
                      <th>PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pnl.details.map((d) => (
                      <tr key={d.order_id}>
                        <td style={{ fontFamily: 'monospace' }}>{d.order_id}</td>
                        <td style={{ textAlign: 'center' }}>{d.hour}</td>
                        <td style={{ textAlign: 'center' }}>{d.side}</td>
                        <td style={{ textAlign: 'right' }}>{Number(d.quantity).toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }}>${Number(d.bid_price).toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }}>${Number(d.day_ahead_price).toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }}>${Number(d.real_time_price).toFixed(2)}</td>
                        <td style={{ textAlign: 'center' }}>{d.filled ? 'Yes' : 'No'}</td>
                        <td style={{ textAlign: 'right' }}>${Number(d.pnl).toFixed(2)}</td>
                      </tr>
                    ))}
                    {pnl.details.length === 0 && (
                      <tr><td colSpan={9} style={{ textAlign: 'center', color: '#999' }}>No PnL yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
