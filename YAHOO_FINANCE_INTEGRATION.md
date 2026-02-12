# Yahoo Finance Integration - Indian Stock Market Tracking

## Overview
This document describes the Yahoo Finance integration added to CogniCap for tracking Indian stock market data.

## New Features

### 1. Market Watch Tab
A new "Market Watch" tab has been added to the dashboard with the following features:

#### Market Indices
- **NIFTY 50**: Real-time index value with daily change percentage
- **SENSEX**: Real-time index value with daily change percentage
- Both indices show:
  - Current value
  - Day's change (absolute and percentage)
  - Day's high and low

#### Top Stocks
- **Top 10 Gainers**: Stocks with highest percentage gain today from Nifty 50
- **Top 10 Losers**: Stocks with highest percentage loss today from Nifty 50
- Each stock displays:
  - Symbol
  - Current price
  - Day's change (absolute and percentage)

### 2. Dashboard Tabs
The dashboard now features two tabs:
- **Tab 1 - My Portfolio**: Original portfolio view (unchanged)
  - Total investment
  - Current value
  - Total P&L
  - Holdings table
  - Top performers from your portfolio
  
- **Tab 2 - Market Watch**: New market tracking view
  - Market indices (Nifty 50, Sensex)
  - Top 10 gainers
  - Top 10 losers

## Technical Implementation

### Backend Changes

#### New Dependencies
- `yfinance==0.2.36` - Yahoo Finance API client
- `pandas` - Data manipulation (dependency of yfinance)

#### New API Endpoints

1. **GET /api/market/indices**
   - Returns current data for Nifty 50 and Sensex
   - Response includes: value, change, change_percent, high, low, volume
   - No authentication required

2. **GET /api/market/top-stocks**
   - Returns top 10 gainers and losers from Nifty 50
   - Response includes: symbol, name, price, change, change_percent, volume, high, low
   - No authentication required

### Frontend Changes

#### New Components

1. **MarketComponent** (`src/app/components/market/`)
   - `market.component.ts` - Component logic
   - `market.component.html` - Template with indices and stock tables
   - `market.component.scss` - Styling for market view

#### Updated Components

1. **DashboardComponent**
   - Added tab navigation
   - Added `activeTab` state management
   - Imports MarketComponent

2. **KiteService**
   - New interfaces: `MarketIndex`, `MarketIndices`, `Stock`, `TopStocks`
   - New methods:
     - `getMarketIndices(): Observable<MarketIndices>`
     - `getTopStocks(): Observable<TopStocks>`

## File Changes Summary

### Modified Files
- `backend/requirements.txt` - Added yfinance dependency
- `backend/app.py` - Added market data endpoints
- `frontend/cognicap-app/src/app/services/kite.service.ts` - Added market data methods
- `frontend/cognicap-app/src/app/components/dashboard/dashboard.component.ts` - Added tab functionality
- `frontend/cognicap-app/src/app/components/dashboard/dashboard.component.html` - Added tab UI
- `frontend/cognicap-app/src/app/components/dashboard/dashboard.component.scss` - Added tab styles

### New Files
- `frontend/cognicap-app/src/app/components/market/market.component.ts`
- `frontend/cognicap-app/src/app/components/market/market.component.html`
- `frontend/cognicap-app/src/app/components/market/market.component.scss`
- `backend/test_market_api.py` - Test script for market API endpoints

## Installation & Setup

### 1. Install Backend Dependencies
```bash
cd backend
source venv/bin/activate
pip install yfinance==0.2.36
```

### 2. No Frontend Changes Required
The frontend already has all necessary dependencies (Angular, RxJS, etc.)

### 3. Start the Application
```bash
# From project root
./start.sh
```

Or manually:
```bash
# Terminal 1 - Backend
cd backend
source venv/bin/activate
python3 app.py

# Terminal 2 - Frontend
cd frontend/cognicap-app
npm start
```

### 4. Access the Application
- Open browser: http://localhost:4200
- Login with your Zerodha credentials
- Navigate between "My Portfolio" and "Market Watch" tabs

## Testing

### Test Backend Endpoints
```bash
cd backend
source venv/bin/activate

# Make sure backend is running in another terminal
python test_market_api.py
```

Expected output:
- Nifty 50 and Sensex current values with changes
- Top 3 gainers and losers with their prices and change percentages

### Manual Testing Checklist
- [ ] Backend starts without errors
- [ ] Frontend compiles successfully
- [ ] "Market Watch" tab appears in dashboard
- [ ] Clicking tabs switches between views
- [ ] Market indices load and display correctly
- [ ] Top gainers and losers load and display correctly
- [ ] All existing portfolio functionality still works

## Data Sources

### Yahoo Finance Tickers
- **Nifty 50**: `^NSEI`
- **Sensex**: `^BSESN`
- **Nifty 50 Stocks**: Individual stocks with `.NS` suffix (e.g., `RELIANCE.NS`)

### Data Refresh
- Market data is fetched on component load
- Can be refreshed manually using the "Refresh" button (portfolio tab only currently)
- Consider adding auto-refresh every 5 minutes (future enhancement)

## Known Limitations

1. **Market Data Delay**: Yahoo Finance provides delayed market data (typically 15-20 minutes)
2. **Rate Limiting**: Yahoo Finance may rate limit requests if too many are made in short time
3. **Market Hours**: Data is most accurate during market hours (9:15 AM - 3:30 PM IST)
4. **Nifty 50 Stocks**: Only shows top gainers/losers from Nifty 50 stocks (not entire NSE)

## Future Enhancements

- [ ] Add auto-refresh capability for market data
- [ ] Add more indices (Bank Nifty, Nifty IT, etc.)
- [ ] Add sector-wise performance
- [ ] Add search functionality for specific stocks
- [ ] Add stock charts and historical data
- [ ] Add market sentiment indicators
- [ ] Cache market data to reduce API calls

## Troubleshooting

### Backend Errors

**Issue**: `ModuleNotFoundError: No module named 'yfinance'`
```bash
cd backend
source venv/bin/activate
pip install yfinance==0.2.36
```

**Issue**: Market data not loading
- Check if backend is running on port 5000
- Check backend logs for Yahoo Finance API errors
- Verify internet connection

### Frontend Errors

**Issue**: "Property 'getMarketIndices' does not exist"
- Clear browser cache
- Restart Angular dev server: `npm start`

**Issue**: CORS errors
- Verify backend CORS is enabled (flask-cors installed)
- Check backend is running on port 5000

## Support

For issues or questions:
1. Check backend logs: `backend/app.py` output
2. Check browser console for frontend errors
3. Test API endpoints using `test_market_api.py`
4. Verify all dependencies are installed correctly

---

**Integration completed**: February 12, 2026
**Version**: 1.0.0
