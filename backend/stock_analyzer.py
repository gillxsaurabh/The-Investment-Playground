"""
On-Demand Stock Health Analyzer using Kite API
This service analyzes individual stocks on request, eliminating the need for yfinance.
"""

import pandas as pd
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta
import time
from typing import Dict, Any, Optional
from google import genai
from kiteconnect import KiteConnect


class CachedNiftyData:
    """Simple in-memory cache for Nifty data"""
    def __init__(self):
        self.data = None
        self.timestamp = None
        self.cache_duration = 3600  # 1 hour in seconds
    
    def get_data(self):
        if self.data is not None and self.timestamp is not None:
            # Check if cache is still valid
            if (datetime.now() - self.timestamp).seconds < self.cache_duration:
                return self.data
        return None
    
    def set_data(self, data):
        self.data = data
        self.timestamp = datetime.now()


# Global cache instance
nifty_cache = CachedNiftyData()


class StockAnalyzer:
    """Analyzes individual stocks on-demand using Kite API"""
    
    def __init__(self, kite_instance: KiteConnect, gemini_api_key: Optional[str] = None):
        self.kite = kite_instance
        self.gemini_api_key = gemini_api_key
        self.gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
    
    def analyze_stock(self, symbol: str, instrument_token: Optional[int] = None) -> Dict[str, Any]:
        """
        Analyze a single stock and return health report
        
        Args:
            symbol: Trading symbol (e.g., 'RELIANCE')
            instrument_token: Kite instrument token (optional, will lookup if not provided)
        
        Returns:
            Dictionary with stock health details and score
        """
        try:
            # Get instrument token if not provided
            if not instrument_token:
                instrument_token = self._get_instrument_token(symbol)
                if not instrument_token:
                    raise Exception(f"Could not find instrument token for {symbol}")
            
            # Fetch Nifty data (cached)
            nifty_data = self._get_nifty_data()
            
            # Fetch stock historical data
            stock_data = self._fetch_stock_history(instrument_token, symbol)
            
            if stock_data is None or stock_data.empty:
                raise Exception(f"No historical data available for {symbol}")
            
            # Calculate technical indicators
            technical_score = self._calculate_technical_score(stock_data, nifty_data, symbol)
            
            # Fetch fundamentals
            fundamental_score = self._calculate_fundamental_score(symbol)
            
            # Get AI sentiment
            ai_score = self._get_ai_sentiment(symbol)
            
            # Calculate overall score
            overall_score = self._calculate_overall_score(technical_score, fundamental_score, ai_score)
            
            return {
                'symbol': symbol,
                'score': round(overall_score, 2),
                'details': {
                    'recency': technical_score.get('recency', {}),
                    'trend': technical_score.get('trend', {}),
                    'fundamentals': fundamental_score,
                    'ai_sentiment': ai_score
                },
                'analyzed_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"Error analyzing {symbol}: {str(e)}")
            raise
    
    def _get_instrument_token(self, symbol: str) -> Optional[int]:
        """Get instrument token for a symbol"""
        try:
            # Fetch instruments list (this is cached by kiteconnect internally)
            instruments = self.kite.instruments("NSE")
            
            # Search for the symbol
            for inst in instruments:
                if inst['tradingsymbol'] == symbol:
                    return inst['instrument_token']
            
            return None
        except Exception as e:
            print(f"Error getting instrument token for {symbol}: {str(e)}")
            return None
    
    def _get_nifty_data(self) -> Optional[pd.DataFrame]:
        """Fetch Nifty 50 data with caching"""
        # Check cache first
        cached_data = nifty_cache.get_data()
        if cached_data is not None:
            print("Using cached Nifty data")
            return cached_data
        
        try:
            print("Fetching fresh Nifty data from Kite API")
            # Nifty 50 instrument token
            nifty_token = 256265  # NSE:NIFTY 50
            
            # Fetch 6 months of data
            to_date = datetime.now()
            from_date = to_date - timedelta(days=180)
            
            # Fetch historical data
            nifty_history = self.kite.historical_data(
                nifty_token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day"
            )
            
            if not nifty_history:
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(nifty_history)
            df['date'] = pd.to_datetime(df['date'], utc=True)
            df['date'] = df['date'].dt.tz_localize(None)  # Make timezone-naive
            df.set_index('date', inplace=True)
            
            # Rename columns to standard format
            df = df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })
            
            # Cache the data
            nifty_cache.set_data(df)
            
            return df
        
        except Exception as e:
            print(f"Error fetching Nifty data: {str(e)}")
            return None
    
    def _fetch_stock_history(self, instrument_token: int, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch historical data for a stock using Kite API"""
        try:
            # Add small delay to respect rate limits
            time.sleep(0.2)
            
            # Fetch 6 months of data
            to_date = datetime.now()
            from_date = to_date - timedelta(days=180)
            
            history = self.kite.historical_data(
                instrument_token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day"
            )
            
            if not history:
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(history)
            df['date'] = pd.to_datetime(df['date'], utc=True)
            df['date'] = df['date'].dt.tz_localize(None)  # Make timezone-naive
            df.set_index('date', inplace=True)
            
            # Rename columns to standard format
            df = df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })
            
            return df
        
        except Exception as e:
            print(f"Error fetching history for {symbol}: {str(e)}")
            return None
    
    def _calculate_technical_score(self, stock_data: pd.DataFrame, nifty_data: Optional[pd.DataFrame], symbol: str) -> Dict[str, Any]:
        """Calculate technical analysis scores"""
        try:
            # 1. Calculate Recency (Relative Strength vs Nifty)
            recency_score = 3
            recency_detail = "N/A"
            
            if nifty_data is not None and not nifty_data.empty:
                three_months_ago = datetime.now() - timedelta(days=90)
                
                stock_recent = stock_data[stock_data.index >= three_months_ago]
                nifty_recent = nifty_data[nifty_data.index >= three_months_ago]
                
                if not stock_recent.empty and not nifty_recent.empty and len(stock_recent) > 0 and len(nifty_recent) > 0:
                    stock_return = ((stock_recent['Close'].iloc[-1] / stock_recent['Close'].iloc[0]) - 1) * 100
                    nifty_return = ((nifty_recent['Close'].iloc[-1] / nifty_recent['Close'].iloc[0]) - 1) * 100
                    
                    if stock_return > nifty_return + 5:
                        recency_score = 5
                        recency_detail = f"Strong outperformance: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
                    elif stock_return > nifty_return:
                        recency_score = 4
                        recency_detail = f"Outperforming: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
                    elif stock_return > nifty_return - 5:
                        recency_score = 3
                        recency_detail = f"In-line: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
                    else:
                        recency_score = 2
                        recency_detail = f"Underperforming: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
            
            # 2. Calculate Trend (ADX using manual calculation)
            trend_score = 3
            trend_strength = "N/A"
            trend_direction = "N/A"
            
            if len(stock_data) >= 50:
                # Calculate ADX manually
                current_adx = self._calculate_adx(stock_data, period=14)
                
                if current_adx is not None and pd.notna(current_adx):
                    # Calculate EMAs manually
                    ema_20 = stock_data['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
                    ema_50 = stock_data['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
                    current_price = stock_data['Close'].iloc[-1]
                    
                    # Determine trend strength
                    if current_adx > 25:
                        trend_strength = f"Strong (ADX: {current_adx:.1f})"
                    elif current_adx > 20:
                        trend_strength = f"Moderate (ADX: {current_adx:.1f})"
                    else:
                        trend_strength = f"Weak (ADX: {current_adx:.1f})"
                    
                    # Determine trend direction
                    if pd.notna(ema_20) and pd.notna(ema_50):
                        if current_price > ema_20 > ema_50:
                            trend_direction = "Bullish"
                            trend_score = 5 if current_adx > 25 else 4
                        elif current_price < ema_20 < ema_50:
                            trend_direction = "Bearish"
                            trend_score = 1 if current_adx > 25 else 2
                        else:
                            trend_direction = "Mixed"
                            trend_score = 3
            
            return {
                'recency': {
                    'score': recency_score,
                    'detail': recency_detail
                },
                'trend': {
                    'score': trend_score,
                    'strength': trend_strength,
                    'direction': trend_direction
                }
            }
        
        except Exception as e:
            print(f"Error calculating technical score: {str(e)}")
            return {
                'recency': {'score': 3, 'detail': 'N/A'},
                'trend': {'score': 3, 'strength': 'N/A', 'direction': 'N/A'}
            }
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average Directional Index (ADX) manually
        """
        try:
            high = df['High']
            low = df['Low']
            close = df['Close']
            
            # Calculate True Range (TR)
            high_low = high - low
            high_close = abs(high - close.shift())
            low_close = abs(low - close.shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            
            # Calculate Directional Movement
            plus_dm = high.diff()
            minus_dm = -low.diff()
            
            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm < 0] = 0
            
            # Smooth TR and DM
            tr_smooth = tr.rolling(window=period).sum()
            plus_dm_smooth = plus_dm.rolling(window=period).sum()
            minus_dm_smooth = minus_dm.rolling(window=period).sum()
            
            # Calculate Directional Indicators
            plus_di = 100 * (plus_dm_smooth / tr_smooth)
            minus_di = 100 * (minus_dm_smooth / tr_smooth)
            
            # Calculate DX
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            
            # Calculate ADX (smoothed DX)
            adx = dx.rolling(window=period).mean()
            
            # Return the last ADX value
            return adx.iloc[-1] if not adx.empty else None
            
        except Exception as e:
            print(f"Error calculating ADX: {str(e)}")
            return None
    
    def _calculate_fundamental_score(self, symbol: str) -> Dict[str, Any]:
        """Scrape fundamental data from Screener.in"""
        try:
            # Add delay to avoid rate limiting
            time.sleep(1.0)
            
            url = f"https://www.screener.in/company/{symbol}/consolidated/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract key ratios with multiple search terms
            roe = self._extract_ratio(soup, 'ROE') or self._extract_ratio(soup, 'Return on Equity')
            debt_to_equity = (self._extract_ratio(soup, 'Debt to equity') or 
                            self._extract_ratio(soup, 'D/E') or 
                            self._extract_ratio(soup, 'Debt Equity'))
            sales_growth = (self._extract_ratio(soup, 'Sales growth') or 
                          self._extract_ratio(soup, 'Revenue growth') or
                          self._extract_ratio(soup, 'Sales CAGR'))
            
            # Calculate score (improved logic for missing data)
            score = 3  # Default neutral
            
            if roe is not None:
                if debt_to_equity is not None:
                    # Both ROE and D/E available - use full logic
                    if roe > 15 and debt_to_equity < 1:
                        score = 5
                    elif roe > 10 and debt_to_equity < 2:
                        score = 4
                    elif roe < 5 or debt_to_equity > 3:
                        score = 1
                    elif roe < 10 or debt_to_equity > 2:
                        score = 2
                else:
                    # Only ROE available - score based on ROE alone
                    if roe > 15:
                        score = 4  # Good, but can't confirm low debt
                    elif roe > 10:
                        score = 3  # Average
                    elif roe < 5:
                        score = 2  # Below average
                    else:
                        score = 3  # Neutral
            elif debt_to_equity is not None:
                # Only D/E available - score based on debt levels
                if debt_to_equity < 1:
                    score = 4  # Low debt is good
                elif debt_to_equity < 2:
                    score = 3  # Moderate debt
                else:
                    score = 2  # High debt is concerning
            
            # Create summary
            summary_parts = []
            if roe is not None:
                summary_parts.append(f"ROE: {roe:.1f}%")
            if debt_to_equity is not None:
                summary_parts.append(f"D/E: {debt_to_equity:.2f}")
            if sales_growth is not None:
                summary_parts.append(f"Growth: {sales_growth:.1f}%")
            
            summary = ", ".join(summary_parts) if summary_parts else "Data unavailable"
            
            return {
                'score': score,
                'summary': summary,
                'roe': roe,
                'debt_to_equity': debt_to_equity,
                'sales_growth': sales_growth
            }
        
        except Exception as e:
            print(f"Error fetching fundamentals for {symbol}: {str(e)}")
            return {
                'score': 3,
                'summary': "Data unavailable - scraping failed",
                'error': str(e)
            }
    
    def _extract_ratio(self, soup: BeautifulSoup, ratio_name: str) -> Optional[float]:
        """Extract a specific ratio from Screener.in HTML"""
        try:
            import re
            
            # Look for the ratio in the top-ratios section
            ratios_section = soup.find('ul', {'id': 'top-ratios'})
            if ratios_section:
                for li in ratios_section.find_all('li'):
                    text = li.get_text()
                    if ratio_name.lower() in text.lower():
                        numbers = re.findall(r'[-+]?\d*\.?\d+', text)
                        if numbers:
                            return float(numbers[-1])
            
            # Fallback: search in all text
            page_text = soup.get_text()
            if ratio_name.lower() in page_text.lower():
                lines = page_text.split('\n')
                for i, line in enumerate(lines):
                    if ratio_name.lower() in line.lower():
                        search_text = ' '.join(lines[i:min(i+3, len(lines))])
                        numbers = re.findall(r'[-+]?\d*\.?\d+', search_text)
                        if numbers:
                            return float(numbers[0])
            
            return None
        
        except Exception as e:
            print(f"Error extracting {ratio_name}: {str(e)}")
            return None
    
    def _get_ai_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get AI sentiment analysis using Gemini"""
        try:
            if not self.gemini_client:
                return {
                    'score': 3,
                    'summary': "AI analysis unavailable - no API key"
                }
            
            prompt = f"""Analyze the stock {symbol} listed on Indian stock exchanges (NSE/BSE).

Based on recent news, quarterly results, and market sentiment:
1. Provide a brief sentiment summary (1-2 sentences)
2. Give a score from 1-5 where:
   - 5 = Strong positive outlook (high growth, good governance, strong financials)
   - 4 = Positive outlook
   - 3 = Neutral/Mixed signals
   - 2 = Negative concerns (governance issues, declining performance)
   - 1 = High risk (bankruptcy concerns, major red flags)

Focus on: Recent capex, governance quality, profitability trends, and regulatory updates.

Return your response in this exact format:
SCORE: [number]
SUMMARY: [your 1-2 sentence summary]"""

            # Call Gemini API
            response = self.gemini_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            
            # Parse response
            response_text = response.text
            
            score = 3
            summary = "Analysis unavailable"
            
            if "SCORE:" in response_text and "SUMMARY:" in response_text:
                lines = response_text.strip().split('\n')
                for line in lines:
                    if line.startswith('SCORE:'):
                        try:
                            score = int(line.split(':')[1].strip())
                            score = max(1, min(5, score))
                        except:
                            score = 3
                    elif line.startswith('SUMMARY:'):
                        summary = line.split(':', 1)[1].strip()
            else:
                summary = response_text[:200]
            
            return {
                'score': score,
                'summary': summary
            }
        
        except Exception as e:
            print(f"Error getting AI sentiment for {symbol}: {str(e)}")
            return {
                'score': 3,
                'summary': "AI analysis failed"
            }
    
    def _calculate_overall_score(self, technical: Dict, fundamental: Dict, ai: Dict) -> float:
        """
        Calculate overall health score
        Weights: Recency 25%, Trend 25%, Fundamentals 30%, AI 20%
        """
        recency_score = technical.get('recency', {}).get('score', 3)
        trend_score = technical.get('trend', {}).get('score', 3)
        fundamental_score = fundamental.get('score', 3)
        ai_score = ai.get('score', 3)
        
        overall = (
            recency_score * 0.25 +
            trend_score * 0.25 +
            fundamental_score * 0.30 +
            ai_score * 0.20
        )
        
        return overall
