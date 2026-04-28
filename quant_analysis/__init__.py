"""
Quant Stock Market Analysis Framework
=====================================
A quantitative analysis model for investment bankers, traders, and quant traders.
"""

__version__ = "1.0.0"

try:
    from .data.loader import MarketDataLoader
except ImportError:
    MarketDataLoader = None
try:
    from .technical.indicators import TechnicalAnalyzer
except ImportError:
    TechnicalAnalyzer = None
try:
    from .fundamental.ratios import FundamentalAnalyzer
except ImportError:
    FundamentalAnalyzer = None
try:
    from .risk.metrics import RiskAnalyzer
except ImportError:
    RiskAnalyzer = None
try:
    from .models.forecaster import PriceForecaster
except ImportError:
    PriceForecaster = None
try:
    from .backtest.engine import BacktestEngine
except ImportError:
    BacktestEngine = None
try:
    from .report.generator import ReportGenerator
except ImportError:
    ReportGenerator = None
try:
    from .trading.daily_model import DailyTradingModel, TradeRecommendation
except ImportError:
    DailyTradingModel = None
    TradeRecommendation = None

__all__ = [
    "MarketDataLoader",
    "TechnicalAnalyzer",
    "FundamentalAnalyzer",
    "RiskAnalyzer",
    "PriceForecaster",
    "BacktestEngine",
    "ReportGenerator",
    "DailyTradingModel",
    "TradeRecommendation",
]
