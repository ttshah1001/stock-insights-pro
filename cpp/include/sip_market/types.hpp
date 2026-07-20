#pragma once

#include <cstdint>
#include <string>

namespace sip {

enum class Side : uint8_t { Bid = 0, Ask = 1 };

enum class OrderType : uint8_t { Limit = 0, Market = 1 };

enum class TimeInForce : uint8_t { GTC = 0, IOC = 1 };

struct Order {
  uint64_t id = 0;
  Side side = Side::Bid;
  OrderType type = OrderType::Limit;
  TimeInForce tif = TimeInForce::GTC;
  double price = 0.0;
  double quantity = 0.0;
  double remaining = 0.0;
  uint64_t timestamp_ns = 0;
  uint64_t latency_ns = 0;  // simulated network / processing delay
};

struct Trade {
  uint64_t trade_id = 0;
  uint64_t buy_order_id = 0;
  uint64_t sell_order_id = 0;
  double price = 0.0;
  double quantity = 0.0;
  uint64_t timestamp_ns = 0;
};

struct Level {
  double price = 0.0;
  double quantity = 0.0;
  int order_count = 0;
};

struct BookSnapshot {
  double best_bid = 0.0;
  double best_ask = 0.0;
  double bid_size = 0.0;
  double ask_size = 0.0;
  double mid = 0.0;
  double spread = 0.0;
  double imbalance = 0.0;  // (bid_size - ask_size) / (bid_size + ask_size)
};

}  // namespace sip
