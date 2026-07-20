"""
Market microstructure simulation: order book + matching engine.

Uses the native C++ extension when available; otherwise a Python fallback
with the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional

try:
    import sip_market_native as _native

    BACKEND = "native"
except ImportError:
    _native = None
    BACKEND = "python"


class Side(str, Enum):
    Bid = "Bid"
    Ask = "Ask"


class OrderType(str, Enum):
    Limit = "Limit"
    Market = "Market"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"


@dataclass
class LevelView:
    price: float
    quantity: float
    order_count: int


@dataclass
class SnapshotView:
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    mid: float
    spread: float
    imbalance: float


@dataclass
class TradeView:
    trade_id: int
    buy_order_id: int
    sell_order_id: int
    price: float
    quantity: float
    timestamp_ns: int


def _snap_from_native(s) -> SnapshotView:
    return SnapshotView(
        best_bid=float(s.best_bid),
        best_ask=float(s.best_ask),
        bid_size=float(s.bid_size),
        ask_size=float(s.ask_size),
        mid=float(s.mid),
        spread=float(s.spread),
        imbalance=float(s.imbalance),
    )


def _trade_from_native(t) -> TradeView:
    return TradeView(
        trade_id=int(t.trade_id),
        buy_order_id=int(t.buy_order_id),
        sell_order_id=int(t.sell_order_id),
        price=float(t.price),
        quantity=float(t.quantity),
        timestamp_ns=int(t.timestamp_ns),
    )


class _PythonEngine:
    """Minimal price-time book used when the native module is not built."""

    def __init__(self, slippage_bps: float = 1.0, default_latency_ns: int = 50_000):
        self.slippage_bps = slippage_bps
        self.default_latency_ns = default_latency_ns
        self._bids: dict[float, list[dict]] = {}
        self._asks: dict[float, list[dict]] = {}
        self._next_id = 1
        self._next_trade = 1
        self._clock = 0
        self._trades: list[TradeView] = []

    def seed_liquidity(self, mid: float, tick: float, levels: int, size_per_level: float) -> None:
        for i in range(1, levels + 1):
            self._add(Side.Bid, mid - i * tick, size_per_level * (1 + 0.1 * (i - 1)))
            self._add(Side.Ask, mid + i * tick, size_per_level * (1 + 0.1 * (i - 1)))

    def _add(self, side: Side, price: float, qty: float) -> int:
        oid = self._next_id
        self._next_id += 1
        order = {"id": oid, "price": price, "remaining": qty, "ts": self._clock}
        book = self._bids if side == Side.Bid else self._asks
        book.setdefault(price, []).append(order)
        return oid

    def snapshot(self) -> SnapshotView:
        bid_prices = sorted(self._bids.keys(), reverse=True)
        ask_prices = sorted(self._asks.keys())
        best_bid = bid_prices[0] if bid_prices else 0.0
        best_ask = ask_prices[0] if ask_prices else 0.0
        bid_size = sum(o["remaining"] for o in self._bids.get(best_bid, [])) if best_bid else 0.0
        ask_size = sum(o["remaining"] for o in self._asks.get(best_ask, [])) if best_ask else 0.0
        mid = 0.5 * (best_bid + best_ask) if best_bid and best_ask else (best_bid or best_ask)
        spread = (best_ask - best_bid) if best_bid and best_ask else 0.0
        denom = bid_size + ask_size
        imbalance = ((bid_size - ask_size) / denom) if denom else 0.0
        return SnapshotView(best_bid, best_ask, bid_size, ask_size, mid, spread, imbalance)

    def bid_levels(self, depth: int = 10) -> list[LevelView]:
        out = []
        for px in sorted(self._bids.keys(), reverse=True)[:depth]:
            lst = self._bids[px]
            out.append(LevelView(px, sum(o["remaining"] for o in lst), len(lst)))
        return out

    def ask_levels(self, depth: int = 10) -> list[LevelView]:
        out = []
        for px in sorted(self._asks.keys())[:depth]:
            lst = self._asks[px]
            out.append(LevelView(px, sum(o["remaining"] for o in lst), len(lst)))
        return out

    def _slip(self, px: float, buy: bool) -> float:
        slip = px * (self.slippage_bps / 10_000.0)
        return px + slip if buy else max(0.0, px - slip)

    def _match(self, side: Side, qty: float, limit: Optional[float], is_market: bool) -> list[TradeView]:
        buy = side == Side.Bid
        remaining = qty
        oid = self._next_id
        self._next_id += 1
        local: list[TradeView] = []
        while remaining > 1e-12:
            prices = sorted(self._asks.keys()) if buy else sorted(self._bids.keys(), reverse=True)
            if not prices:
                break
            px = prices[0]
            if not is_market:
                if buy and limit is not None and limit + 1e-12 < px:
                    break
                if not buy and limit is not None and limit - 1e-12 > px:
                    break
            book = self._asks if buy else self._bids
            level = book[px]
            while remaining > 1e-12 and level:
                resting = level[0]
                fill = min(remaining, resting["remaining"])
                fill_px = self._slip(px, buy)
                t = TradeView(
                    trade_id=self._next_trade,
                    buy_order_id=oid if buy else resting["id"],
                    sell_order_id=resting["id"] if buy else oid,
                    price=fill_px,
                    quantity=fill,
                    timestamp_ns=self._clock + self.default_latency_ns,
                )
                self._next_trade += 1
                self._clock = t.timestamp_ns
                resting["remaining"] -= fill
                remaining -= fill
                local.append(t)
                self._trades.append(t)
                if resting["remaining"] <= 1e-12:
                    level.pop(0)
            if not level:
                del book[px]
        return local

    def market_buy(self, qty: float, ts_ns: int = 0) -> list[TradeView]:
        if ts_ns:
            self._clock = max(self._clock, ts_ns)
        return self._match(Side.Bid, qty, None, True)

    def market_sell(self, qty: float, ts_ns: int = 0) -> list[TradeView]:
        if ts_ns:
            self._clock = max(self._clock, ts_ns)
        return self._match(Side.Ask, qty, None, True)

    def submit_limit(self, side: Side, price: float, qty: float, ioc: bool = False) -> int:
        trades = self._match(side, qty, price, False)
        filled = sum(t.quantity for t in trades)
        rem = qty - filled
        if rem <= 1e-12 or ioc:
            return 0
        return self._add(side, price, rem)

    def trades(self) -> list[TradeView]:
        return list(self._trades)

    def clear_trades(self) -> None:
        self._trades.clear()

    def order_count(self) -> int:
        return sum(len(v) for v in self._bids.values()) + sum(len(v) for v in self._asks.values())


class MarketSimulator:
    """High-level simulator used by the web API and CLI."""

    def __init__(self, slippage_bps: float = 1.0, default_latency_ns: int = 50_000):
        self.backend = BACKEND
        self.slippage_bps = slippage_bps
        self.default_latency_ns = default_latency_ns
        if _native is not None:
            cfg = _native.MatchConfig()
            cfg.slippage_bps = float(slippage_bps)
            cfg.default_latency_ns = int(default_latency_ns)
            self._eng = _native.MatchingEngine(cfg)
            self._py = None
        else:
            self._eng = None
            self._py = _PythonEngine(slippage_bps, default_latency_ns)

    def seed(self, mid: float, tick: float = 0.01, levels: int = 10, size_per_level: float = 100.0) -> SnapshotView:
        if self._eng is not None:
            self._eng.seed_liquidity(float(mid), float(tick), int(levels), float(size_per_level))
            return _snap_from_native(self._eng.snapshot())
        self._py.seed_liquidity(float(mid), float(tick), int(levels), float(size_per_level))
        return self._py.snapshot()

    def market_buy(self, qty: float) -> list[TradeView]:
        if self._eng is not None:
            return [_trade_from_native(t) for t in self._eng.market_buy(float(qty))]
        return self._py.market_buy(float(qty))

    def market_sell(self, qty: float) -> list[TradeView]:
        if self._eng is not None:
            return [_trade_from_native(t) for t in self._eng.market_sell(float(qty))]
        return self._py.market_sell(float(qty))

    def snapshot(self) -> SnapshotView:
        if self._eng is not None:
            return _snap_from_native(self._eng.snapshot())
        return self._py.snapshot()

    def depth(self, levels: int = 10) -> dict[str, Any]:
        if self._eng is not None:
            bids = [
                {"price": float(l.price), "quantity": float(l.quantity), "order_count": int(l.order_count)}
                for l in self._eng.bid_levels(int(levels))
            ]
            asks = [
                {"price": float(l.price), "quantity": float(l.quantity), "order_count": int(l.order_count)}
                for l in self._eng.ask_levels(int(levels))
            ]
        else:
            bids = [asdict(l) for l in self._py.bid_levels(int(levels))]
            asks = [asdict(l) for l in self._py.ask_levels(int(levels))]
        snap = self.snapshot()
        return {"bids": bids, "asks": asks, "snapshot": asdict(snap), "backend": self.backend}

    def run_demo(self, mid: float, buy_qty: float = 25.0, sell_qty: float = 15.0) -> dict[str, Any]:
        self.seed(mid=mid, tick=0.01, levels=10, size_per_level=100.0)
        before = asdict(self.snapshot())
        buys = [asdict(t) for t in self.market_buy(buy_qty)]
        sells = [asdict(t) for t in self.market_sell(sell_qty)]
        after = asdict(self.snapshot())
        depth = self.depth(8)
        avg_buy = (sum(t["price"] * t["quantity"] for t in buys) / sum(t["quantity"] for t in buys)) if buys else None
        avg_sell = (sum(t["price"] * t["quantity"] for t in sells) / sum(t["quantity"] for t in sells)) if sells else None
        return {
            "backend": self.backend,
            "mid": mid,
            "before": before,
            "after": after,
            "buy_trades": buys,
            "sell_trades": sells,
            "avg_buy_price": avg_buy,
            "avg_sell_price": avg_sell,
            "depth": depth,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
        }


def benchmark(n_orders: int = 10_000, mid: float = 100.0) -> dict[str, Any]:
    if _native is not None:
        return dict(_native.benchmark_match(int(n_orders), float(mid)))
    import time

    sim = MarketSimulator(slippage_bps=0.5)
    sim.seed(mid=mid, tick=0.01, levels=20, size_per_level=100.0)
    t0 = time.perf_counter()
    for i in range(n_orders):
        if i % 2 == 0:
            sim.market_buy(1.0)
        else:
            sim.market_sell(1.0)
        if i % 50 == 0:
            sim.seed(mid=mid, tick=0.01, levels=5, size_per_level=50.0)
    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "orders": n_orders,
        "elapsed_ms": ms,
        "orders_per_sec": n_orders / (ms / 1000.0) if ms > 0 else 0.0,
        "trades": len(sim._py.trades()) if sim._py else 0,
        "backend": "python",
    }
