#pragma once

#include "sip_market/order_book.hpp"

#include <vector>

namespace sip {

struct MatchConfig {
  // Extra adverse selection / impact: fraction of spread paid beyond touch
  double slippage_bps = 1.0;
  // Fixed processing latency applied if order.latency_ns == 0
  uint64_t default_latency_ns = 50'000;  // 50 microseconds
};

/**
 * Continuous matching engine with price-time priority and simple
 * latency + slippage modeling for aggressive orders.
 */
class MatchingEngine {
 public:
  explicit MatchingEngine(MatchConfig cfg = {});

  OrderBook& book() { return book_; }
  const OrderBook& book() const { return book_; }
  const std::vector<Trade>& trades() const { return trades_; }
  void clear_trades() { trades_.clear(); }

  // Submit order; returns resting order id (0 if fully filled / cancelled IOC)
  uint64_t submit(Order order);

  // Seed book with resting liquidity around a mid price
  void seed_liquidity(double mid, double tick, int levels, double size_per_level);

  // Run a simple marketable sweep for qty at market (for sim / benchmarks)
  std::vector<Trade> market_buy(double qty, uint64_t ts_ns = 0);
  std::vector<Trade> market_sell(double qty, uint64_t ts_ns = 0);

 private:
  std::vector<Trade> match_incoming(Order& incoming);
  double apply_slippage(double touch_price, Side aggressive_side, double mid) const;

  MatchConfig cfg_;
  OrderBook book_;
  std::vector<Trade> trades_;
  uint64_t next_trade_id_ = 1;
  uint64_t clock_ns_ = 0;
};

}  // namespace sip
