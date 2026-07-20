#include "sip_market/order_book.hpp"

#include <algorithm>
#include <stdexcept>

namespace sip {

uint64_t OrderBook::add_order(Order order) {
  if (order.quantity <= 0.0) {
    throw std::invalid_argument("quantity must be positive");
  }
  if (order.type == OrderType::Limit && order.price <= 0.0) {
    throw std::invalid_argument("limit order requires positive price");
  }
  if (order.id == 0) {
    order.id = next_id_++;
  } else {
    next_id_ = std::max(next_id_, order.id + 1);
  }
  order.remaining = order.quantity;

  Index idx;
  idx.side = order.side;
  idx.price = order.price;

  if (order.side == Side::Bid) {
    auto& lvl = bids_[order.price];
    lvl.push_back(order);
    idx.it = std::prev(lvl.end());
  } else {
    auto& lvl = asks_[order.price];
    lvl.push_back(order);
    idx.it = std::prev(lvl.end());
  }
  orders_[order.id] = idx;
  return order.id;
}

bool OrderBook::cancel_order(uint64_t order_id) {
  auto it = orders_.find(order_id);
  if (it == orders_.end()) return false;
  Index& idx = it->second;
  if (idx.side == Side::Bid) {
    auto map_it = bids_.find(idx.price);
    if (map_it == bids_.end()) {
      orders_.erase(it);
      return false;
    }
    map_it->second.erase(idx.it);
    if (map_it->second.empty()) bids_.erase(map_it);
  } else {
    auto map_it = asks_.find(idx.price);
    if (map_it == asks_.end()) {
      orders_.erase(it);
      return false;
    }
    map_it->second.erase(idx.it);
    if (map_it->second.empty()) asks_.erase(map_it);
  }
  orders_.erase(it);
  return true;
}

std::optional<Order> OrderBook::get_order(uint64_t order_id) const {
  auto it = orders_.find(order_id);
  if (it == orders_.end()) return std::nullopt;
  return *(it->second.it);
}

std::optional<double> OrderBook::best_bid() const {
  if (bids_.empty()) return std::nullopt;
  return bids_.begin()->first;
}

std::optional<double> OrderBook::best_ask() const {
  if (asks_.empty()) return std::nullopt;
  return asks_.begin()->first;
}

BookSnapshot OrderBook::snapshot() const {
  BookSnapshot s;
  if (!bids_.empty()) {
    s.best_bid = bids_.begin()->first;
    for (const auto& o : bids_.begin()->second) s.bid_size += o.remaining;
  }
  if (!asks_.empty()) {
    s.best_ask = asks_.begin()->first;
    for (const auto& o : asks_.begin()->second) s.ask_size += o.remaining;
  }
  if (s.best_bid > 0.0 && s.best_ask > 0.0) {
    s.mid = 0.5 * (s.best_bid + s.best_ask);
    s.spread = s.best_ask - s.best_bid;
  } else if (s.best_bid > 0.0) {
    s.mid = s.best_bid;
  } else if (s.best_ask > 0.0) {
    s.mid = s.best_ask;
  }
  const double denom = s.bid_size + s.ask_size;
  if (denom > 0.0) {
    s.imbalance = (s.bid_size - s.ask_size) / denom;
  }
  return s;
}

std::vector<Level> OrderBook::bid_levels(int depth) const {
  std::vector<Level> out;
  int n = 0;
  for (const auto& [px, lst] : bids_) {
    if (n++ >= depth) break;
    Level lvl;
    lvl.price = px;
    lvl.order_count = static_cast<int>(lst.size());
    for (const auto& o : lst) lvl.quantity += o.remaining;
    out.push_back(lvl);
  }
  return out;
}

std::vector<Level> OrderBook::ask_levels(int depth) const {
  std::vector<Level> out;
  int n = 0;
  for (const auto& [px, lst] : asks_) {
    if (n++ >= depth) break;
    Level lvl;
    lvl.price = px;
    lvl.order_count = static_cast<int>(lst.size());
    for (const auto& o : lst) lvl.quantity += o.remaining;
    out.push_back(lvl);
  }
  return out;
}

Order* OrderBook::best_bid_order() {
  if (bids_.empty() || bids_.begin()->second.empty()) return nullptr;
  return &bids_.begin()->second.front();
}

Order* OrderBook::best_ask_order() {
  if (asks_.empty() || asks_.begin()->second.empty()) return nullptr;
  return &asks_.begin()->second.front();
}

void OrderBook::consume(Order& order, double qty) {
  order.remaining -= qty;
  if (order.remaining < 0.0) order.remaining = 0.0;
}

void OrderBook::erase_if_empty(Order& order) {
  if (order.remaining > 1e-12) return;
  cancel_order(order.id);
}

}  // namespace sip
