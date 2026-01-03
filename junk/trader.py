import time
import logging
from datetime import datetime
import pandas as pd
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trader.log"),
        logging.StreamHandler()
    ]
)

class PaperTrader:
    def __init__(self, strategy):
        self.strategy = strategy
        self.positions = {}
        self.capital = 10000.0
        
    def get_live_weather(self):
        # Fetch from AWC (Fresher)
        try:
            url = "https://aviationweather.gov/api/data/metar?ids=KNYC&format=json"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data:
                    temp_c = data[0]['temp']
                    if temp_c is not None:
                        return (temp_c * 9/5) + 32
        except Exception as e:
            logging.error(f"Error fetching weather: {e}")
        return None


    def get_live_markets(self):
        # Fetch from Kalshi Public API
        try:
            url = "https://api.elections.kalshi.com/trade-api/v2/markets"
            params = {"series_ticker": "KXHIGHNY", "status": "open", "limit": 100}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                return response.json().get("markets", [])
        except Exception as e:
            logging.error(f"Error fetching markets: {e}")
        return []

    def run(self):
        logging.info("Starting Paper Trader...")
        while True:
            try:
                self.tick()
                time.sleep(60) # Run every minute
            except KeyboardInterrupt:
                logging.info("Stopping Trader...")
                break
            except Exception as e:
                logging.error(f"Error in tick: {e}")
                time.sleep(60)

    def tick(self):
        current_temp = self.get_live_weather()
        if current_temp is None:
            return
            
        markets = self.get_live_markets()
        if not markets:
            return
            
        logging.info(f"Current Temp: {current_temp:.1f}F | Active Markets: {len(markets)}")
        
        for market in markets:
            ticker = market['ticker']
            
            # Check strategy
            signal = self.strategy.on_tick(market, current_temp)
            
            if signal == "BUY_YES":
                self.execute_trade(ticker, "YES", market)
            elif signal == "BUY_NO":
                self.execute_trade(ticker, "NO", market)
                
    def execute_trade(self, ticker, side, market):
        # Paper Trade Logic
        # If Buying YES, we pay yes_ask
        # If Buying NO, we pay no_ask
        price = market.get('yes_ask') if side == "YES" else market.get('no_ask')
        if not price:
            return
            
        qty = 10 # Fixed size
        cost = price * qty / 100.0
        
        if self.capital >= cost:
            self.capital -= cost
            self.positions[ticker] = self.positions.get(ticker, 0) + qty
            logging.info(f"TRADE: Bought {qty} {side} {ticker} @ {price} cents. Capital: ${self.capital:.2f}")

if __name__ == "__main__":
    class CompoundingStrategy:
        def on_tick(self, market, current_temp):
            strike_type = market.get('strike_type')
            floor = market.get('floor_strike')
            cap = market.get('cap_strike')
            
            # We need the market price to make a decision
            # But on_tick in trader.py currently only takes market and temp
            # The market dict contains 'yes_ask' and 'no_ask'
            
            # 1. "High < X" (Less) -> Buy NO if Temp > Cap
            if strike_type == 'less' and cap is not None:
                if current_temp > cap:
                    # Check Price: We want NO price < 99 (YES price > 1)
                    # In trader.py, we buy NO at 'no_ask'.
                    # So we want no_ask <= 99.
                    no_ask = market.get('no_ask')
                    if no_ask and no_ask <= 99:
                        return "BUY_NO"

            # 2. "High > X" (Greater) -> Buy YES if Temp > Floor
            if strike_type == 'greater' and floor is not None:
                if current_temp > floor:
                    # Check Price: We want YES price <= 99
                    yes_ask = market.get('yes_ask')
                    if yes_ask and yes_ask <= 99:
                        return "BUY_YES"
            
            return "HOLD"

    trader = PaperTrader(CompoundingStrategy())
    trader.run()
