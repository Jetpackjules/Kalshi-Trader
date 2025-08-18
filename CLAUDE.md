# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This repository contains temperature monitoring and analysis tools for NYC weather data, specifically designed to support analysis related to Kalshi's temperature prediction markets (NHIGH contracts). The project focuses on tracking daily maximum temperatures at Central Park, NYC (KNYC station) as specified in the Kalshi trading rules.

## Common Development Commands

### Testing APIs
- `python3 simple_api_test.py` - Quick test of all three weather APIs for a single date
- `python3 debug_api_test.py` - Comprehensive test across date ranges with detailed logging
- `python3 test_asos_fix.py` - Specific test for ASOS timezone fix validation

### Analysis and Comparison  
- `python3 kalshi_comparison.py` - Compare weather APIs against Kalshi settlement data
- `python3 api_deviance_analysis.py` - Comprehensive API performance analysis with deviance calculations
- `python3 kalshi_vs_actual_temps_simple.py` - Two-number comparison of Kalshi settlements vs weather APIs
- `python3 kalshi_visual_analysis.py` - Generate comprehensive visualizations of market analysis

### Kalshi Trading Integration
- `python3 kalshi_historical_price_analysis.py` - Analyze historical market prices before expiration using candlestick data
- `python3 test_kalshi_auth.py` - Test Kalshi API authentication and connectivity
- `python3 check_active_markets.py` - Check for currently active temperature markets
- `cd kalshi_monitor && python3 kalshi_temperature_monitor.py` - Real-time market monitoring (requires API credentials)

### Candlestick Data Generation
- `python3 BACKLOG!/kalshi_temp_backtest.py --outdir ./data --days 30 --interval 5m` - Generate comprehensive candlestick data for visualization
- Outputs to `data/candles/KXHIGHNY_candles_5m.csv` with OHLC market data

### Web Visualization
- `python3 -m http.server 8080` - Start local web server for market visualization
- Access via `http://localhost:8080/kalshi_market_viewer_with_timelines.html`
- Static versions available: `kalshi_market_viewer_static.html` for offline use
- `python3 test_website.py` - Test website functionality and data loading

### Environment Setup
- Virtual environment located in `venv/` directory
- Activate with `source venv/bin/activate` (if using virtual environment)
- Key dependencies: pandas, requests, plotly.js (CDN), modules in `modules/` directory

## Code Architecture

### Modular API Design
The codebase uses a modular architecture with all weather APIs inheriting from `BaseWeatherAPI`:

**Core Module Structure:**
- `modules/base_api.py` - Abstract base class (`BaseWeatherAPI`) providing common functionality
- `modules/nws_api.py` - NWS API implementation (`NWSAPI` class) with aggressive data fetching
- `modules/synoptic_api.py` - Synoptic API (`SynopticAPI` class) for high-frequency data
- `modules/ncei_asos.py` - NCEI ASOS (`NCEIASOS` class) historical data with UTC timezone handling
- `modules/kalshi_nws_source.py` - Official NWS source (`KalshiNWSSource` class) matching Kalshi settlement
- `modules/kalshi_api.py` - Kalshi trading API integration (`KalshiAPI` class)

**Key Design Patterns:**
- All APIs implement `get_daily_max_temperature(target_date)` method
- Common climate day logic handled in base class
- Timezone-aware datetime handling throughout
- Robust error handling with fallback strategies

### Data Sources and Architecture

#### Primary Data Sources
- **NWS API**: Official National Weather Service observations API (`api.weather.gov`)
- **Synoptic API**: High-frequency weather data service with 5-minute granularity  
- **NCEI ASOS**: Historical 5-minute ASOS data files from NOAA's archive
- **Kalshi NWS Source**: Official settlement data source for trading validation

#### Core Concept: Climate Days
All scripts implement "climate day" logic where a meteorological day runs from 00:00 LST to the next 00:00 LST. During Daylight Saving Time, this means the climate day ends at 01:00 local clock time to maintain 24-hour periods.

#### Critical Timezone Handling
**NCEI ASOS**: Data timestamps are in UTC format, requiring UTC day bounds (00:00 UTC to 24:00 UTC) rather than local climate day conversion. This was a major bug fix - previous attempts to convert local climate windows to UTC bounds failed.

### Station Coverage
- **KNYC**: Central Park (primary settlement station for Kalshi)
- **KLGA**: LaGuardia Airport  
- **KJFK**: JFK Airport
- **KEWR**: Newark Airport
- **KTEB**: Teterboro Airport

## Legacy Scripts (Deprecated)

The `legacy_scripts/` directory contains standalone scripts that have been superseded by the modular API architecture:
- `nws_api_climate_daily_peaks.py` - Replaced by `modules/nws_api.py`
- `synoptic_5min_7day_climate_plots.py` - Replaced by `modules/synoptic_api.py`
- `ncei_asos_5min_data_parser.py` - Replaced by `modules/ncei_asos.py`

## API Credentials and Configuration

### Synoptic API
- Token required: `SYNOPTIC_TOKEN` (currently hardcoded in modules/synoptic_api.py)
- Base URL: `https://api.synopticdata.com/v2/stations/timeseries`

