# 🌡️ Kalshi Temperature Market Monitor

Real-time monitoring script that captures snapshots of ALL temperature markets on Kalshi every 30 seconds.

## 🔐 Authentication Setup

**Required**: You need Kalshi API credentials to use this monitor.

### Option 1: Environment Variables
```bash
export KALSHI_API_KEY="your-key-id"
export KALSHI_PRIVATE_KEY_FILE="/path/to/private_key.pem"
```

### Option 2: .env File  
Create a `.env` file in the `kalshi_monitor/` directory:
```
KALSHI_API_KEY=your-key-id
KALSHI_PRIVATE_KEY_FILE=path/to/private_key.pem
```

### Getting API Credentials
1. Sign up at [kalshi.com](https://kalshi.com)
2. Log into your account
3. Go to **Account Settings** → **Profile Settings**
4. Click **"Create New API Key"**
5. Save the **Key ID** and **Private Key** (RSA format)
6. **Important**: Private key is only shown once - save it immediately!

## 🚀 Quick Start

```bash
cd kalshi_monitor
# Set up credentials (see above)
python3 kalshi_temperature_monitor.py
```

## 📊 What It Does

- **Monitors ALL temperature markets** (HIGH, LOW, TEMP tickers) across all cities/locations
- **Captures market snapshots every 30 seconds** including:
  - Current bid/ask prices
  - Last traded price
  - Volume and open interest
  - Market status and expiration times
- **Saves to daily CSV files** in `data/` directory
- **Runs continuously** until stopped with Ctrl+C

## 📁 Output Files

Data is saved to daily CSV files:
```
data/
├── kalshi_temp_markets_20250805.csv
├── kalshi_temp_markets_20250806.csv
├── monitor.log
└── ...
```

## 📋 CSV Columns

Each snapshot includes:
- `timestamp` - UTC timestamp of snapshot
- `ticker` - Market ticker (e.g., KXHIGHNY-25AUG05)
- `title` - Full market title
- `subtitle` - Temperature range/threshold
- `event_ticker` - Event identifier
- `status` - Market status (open/closed/settled)
- `close_time` - When trading closes
- `expiration_time` - When market settles
- `last_price` - Last traded price ($)
- `yes_ask` / `yes_bid` - Current YES prices
- `no_ask` / `no_bid` - Current NO prices
- `volume` - Total volume
- `volume_24h` - 24-hour volume
- `open_interest` - Open positions
- `liquidity` - Market liquidity metric
- `dollar_volume_24h` - 24h dollar volume
- `result` - Settlement result (if settled)
- `settlement_value` - Final settlement price

## 🔧 Configuration

Edit the script to customize:
- **Monitoring interval**: Change `interval_seconds=30` in `main()`
- **API endpoint**: Modify `api_base` in `KalshiTempMonitor.__init__()`
- **Market filters**: Adjust `temp_keywords` in `get_temperature_markets()`

## 🛑 Stopping

Press `Ctrl+C` to stop monitoring gracefully. The script will finish the current cycle and save any pending data.

## 📝 Logs

Monitor activity is logged to:
- Console output
- `data/monitor.log` file

## ⚡ Performance

- Each cycle takes ~2-5 seconds depending on number of markets
- Uses minimal CPU/memory
- Automatically handles API rate limits and errors
- Graceful shutdown preserves all data

## 🔍 Example Usage

```bash
# Start monitoring
python3 kalshi_temperature_monitor.py

# Output:
🌡️ Kalshi Temperature Market Monitor
==================================================
🚀 Starting Kalshi temperature monitoring (every 30s)
📂 Data will be saved to: /path/to/data
🛑 Press Ctrl+C to stop
📊 Found 45 temperature markets out of 234 total
💾 Saved 45 market snapshots to kalshi_temp_markets_20250805.csv
📈 Cycle complete: 45 active markets, avg price: $0.42
⏱️ Cycle took 3.2s, sleeping 26.8s...
```

## 🚨 Important Notes

- **No Authentication Required** - Uses public API endpoints
- **Rate Limiting** - Script handles API limits automatically  
- **Data Persistence** - Each day creates a new CSV file
- **All Markets** - Captures temperature markets for ALL cities, not just NYC
- **Real-time** - Perfect for capturing pre-expiration market sentiment

## 💡 Analysis Ideas

With this continuous data, you can:
- Track how market prices change as expiration approaches
- Compare market confidence vs actual weather outcomes
- Identify the best times to enter/exit positions
- Analyze market efficiency across different cities
- Build predictive models using pre-close market data