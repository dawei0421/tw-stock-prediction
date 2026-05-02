"""TTL cache wrappers using cachetools."""

from cachetools import TTLCache

# Quote cache: max 500 stocks, 60-second TTL (real yfinance data)
quote_cache: TTLCache = TTLCache(maxsize=500, ttl=60)

# Signal calculation cache: max 200, 60-second TTL
signal_cache: TTLCache = TTLCache(maxsize=200, ttl=60)

# AI analysis cache: max 100, 5-minute TTL (keyed by score bucket)
ai_cache: TTLCache = TTLCache(maxsize=100, ttl=300)

# Stock info cache: max 2000, 24-hour TTL
stock_info_cache: TTLCache = TTLCache(maxsize=2000, ttl=86400)

# Historical data cache: max 100, 1-hour TTL
history_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)

# Rate-limit cooldown cache: max 100, 5-minute TTL
rate_limit_cache: TTLCache = TTLCache(maxsize=100, ttl=300)

# TWSE institutional/margin data cache: max 500, 12-hour TTL (updates once after market close)
twse_cache: TTLCache = TTLCache(maxsize=500, ttl=43200)

# Intraday real-time quote cache: max 500, 5-second TTL (TWSE MIS API during market hours)
intraday_cache: TTLCache = TTLCache(maxsize=500, ttl=5)

# Raw historical dataframe cache: max 200, 30-minute TTL (avoids repeated yfinance 6mo fetches)
raw_df_cache: TTLCache = TTLCache(maxsize=200, ttl=1800)
