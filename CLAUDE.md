# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This repository contains temperature monitoring and analysis tools for NYC weather data, specifically designed to support analysis related to Kalshi's temperature prediction markets (NHIGH contracts). The project focuses on tracking daily maximum temperatures at Central Park, NYC (KNYC station) as specified in the Kalshi trading rules.

## Data Sources and Architecture

The codebase implements multiple weather data collection strategies:

### Primary Data Sources
- **NWS API**: Official National Weather Service observations API (`api.weather.gov`)
- **Synoptic API**: High-frequency weather data service with 5-minute granularity
- **NCEI ASOS**: Historical 5-minute ASOS data files from NOAA's archive

### Core Concept: Climate Days
All scripts implement "climate day" logic where a meteorological day runs from 00:00 LST to the next 00:00 LST. During Daylight Saving Time, this means the climate day ends at 01:00 local clock time to maintain 24-hour periods.

### Station Coverage
- **KNYC**: Central Park (primary settlement station for Kalshi)
- **KLGA**: LaGuardia Airport  
- **KJFK**: JFK Airport
- **KEWR**: Newark Airport
- **KTEB**: Teterboro Airport

## Key Scripts and Functionality

### Temperature Data Collection
- `nws_api_climate_daily_peaks.py`: Fetches daily temperature peaks from NWS API for multiple NYC stations over the last 7 climate days
- `synoptic_5min_7day_climate_plots.py`: Creates individual daily plots and overlay analysis using Synoptic's 5-minute data
- `nws_api_7day_temperature_plots.py`: Generates temperature plots from 7 days of NWS API data

### Data Processing
- `ncei_asos_5min_data_parser.py`: Parses raw NCEI ASOS 5-minute data files with complex regex-based record extraction
- `ncei_asos_daily_temperature_plots.py`: Creates daily temperature visualizations from parsed NCEI data
- `data_dl.py`: Downloads ASOS data files from NCEI servers

## API Credentials and Configuration

### Synoptic API
- Token required: `SYNOPTIC_TOKEN` (currently hardcoded in synoptic_5min_7day_climate_plots.py)
- Base URL: `https://api.synopticdata.com/v2/stations/timeseries`

### NWS API
- No authentication required
- Uses User-Agent: `"nyc-temp-check (you@example.com)"`
- Rate limiting: Built-in pagination handling

## Temperature Analysis Patterns

### Peak Detection
Scripts calculate daily temperature peaks and include:
- Exact peak temperature and timestamp
- Rounded temperature (for betting strike prices)
- Delta to next 0.5°F increment (trading edge analysis)

### Data Quality
- Temperature bounds: -80°F to 130°F (sanity filtering)
- Quality control flags: Only accepts "V" (valid) or "C" (corrected) data from NWS
- Missing data handling: Scripts gracefully handle API failures and missing observations

## Timezone Handling

All scripts use `zoneinfo.ZoneInfo("America/New_York")` for proper DST handling. Temperature timestamps are consistently converted to local NYC time for analysis and display.

## File Naming Convention

Scripts follow the pattern: `[datasource]_[frequency]_[purpose].py`
- Data source: `nws_api`, `synoptic`, `ncei_asos`  
- Frequency: `5min`, `7day`, `daily`
- Purpose: `plots`, `parser`, `peaks`, `climate`

## Kalshi Trading Context

Reference `KALSHI_RULES.txt` for official contract specifications. Key points:
- Settlement based on NWS Daily Climate Report for Central Park
- Temperature reported in Fahrenheit with 1-degree increments
- Data revisions after expiration are not considered
- Contract expiration typically 7-8 AM ET following data release

## Output Files

- `nyc_synoptic_5min_backtest.csv`: Historical backtest data
- `nyc_synoptic_5min_peaks_wide.csv`: Wide-format comparison data
- `asos_5min_data/`: Directory for downloaded NCEI files