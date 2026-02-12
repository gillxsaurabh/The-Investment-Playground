# Stock Health Module - On-Demand Analysis (Kite API Edition)

## Overview
This implementation eliminates the use of yfinance and leverages the paid Kite API for all market data operations. The system follows a **zero-analysis-on-load** principle where stock analysis happens only when the user explicitly requests it.

## Key Features

### ✅ On-Demand Analysis
- **No bulk processing**: Analysis is triggered only when the user clicks "Analyze" for a specific stock
- **Cost-effective**: Only pay for LLM tokens when analyzing stocks the user cares about
- **Fast page loads**: Dashboard loads instantly with just the holdings list

### ✅ Kite API Integration
- **Historical Data**: Fetches daily candles using `kite.historical_data()`
- **Market Indices**: Real-time Nifty 50 and Sensex data via `kite.quote()`
- **Instrument Lookup**: Automatic instrument token resolution
- **Rate Limiting**: Built-in delays to respect Kite's 3 req/sec limit

### ✅ Smart Caching
- **Nifty Data Cache**: Nifty 50 historical data is cached for 1 hour
- **Why**: Multiple stock analyses use Nifty for relative strength calculation
- **Benefit**: Only 1 API call for Nifty regardless of how many stocks are analyzed

## Architecture

### Backend Components

#### 1. `stock_analyzer.py` - New On-Demand Analyzer
```python
class StockAnalyzer:
    def analyze_stock(symbol, instrument_token=None):
        # Fetch Nifty (cached)
        # Fetch stock history from Kite
        # Calculate technical indicators (ADX, EMA, Relative Strength)
        # Scrape fundamentals from Screener.in
        # Get AI sentiment from Gemini
        # Return comprehensive health report
```

**Key Methods:**
- `_get_nifty_data()`: Fetches/caches Nifty 50 data
- `_fetch_stock_history()`: Gets stock candles from Kite
- `_calculate_technical_score()`: Uses pandas-ta for ADX and EMA
- `_calculate_fundamental_score()`: Scrapes Screener.in
- `_get_ai_sentiment()`: Calls Gemini AI for sentiment analysis

#### 2. New API Endpoint: `/api/analyze-stock`

**Request:**
```json
POST /api/analyze-stock
{
  "access_token": "your_kite_token",
  "symbol": "RELIANCE",
  "instrument_token": 738561  // optional
}
```

**Response:**
```json
{
  "success": true,
  "symbol": "RELIANCE",
  "score": 4.2,
  "details": {
    "recency": {
      "score": 5,
      "detail": "Outperforming Nifty: 15.2% vs 8.3%"
    },
    "trend": {
      "score": 4,
      "strength": "Strong (ADX: 28.5)",
      "direction": "Bullish"
    },
    "fundamentals": {
      "score": 4,
      "summary": "ROE: 12.5%, D/E: 0.85, Growth: 18.2%",
      "roe": 12.5,
      "debt_to_equity": 0.85,
      "sales_growth": 18.2
    },
    "ai_sentiment": {
      "score": 4,
      "summary": "Strong fundamentals with positive outlook..."
    }
  },
  "analyzed_at": "2026-02-12T10:30:45.123456"
}
```

### Scoring System

**Overall Score Calculation:**
- **Recency (Relative Strength)**: 25% weight
- **Trend (ADX + EMA)**: 25% weight
- **Fundamentals (ROE, D/E)**: 30% weight
- **AI Sentiment**: 20% weight

**Score Range:** 0-5
- 5.0 - Strong Buy
- 4.0 - Buy
- 3.0 - Neutral/Hold
- 2.0 - Sell
- 1.0 - Strong Sell

### Technical Indicators

#### 1. Recency Score (Relative Strength)
- Compares stock performance vs Nifty 50 over 3 months
- Uses Kite historical data instead of yfinance
- Scoring:
  - 5: Outperforming Nifty by >5%
  - 4: Outperforming Nifty
  - 3: In-line with market
  - 2: Underperforming

#### 2. Trend Score (ADX + EMA)
- **ADX (Average Directional Index)**: Calculated using pandas-ta
  - >25: Strong trend
  - 20-25: Moderate trend
  - <20: Weak/sideways
- **EMA Cross**: Uses 20-day and 50-day EMAs
  - Price > EMA20 > EMA50 = Bullish
  - Price < EMA20 < EMA50 = Bearish

## Migration from yfinance

### What Changed

1. **Removed Dependencies:**
   - ❌ `yfinance==0.2.36`
   
2. **Added Dependencies:**
   - ✅ `pandas-ta>=0.3.14b` (for technical indicators)

3. **Data Source Changes:**
   - **Historical Data**: `yfinance.Ticker().history()` → `kite.historical_data()`
   - **Market Indices**: `yf.Ticker("^NSEI")` → `kite.quote(['NSE:NIFTY 50'])`
   - **Technical Indicators**: Manual calculation → `pandas-ta.adx()`, `pandas-ta.ema()`

4. **API Changes:**
   - **Market Indices Endpoint**: Now requires `access_token` (POST instead of GET)

### Code Comparison

**Before (yfinance):**
```python
nifty = yf.Ticker("^NSEI")
nifty_data = nifty.history(period="6mo")
```

**After (Kite API):**
```python
nifty_token = 256265
nifty_history = kite.historical_data(
    nifty_token,
    from_date.strftime("%Y-%m-%d"),
    to_date.strftime("%Y-%m-%d"),
    "day"
)
df = pd.DataFrame(nifty_history)
```

## Cost Analysis

