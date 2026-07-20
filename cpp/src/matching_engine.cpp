#include "sip_market/matching_engine.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace sip {

namespace {
uint64_t next_aggressive_id() {
  static uint64_t id = 1'000'000'000ULL;
  return ++id;
}
}  // namespace

MatchingEngine::MatchingEngine(MatchConfig cfg) : cfg_(cfg) {}

void MatchingEngine::seed_liquidity(double mid, double tick, int levels, double size_per_level) {
  if (mid <= 0.0 || tick <= 0.0 || levels <= 0 || size_per_level <= 0.0) {
    throw std::invalid_argument("invalid seed parameters");
  }
  for (int i = 1; i <= levels; ++i) {
    Order bid;
    bid.side = Side::Bid;
    bid.type = OrderType::Limit;
    bid.price = mid - static_cast<double>(i) * tick;
    bid.quantity = size_per_level * (1.0 + 0.1 * static_cast<double>(i - 1));
    bid.timestamp_ns = clock_ns_;
    book_.add_order(bid);

    Order ask;
    ask.side = Side::Ask;
    ask.type = OrderType::Limit;
    ask.price = mid + static_cast<double>(i) * tick;
    ask.quantity = size_per_level * (1.0 + 0.1 * static_cast<double>(i - 1));
    ask.timestamp_ns = clock_ns_;
    book_.add_order(ask);
  }
}

double MatchingEngine::apply_slippage(double touch_price, Side aggressive_side, double /*mid*/) const {
  if (cfg_.slippage_bps <= 0.0) return touch_price;
  const double slip = touch_price * (cfg_.slippage_bps / 10'000.0);
  if (aggressive_side == Side::Bid) {
    return touch_price + slip;
  }
  return std::max(0.0, touch_price - slip);
}

std::vector<Trade> MatchingEngine::match_incoming(Order& incoming) {
  std::vector<Trade> local;
  const bool is_buy = incoming.side == Side::Bid;

  while (incoming.remaining > 1e-12) {
    Order* resting = is_buy ? book_.best_ask_order() : book_.best_bid_order();
    if (!resting) break;

    const bool crosses =
        incoming.type == OrderType::Market ||
        (is_buy && incoming.price + 1e-12 >= resting->price) ||
        (!is_buy && incoming.price - 1e-12 <= resting->price);
    if (!crosses) break;

    const double qty = std::min(incoming.remaining, resting->remaining);
    const double raw_px = resting->price;
    const double px = apply_slippage(raw_px, incoming.side, 0.0);
    const uint64_t resting_id = resting->id;

    Trade t;
    t.trade_id = next_trade_id_++;
    t.quantity = qty;
    t.price = px;
    t.timestamp_ns = std::max(incoming.timestamp_ns + incoming.latency_ns, clock_ns_);
    if (is_buy) {
      t.buy_order_id = incoming.id;
      t.sell_order_id = resting_id;
    } else {
      t.buy_order_id = resting_id;
      t.sell_order_id = incoming.id;
    }

    book_.consume(*resting, qty);
    incoming.remaining -= qty;
    local.push_back(t);
    trades_.push_back(t);
    clock_ns_ = t.timestamp_ns;
    book_.erase_if_empty(*resting);
  }
  return local;
}

uint64_t MatchingEngine::submit(Order order) {
  if (order.latency_ns == 0) order.latency_ns = cfg_.default_latency_ns;
  if (order.timestamp_ns == 0) order.timestamp_ns = clock_ns_;
  clock_ns_ = std::max(clock_ns_, order.timestamp_ns);
  order.remaining = order.quantity;

  if (order.type == OrderType::Market) {
    order.id = next_aggressive_id();
    match_incoming(order);
    return 0;
  }

  // Limit: match marketable quantity, then rest remainder (unless IOC)
  order.id = next_aggressive_id();
  match_incoming(order);

  if (order.remaining <= 1e-12) return 0;
  if (order.tif == TimeInForce::IOC) return 0;

  Order rest = order;
  rest.type = OrderType::Limit;
  rest.quantity = order.remaining;
  rest.remaining = order.remaining;
  rest.id = 0;  // book assigns stable resting id
  return book_.add_order(rest);
}

std::vector<Trade> MatchingEngine::market_buy(double qty, uint64_t ts_ns) {
  Order o;
  o.side = Side::Bid;
  o.type = OrderType::Market;
  o.quantity = qty;
  o.timestamp_ns = ts_ns ? ts_ns : clock_ns_;
  const size_t before = trades_.size();
  submit(o);
  return std::vector<Trade>(trades_.begin() + static_cast<std::ptrdiff_t>(before), trades_.end());
}

std::vector<Trade> MatchingEngine::market_sell(double qty, uint64_t ts_ns) {
  Order o;
  o.side = Side::Ask;
  o.type = OrderType::Market;
  o.quantity = qty;
  o.timestamp_ns = ts_ns ? ts_ns : clock_ns_;
  const size_t before = trades_.size();
  submit(o);
  return std::vector<Trade>(trades_.begin() + static_cast<std::ptrdiff_t>(before), trades_.end());
}

}  // namespace sip