### NWS API
- No authentication required
- Uses User-Agent: `"nyc-temp-check (you@example.com)"`
- Rate limiting: Built-in pagination handling
- Aggressive data fetching with extended time windows and fallback strategies

### NCEI ASOS
- No authentication required
- Downloads 5-minute data files from NCEI servers
- Files cached locally in `asos_5min_data/` directory
- Automatic file completeness validation and re-download

### Kalshi API
- **Base URL**: `https://api.elections.kalshi.com/trade-api/v2`
- **Authentication**: RSA private key signing required
- **Credentials**: Set `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_FILE` environment variables
- **Key Endpoints**:
  - `/events` - Get all active markets and events
  - `/series/{series}/markets/{ticker}/candlesticks` - Historical OHLC price data
- **Rate Limiting**: Built-in handling with authentication headers regeneration
- **Candlestick Data**: Supports 1-minute, 1-hour, and 1-day intervals

## Temperature Analysis Patterns

### Peak Detection
All APIs use consistent peak detection via `BaseWeatherAPI.find_daily_peak()`:
- Exact peak temperature and timestamp
- Rounded temperature (for betting strike prices)
- Observation count for data quality assessment
- Source tracking for comparative analysis

### Data Quality and Validation
- Temperature bounds: -80°F to 130°F (sanity filtering)
- Quality control flags: NWS APIs only accept "V" (valid) or "C" (corrected) data
- Missing data handling: Graceful error handling with detailed logging
- Aggressive retry logic for incomplete or missing data

### Timezone Handling
All scripts use `zoneinfo.ZoneInfo("America/New_York")` for proper DST handling. **Critical**: NCEI ASOS data requires special UTC handling - timestamps are in UTC and must use UTC day bounds rather than converted local climate day windows.

## Kalshi Trading Context

Reference `analysis/KALSHI_RULES.txt` for official contract specifications. Key points:
- Settlement based on NWS Daily Climate Report for Central Park (KNYC)
- Temperature reported in Fahrenheit with 1-degree increments
- Data revisions after expiration are not considered  
- Contract expiration typically 7-8 AM ET following data release
- Settlement data accessible at: https://www.weather.gov/wrh/climate?wfo=okx

### Trading Analysis Components
- `modules/kalshi_nws_source.py` - Official settlement data source
- `kalshi_comparison.py` - API vs settlement comparison
- `api_deviance_analysis.py` - API performance ranking with deviance calculations
- `kalshi_historical_price_analysis.py` - Pre-expiration market price analysis using candlestick data
- `kalshi_monitor/` - Real-time market monitoring system with authentication

## Data Storage and Output

### Generated Files
- `debug_api_results.csv` - API test results across date ranges
- `weather_apis_comparison.csv` - Cross-API temperature comparisons
- `kalshi_vs_weather_comparison.csv` - Settlement vs weather API analysis
- `kalshi_temperature_markets.csv` - Market data extracts
- `api_performance_summary.csv` - API ranking by accuracy and deviance metrics
- `api_deviance_detailed_results.csv` - Detailed per-day API performance analysis
- `kalshi_historical_prices_YYYYMMDD_HHMM.csv` - Historical market price snapshots
- `kalshi_monitor/data/kalshi_temp_markets_YYYYMMDD.csv` - Real-time market monitoring data

### Data Directories  
- `asos_5min_data/` - Downloaded NCEI ASOS files (cached)
- `data/candles/` - Generated candlestick data for market visualization
- `data/raw/` - Raw candlestick JSON files per market ticker
- `kalshi_monitor/data/` - Real-time market monitoring data and logs
- `legacy_scripts/` - Deprecated standalone scripts (superseded by modular architecture)
- `BACKLOG!/` - Contains backtest utilities and requirements

### Interactive Visualization System
The project includes a comprehensive web-based visualization system:

**Core Visualization Files:**
- `kalshi_market_viewer_with_timelines.html` - **Primary visualization** with full temperature curves and market trendlines
- `kalshi_market_viewer_static.html` - Static version with embedded temperature data (no API dependencies)
- `kalshi_market_viewer.html` - Original version with basic temperature overlays

**Visualization Architecture:**
- **Market Data**: Loaded from `data/candles/KXHIGHNY_candles_5m.csv` containing OHLC candlestick data
- **Temperature Integration**: Dual y-axis charts showing market prices ($0-1) vs temperature curves (60-105°F)
- **Real-time Toggles**: Interactive controls for Synoptic API (orange) and ASOS (blue) temperature overlays
- **Timeline Analysis**: Full 24-hour temperature curves showing morning lows, afternoon peaks, and evening cooling

**Data Flow for Visualization:**
1. Generate candlestick data: `python3 BACKLOG!/kalshi_temp_backtest.py --outdir ./data --days 30 --interval 5m`
2. Start web server: `python3 -m http.server 8080`
3. Access visualization: `http://localhost:8080/kalshi_market_viewer_with_timelines.html`
4. Select date → Load market data → View market efficiency vs actual temperature curves

### Log Files
- `kalshi_monitor/data/monitor.log` - Real-time market monitoring logs
- Various PNG files - Generated visualizations (market analysis, API performance charts)