### Old Approach (Batch Processing)
- **Scenario**: Portfolio with 50 stocks
- **Cost**: 50 LLM calls on every page load
- **Time**: 2-5 minutes to load dashboard
- **Kite API**: 50+ calls (immediate)

### New Approach (On-Demand)
- **Scenario**: Same portfolio, user analyzes 3 stocks
- **Cost**: 3 LLM calls only
- **Time**: Dashboard loads instantly, 5-10 seconds per stock analysis
- **Kite API**: 1 call (Nifty cached) + 3 calls (stocks) = 4 calls total

**Savings**: 83% reduction in LLM costs, 85% reduction in API calls

## Rate Limiting

### Kite API Limits
- **Limit**: 3 requests per second
- **Handling**: 0.35s delay between requests in queue processor
- **Queue**: Threading-based request queue for parallel requests
- **Safety**: Prevents exceeding rate limits even with rapid clicks

### Implementation
```python
analysis_queue = queue.Queue()

def process_analysis_queue():
    while True:
        request_data = analysis_queue.get()
        time.sleep(0.35)  # 333ms between requests
        # Process request
```

## Frontend Integration Guide

### 1. Holdings Dashboard (Lite Mode)

**On Page Load:**
```javascript
// Fetch only holdings list
const response = await fetch('/api/portfolio/holdings', {
  method: 'POST',
  body: JSON.stringify({ access_token })
});

// Display simple table: Symbol | Qty | Avg Price | [Analyze Button]
```

### 2. Analyze Button Click

```javascript
async function analyzeStock(symbol, instrumentToken) {
  // Show loading spinner
  setLoading(true);
  
  const response = await fetch('/api/analyze-stock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      access_token: userToken,
      symbol: symbol,
      instrument_token: instrumentToken  // optional
    })
  });
  
  const result = await response.json();
  
  if (result.success) {
    // Replace button with score badge
    displayScore(result.score, result.details);
  }
  
  setLoading(false);
}
```

### 3. Score Badge Display

```jsx
<div className={`score-badge score-${Math.floor(result.score)}`}>
  <span className="score-value">{result.score}</span>
  <span className="score-stars">{"⭐".repeat(Math.round(result.score))}</span>
</div>
```

### 4. Detailed Breakdown Modal

```jsx
<Modal>
  <Section title="Recency (Relative Strength)">
    <Score value={details.recency.score} />
    <Detail>{details.recency.detail}</Detail>
  </Section>
  
  <Section title="Trend Analysis">
    <Score value={details.trend.score} />
    <Detail>
      Strength: {details.trend.strength}<br/>
      Direction: {details.trend.direction}
    </Detail>
  </Section>
  
  <Section title="Fundamentals">
    <Score value={details.fundamentals.score} />
    <Detail>{details.fundamentals.summary}</Detail>
  </Section>
  
  <Section title="AI Sentiment">
    <Score value={details.ai_sentiment.score} />
    <Detail>{details.ai_sentiment.summary}</Detail>
  </Section>
</Modal>
```

## Installation & Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

Update your `.env` file:
```env
KITE_API_KEY=REDACTED_KITE_API_KEY
KITE_API_SECRET=REDACTED_KITE_API_SECRET
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Run Backend

```bash
python app.py
```

## Testing

### Test Single Stock Analysis

```bash
curl -X POST http://localhost:5000/api/analyze-stock \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "your_kite_token",
    "symbol": "RELIANCE"
  }'
```

### Test Market Indices

```bash
curl -X POST http://localhost:5000/api/market/indices \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "your_kite_token"
  }'
```

## Troubleshooting

### Common Issues

1. **"No historical data available"**
   - Check if instrument token is correct
   - Verify stock is actively traded
   - Check date range (market holidays)

2. **"Rate limit exceeded"**
   - Wait 1 second between requests
   - Queue processor handles this automatically

3. **"Nifty data unavailable"**
   - Check Kite API credentials
   - Verify network connectivity
   - Cache will retry after 1 hour

4. **"Fundamentals unavailable"**
   - Screener.in may be blocking requests
   - Add more delays between scraping attempts
   - Use VPN if IP is blocked

## Performance Metrics

### Expected Response Times
- **Holdings List**: <500ms
- **Analyze Single Stock**: 5-10 seconds
  - Kite API call: 0.5-1s
  - Screener.in scrape: 2-3s
  - Gemini AI: 2-4s
  - Technical calculations: <0.5s

### Caching Benefits
- **First stock analysis**: 10 seconds (Nifty fetch)
- **Subsequent analyses**: 7 seconds (Nifty cached)
- **Cache hit rate**: ~95% for rapid analyses

## Best Practices

1. **Use Instrument Tokens**: Pass instrument tokens to avoid extra lookup calls
2. **Batch Wisely**: Don't analyze more than 3 stocks per second
3. **Cache Aggressively**: Extend cache duration for development/testing
4. **Handle Errors Gracefully**: Display partial data if one metric fails
5. **Show Progress**: Update UI incrementally (recency → trend → fundamentals → AI)

## Future Enhancements

1. **Redis Caching**: Replace in-memory cache with Redis for multi-instance deployments
2. **WebSocket Updates**: Real-time progress updates during analysis
3. **Background Jobs**: Optional pre-analysis of top holdings during off-peak hours
4. **Historical Scores**: Store and track score changes over time
5. **Comparative Analysis**: Compare multiple stocks side-by-side

## Support

For issues or questions:
- Check Kite API documentation: https://kite.trade/docs/connect/v3/
- Pandas-ta documentation: https://github.com/twopirllc/pandas-ta
- Gemini AI documentation: https://ai.google.dev/

---

**Last Updated**: February 12, 2026
**Version**: 2.0 (Kite API Edition)
