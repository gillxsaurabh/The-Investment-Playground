import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Dict, List, Any
import os
from google import genai


class StockHealthService:
    """Service to analyze stock health based on multiple factors"""
    
    def __init__(self, kite_instance, gemini_api_key=None):
        self.kite = kite_instance
        self.gemini_api_key = gemini_api_key
        self.gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
        self.nifty_data = None
        
    def get_portfolio_health_report(self) -> List[Dict[str, Any]]:
        """
        Main function to generate health report for all holdings
        Returns a list of health reports for each stock
        """
        try:
            # Fetch holdings from Kite
            holdings = self.kite.holdings()
            
            if not holdings:
                return []
            
            # Fetch Nifty 50 data once (for relative strength calculation)
            self._fetch_nifty_data()
            
            # Use parallel execution to process multiple stocks simultaneously
            health_reports = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(self._analyze_stock, holding): holding 
                    for holding in holdings
                }
                
                for future in as_completed(futures):
                    try:
                        report = future.result()
                        if report:
                            health_reports.append(report)
                    except Exception as e:
                        holding = futures[future]
                        print(f"Error analyzing {holding.get('tradingsymbol', 'Unknown')}: {str(e)}")
                        # Add a basic error report
                        health_reports.append({
                            'symbol': holding.get('tradingsymbol', 'Unknown'),
                            'error': str(e),
                            'overall_score': 0
                        })
            
            # Sort by overall score (highest first)
            health_reports.sort(key=lambda x: x.get('overall_score', 0), reverse=True)
            
            return health_reports
            
        except Exception as e:
            raise Exception(f"Error generating health report: {str(e)}")
    
    def _fetch_nifty_data(self):
        """Fetch Nifty 50 data for relative strength calculation"""
        try:
            nifty = yf.Ticker("^NSEI")
            self.nifty_data = nifty.history(period="6mo")
        except Exception as e:
            print(f"Error fetching Nifty data: {str(e)}")
            self.nifty_data = None
    
    def _analyze_stock(self, holding: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single stock and generate health report
        """
        symbol = holding.get('tradingsymbol', '')
        
        # Add small delay to avoid rate limiting
        time.sleep(0.5)
        
        try:
            # Map Kite symbol to yfinance symbol (add .NS for NSE stocks)
            yf_symbol = self._map_to_yfinance_symbol(symbol, holding.get('exchange', ''))
            
            # Fetch data in parallel for this stock
            with ThreadPoolExecutor(max_workers=4) as executor:
                # Submit all tasks
                future_technical = executor.submit(self._get_technical_analysis, yf_symbol, symbol)
                future_fundamental = executor.submit(self._get_fundamental_data, symbol)
                future_ai = executor.submit(self._get_ai_sentiment, symbol)
                
                # Get results
                technical_data = future_technical.result()
                fundamental_data = future_fundamental.result()
                ai_data = future_ai.result()
            
            # Calculate overall health score
            overall_score = self._calculate_overall_score(
                technical_data, fundamental_data, ai_data
            )
            
            # Build the report
            report = {
                'symbol': symbol,
                'company_name': holding.get('tradingsymbol', symbol),
                'current_price': round(holding.get('last_price', 0), 2),
                'quantity': holding.get('quantity', 0),
                'investment': round(holding.get('average_price', 0) * holding.get('quantity', 0), 2),
                'current_value': round(holding.get('last_price', 0) * holding.get('quantity', 0), 2),
                'pnl': round(holding.get('pnl', 0), 2),
                'overall_score': round(overall_score, 1),
                'breakdown': {
                    'momentum_score': technical_data.get('momentum_score', 0),
                    'momentum_detail': technical_data.get('momentum_detail', 'N/A'),
                    'trend_score': technical_data.get('trend_score', 0),
                    'trend_strength': technical_data.get('trend_strength', 'N/A'),
                    'trend_direction': technical_data.get('trend_direction', 'N/A'),
                    'fundamental_score': fundamental_data.get('score', 0),
                    'fundamental_health': fundamental_data.get('summary', 'N/A'),
                    'ai_score': ai_data.get('score', 0),
                    'ai_summary': ai_data.get('summary', 'N/A')
                },
                'last_updated': datetime.now().isoformat()
            }
            
            return report
            
        except Exception as e:
            print(f"Error analyzing {symbol}: {str(e)}")
            raise
    
    def _map_to_yfinance_symbol(self, symbol: str, exchange: str) -> str:
        """Map Kite symbol to yfinance symbol"""
        # Clean the symbol - remove special characters that might cause issues
        clean_symbol = symbol.replace('&', '%26').replace('-', '_')
        
        # Try NSE first (more liquid), fallback to BSE
        if exchange == 'BSE':
            return f"{clean_symbol}.BO"
        else:
            # Default to NSE for most stocks
            return f"{clean_symbol}.NS"
    
    def _get_technical_analysis(self, yf_symbol: str, original_symbol: str) -> Dict[str, Any]:
        """
        Perform technical analysis using yfinance
        Returns momentum score, trend score, and details
        """
        try:
            # Fetch stock data with error handling
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period="6mo")
            
            # If data is insufficient, try alternate exchange
            if df.empty or len(df) < 10:
                if '.BO' in yf_symbol:
                    alternate_symbol = yf_symbol.replace('.BO', '.NS')
                    print(f"Trying alternate exchange: {alternate_symbol}")
                    ticker = yf.Ticker(alternate_symbol)
                    df = ticker.history(period="6mo")
                elif '.NS' in yf_symbol:
                    alternate_symbol = yf_symbol.replace('.NS', '.BO')
                    print(f"Trying alternate exchange: {alternate_symbol}")
                    ticker = yf.Ticker(alternate_symbol)
                    df = ticker.history(period="6mo")
            
            if df.empty or len(df) < 10:
                print(f"No sufficient data for {yf_symbol}")
                return self._default_technical_data()
            
            # Calculate Relative Strength (Momentum Score)
            momentum_score, momentum_detail = self._calculate_momentum(df, original_symbol)
            
            # Calculate Trend (ADX and EMA)
            trend_score, trend_strength, trend_direction = self._calculate_trend(df)
            
            return {
                'momentum_score': momentum_score,
                'momentum_detail': momentum_detail,
                'trend_score': trend_score,
                'trend_strength': trend_strength,
                'trend_direction': trend_direction
            }
            
        except Exception as e:
            print(f"Error in technical analysis for {yf_symbol}: {str(e)}")
            return self._default_technical_data()
    
    def _calculate_momentum(self, df: pd.DataFrame, symbol: str) -> tuple:
        """Calculate momentum score based on relative strength vs Nifty"""
        try:
            if self.nifty_data is None or self.nifty_data.empty:
                return 3, "Nifty data unavailable"
            
            if df.empty or len(df) < 5:
                return 3, "Insufficient stock data"
            
            # Get last 3 months data
            three_months_ago = datetime.now() - timedelta(days=90)
            
            stock_recent = df[df.index >= three_months_ago]
            nifty_recent = self.nifty_data[self.nifty_data.index >= three_months_ago]
            
            if stock_recent.empty or nifty_recent.empty:
                return 3, "Insufficient data"
            
            # Calculate returns
            stock_return = ((stock_recent['Close'].iloc[-1] / stock_recent['Close'].iloc[0]) - 1) * 100
            nifty_return = ((nifty_recent['Close'].iloc[-1] / nifty_recent['Close'].iloc[0]) - 1) * 100
            
            # Score based on relative performance
            if stock_return > nifty_return + 5:
                score = 5
                detail = f"Outperforming Nifty ({stock_return:.1f}% vs {nifty_return:.1f}%)"
            elif stock_return > nifty_return:
                score = 4
                detail = f"Slightly outperforming ({stock_return:.1f}% vs {nifty_return:.1f}%)"
            elif stock_return > nifty_return - 5:
                score = 3
                detail = f"In-line with market ({stock_return:.1f}% vs {nifty_return:.1f}%)"
            else:
                score = 2
                detail = f"Underperforming ({stock_return:.1f}% vs {nifty_return:.1f}%)"
            
            return score, detail
            
        except Exception as e:
            print(f"Error calculating momentum: {str(e)}")
            return 3, "Calculation error"
    
    def _calculate_trend(self, df: pd.DataFrame) -> tuple:
        """Calculate trend score using ADX and EMA"""
        try:
            if df.empty or len(df) < 50:
                return 3, "N/A", "N/A"
            
            # Calculate ADX manually
            current_adx = self._calculate_adx(df, period=14)
            
            if current_adx is None or pd.isna(current_adx):
                return 3, "N/A", "N/A"
            
            # Calculate EMAs manually
            ema_20 = df['Close'].ewm(span=20, adjust=False).mean()
            ema_50 = df['Close'].ewm(span=50, adjust=False).mean()
            
            current_price = df['Close'].iloc[-1]
            current_ema_20 = ema_20.iloc[-1] if ema_20 is not None and not ema_20.empty else None
            current_ema_50 = ema_50.iloc[-1] if ema_50 is not None and not ema_50.empty else None
            
            # Determine trend strength
            if current_adx > 25:
                trend_strength_text = f"Strong (ADX: {current_adx:.1f})"
            elif current_adx > 20:
                trend_strength_text = f"Moderate (ADX: {current_adx:.1f})"
            else:
                trend_strength_text = f"Weak/Sideways (ADX: {current_adx:.1f})"
            
            # Determine trend direction
            if current_ema_20 is not None and current_ema_50 is not None:
                if current_price > current_ema_20 > current_ema_50:
                    trend_direction = "Bullish"
                    trend_score = 5 if current_adx > 25 else 4
                elif current_price < current_ema_20 < current_ema_50:
                    trend_direction = "Bearish"
                    trend_score = 1 if current_adx > 25 else 2
                else:
                    trend_direction = "Mixed"
                    trend_score = 3
            else:
                trend_direction = "N/A"
                trend_score = 3
            
            return trend_score, trend_strength_text, trend_direction
            
        except Exception as e:
            print(f"Error calculating trend: {str(e)}")
            return 3, "N/A", "N/A"
    
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
    def _get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        Scrape fundamental data from Screener.in
        Returns fundamental score and summary
        """
        try:
            # Add delay to avoid rate limiting
            time.sleep(1.0)
            
            url = f"https://www.screener.in/company/{symbol}/consolidated/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract key ratios
            roe = self._extract_ratio(soup, 'ROE')
            debt_to_equity = self._extract_ratio(soup, 'Debt to equity')
            sales_growth = self._extract_ratio(soup, 'Sales growth')
            
            # Calculate score
            score = self._calculate_fundamental_score(roe, debt_to_equity, sales_growth)
            
            # Create summary
            summary = self._create_fundamental_summary(roe, debt_to_equity, sales_growth)
            
            return {
                'score': score,
                'summary': summary,
                'roe': roe,
                'debt_to_equity': debt_to_equity,
                'sales_growth': sales_growth
            }
            
        except Exception as e:
            print(f"Error fetching fundamental data for {symbol}: {str(e)}")
            return {
                'score': 3,
                'summary': "Data unavailable",
                'roe': None,
                'debt_to_equity': None,
                'sales_growth': None
            }
    
    def _extract_ratio(self, soup: BeautifulSoup, ratio_name: str) -> float:
        """Extract a specific ratio from Screener.in HTML"""
        try:
            import re
            # Look for the ratio in multiple sections
            ratios_section = soup.find('ul', {'id': 'top-ratios'})
            if ratios_section:
                for li in ratios_section.find_all('li'):
                    text = li.get_text()
                    if ratio_name.lower() in text.lower():
                        # Find number with % or plain number
                        numbers = re.findall(r'[-+]?\d*\.?\d+', text)
                        if numbers:
                            return float(numbers[-1])
            
            # Try alternative method - look in all text
            page_text = soup.get_text()
            if ratio_name.lower() in page_text.lower():
                # Search around the ratio name
                lines = page_text.split('\n')
                for i, line in enumerate(lines):
                    if ratio_name.lower() in line.lower():
                        # Look in current and next few lines for numbers
                        search_text = ' '.join(lines[i:min(i+3, len(lines))])
                        numbers = re.findall(r'[-+]?\d*\.?\d+', search_text)
                        if numbers:
                            return float(numbers[0])
            
            return None
        except Exception as e:
            print(f"Error extracting {ratio_name}: {str(e)}")
            return None
    
    def _calculate_fundamental_score(self, roe: float, debt_to_equity: float, sales_growth: float) -> int:
        """Calculate fundamental score based on key metrics"""
        score = 3  # Default neutral score
        
        try:
            if roe is not None and debt_to_equity is not None:
                if roe > 15 and debt_to_equity < 1:
                    score = 5
                elif roe > 10 and debt_to_equity < 2:
                    score = 4
                elif roe < 5 or debt_to_equity > 3:
                    score = 1
                elif roe < 10 or debt_to_equity > 2:
                    score = 2
            
            return score
        except:
            return 3
    
    def _create_fundamental_summary(self, roe: float, debt_to_equity: float, sales_growth: float) -> str:
        """Create a human-readable fundamental summary"""
        parts = []
        
        if roe is not None:
            parts.append(f"ROE: {roe:.1f}%")
        
        if debt_to_equity is not None:
            parts.append(f"D/E: {debt_to_equity:.2f}")
        
        if sales_growth is not None:
            parts.append(f"Growth: {sales_growth:.1f}%")
        
        if not parts:
            return "Data unavailable"
        
        return ", ".join(parts)
    
    def _get_ai_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Use AI (Gemini) to analyze news and sentiment for the stock
        Returns AI score and summary
        """
        try:
            if not self.gemini_client:
                return {
                    'score': 3,
                    'summary': "AI analysis unavailable"
                }
            
            # Create prompt for AI
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

            # Call Gemini API with available model
            response = self.gemini_client.models.generate_content(
                model='models/gemini-2.0-flash',
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
                            score = max(1, min(5, score))  # Ensure score is between 1-5
                        except:
                            score = 3
                    elif line.startswith('SUMMARY:'):
                        summary = line.split(':', 1)[1].strip()
            else:
                # Fallback: try to parse the response as is
                summary = response_text[:200]  # Truncate to 200 chars
            
            return {
                'score': score,
                'summary': summary
            }
            
        except Exception as e:
            print(f"Error getting AI sentiment for {symbol}: {str(e)}")
            return {
                'score': 3,
                'summary': "AI analysis unavailable"
            }
    
    def _calculate_overall_score(self, technical: Dict, fundamental: Dict, ai: Dict) -> float:
        """
        Calculate overall health score as weighted average
        Weights: Momentum 25%, Trend 25%, Fundamentals 30%, AI 20%
        """
        momentum_score = technical.get('momentum_score', 3)
        trend_score = technical.get('trend_score', 3)
        fundamental_score = fundamental.get('score', 3)
        ai_score = ai.get('score', 3)
        
        overall = (
            momentum_score * 0.25 +
            trend_score * 0.25 +
            fundamental_score * 0.30 +
            ai_score * 0.20
        )
        
        return overall
    
    def _default_technical_data(self) -> Dict[str, Any]:
        """Return default technical data when analysis fails"""
        return {
            'momentum_score': 3,
            'momentum_detail': 'N/A',
            'trend_score': 3,
            'trend_strength': 'N/A',
            'trend_direction': 'N/A'
        }
