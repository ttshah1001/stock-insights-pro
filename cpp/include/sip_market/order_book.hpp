#pragma once

#include "sip_market/types.hpp"

#include <list>
#include <map>
#include <optional>
#include <unordered_map>
#include <vector>

namespace sip {

/**
 * Price-time priority limit order book.
 * Bids: highest price first. Asks: lowest price first.
 * Within a price level, FIFO by arrival timestamp.
 */
class OrderBook {
 public:
  uint64_t add_order(Order order);
  bool cancel_order(uint64_t order_id);
  std::optional<Order> get_order(uint64_t order_id) const;

  std::optional<double> best_bid() const;
  std::optional<double> best_ask() const;
  BookSnapshot snapshot() const;

  std::vector<Level> bid_levels(int depth = 10) const;
  std::vector<Level> ask_levels(int depth = 10) const;

  bool empty() const { return bids_.empty() && asks_.empty(); }
  size_t order_count() const { return orders_.size(); }

  // Matching helpers used by MatchingEngine
  Order* best_bid_order();
  Order* best_ask_order();
  void consume(Order& order, double qty);
  void erase_if_empty(Order& order);

 private:
  using BidMap = std::map<double, std::list<Order>, std::greater<double>>;
  using AskMap = std::map<double, std::list<Order>, std::less<double>>;

  struct Index {
    Side side;
    double price;
    std::list<Order>::iterator it;
  };

  BidMap bids_;
  AskMap asks_;
  std::unordered_map<uint64_t, Index> orders_;
  uint64_t next_id_ = 1;
};

}  // namespace sip
