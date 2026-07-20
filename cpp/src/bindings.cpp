#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "sip_market/matching_engine.hpp"
#include "sip_market/order_book.hpp"
#include "sip_market/types.hpp"

#include <chrono>
#include <vector>

namespace py = pybind11;

PYBIND11_MODULE(sip_market_native, m) {
  m.doc() = "Native order book and matching engine";

  py::enum_<sip::Side>(m, "Side")
      .value("Bid", sip::Side::Bid)
      .value("Ask", sip::Side::Ask);

  py::enum_<sip::OrderType>(m, "OrderType")
      .value("Limit", sip::OrderType::Limit)
      .value("Market", sip::OrderType::Market);

  py::enum_<sip::TimeInForce>(m, "TimeInForce")
      .value("GTC", sip::TimeInForce::GTC)
      .value("IOC", sip::TimeInForce::IOC);

  py::class_<sip::Order>(m, "Order")
      .def(py::init<>())
      .def_readwrite("id", &sip::Order::id)
      .def_readwrite("side", &sip::Order::side)
      .def_readwrite("type", &sip::Order::type)
      .def_readwrite("tif", &sip::Order::tif)
      .def_readwrite("price", &sip::Order::price)
      .def_readwrite("quantity", &sip::Order::quantity)
      .def_readwrite("remaining", &sip::Order::remaining)
      .def_readwrite("timestamp_ns", &sip::Order::timestamp_ns)
      .def_readwrite("latency_ns", &sip::Order::latency_ns);

  py::class_<sip::Trade>(m, "Trade")
      .def(py::init<>())
      .def_readwrite("trade_id", &sip::Trade::trade_id)
      .def_readwrite("buy_order_id", &sip::Trade::buy_order_id)
      .def_readwrite("sell_order_id", &sip::Trade::sell_order_id)
      .def_readwrite("price", &sip::Trade::price)
      .def_readwrite("quantity", &sip::Trade::quantity)
      .def_readwrite("timestamp_ns", &sip::Trade::timestamp_ns);

  py::class_<sip::Level>(m, "Level")
      .def(py::init<>())
      .def_readwrite("price", &sip::Level::price)
      .def_readwrite("quantity", &sip::Level::quantity)
      .def_readwrite("order_count", &sip::Level::order_count);

  py::class_<sip::BookSnapshot>(m, "BookSnapshot")
      .def(py::init<>())
      .def_readwrite("best_bid", &sip::BookSnapshot::best_bid)
      .def_readwrite("best_ask", &sip::BookSnapshot::best_ask)
      .def_readwrite("bid_size", &sip::BookSnapshot::bid_size)
      .def_readwrite("ask_size", &sip::BookSnapshot::ask_size)
      .def_readwrite("mid", &sip::BookSnapshot::mid)
      .def_readwrite("spread", &sip::BookSnapshot::spread)
      .def_readwrite("imbalance", &sip::BookSnapshot::imbalance);

  py::class_<sip::OrderBook>(m, "OrderBook")
      .def(py::init<>())
      .def("add_order", &sip::OrderBook::add_order)
      .def("cancel_order", &sip::OrderBook::cancel_order)
      .def("best_bid", [](const sip::OrderBook& b) {
        auto v = b.best_bid();
        return v.has_value() ? py::cast(*v) : py::none();
      })
      .def("best_ask", [](const sip::OrderBook& b) {
        auto v = b.best_ask();
        return v.has_value() ? py::cast(*v) : py::none();
      })
      .def("snapshot", &sip::OrderBook::snapshot)
      .def("bid_levels", &sip::OrderBook::bid_levels, py::arg("depth") = 10)
      .def("ask_levels", &sip::OrderBook::ask_levels, py::arg("depth") = 10)
      .def("order_count", &sip::OrderBook::order_count);

  py::class_<sip::MatchConfig>(m, "MatchConfig")
      .def(py::init<>())
      .def_readwrite("slippage_bps", &sip::MatchConfig::slippage_bps)
      .def_readwrite("default_latency_ns", &sip::MatchConfig::default_latency_ns);

  py::class_<sip::MatchingEngine>(m, "MatchingEngine")
      .def(py::init<sip::MatchConfig>(), py::arg("config") = sip::MatchConfig{})
      .def("seed_liquidity", &sip::MatchingEngine::seed_liquidity,
           py::arg("mid"), py::arg("tick"), py::arg("levels"), py::arg("size_per_level"))
      .def("submit", &sip::MatchingEngine::submit)
      .def("market_buy", &sip::MatchingEngine::market_buy,
           py::arg("qty"), py::arg("ts_ns") = 0)
      .def("market_sell", &sip::MatchingEngine::market_sell,
           py::arg("qty"), py::arg("ts_ns") = 0)
      .def("trades", &sip::MatchingEngine::trades)
      .def("clear_trades", &sip::MatchingEngine::clear_trades)
      .def("snapshot", [](const sip::MatchingEngine& eng) {
        return eng.book().snapshot();
      })
      .def("bid_levels", [](const sip::MatchingEngine& eng, int depth) {
        return eng.book().bid_levels(depth);
      }, py::arg("depth") = 10)
      .def("ask_levels", [](const sip::MatchingEngine& eng, int depth) {
        return eng.book().ask_levels(depth);
      }, py::arg("depth") = 10)
      .def("order_count", [](const sip::MatchingEngine& eng) {
        return eng.book().order_count();
      });

  m.def("benchmark_match", [](int n_orders, double mid) {
    sip::MatchConfig cfg;
    cfg.slippage_bps = 0.5;
    sip::MatchingEngine eng(cfg);
    eng.seed_liquidity(mid, 0.01, 20, 100.0);

    using clock = std::chrono::steady_clock;
    const auto t0 = clock::now();
    for (int i = 0; i < n_orders; ++i) {
      if (i % 2 == 0) eng.market_buy(1.0);
      else eng.market_sell(1.0);
      if (i % 50 == 0) {
        eng.seed_liquidity(mid, 0.01, 5, 50.0);
      }
    }
    const auto t1 = clock::now();
    const double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    py::dict out;
    out["orders"] = n_orders;
    out["elapsed_ms"] = ms;
    out["orders_per_sec"] = n_orders / (ms / 1000.0);
    out["trades"] = eng.trades().size();
    out["backend"] = "native";
    return out;
  }, py::arg("n_orders") = 10000, py::arg("mid") = 100.0);
}
