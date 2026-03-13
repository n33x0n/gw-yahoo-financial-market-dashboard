# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Yahoo Financial Market Dashboard — Python scraper that downloads financial data from multiple sources (Yahoo Finance, Stooq.pl, NBP) and outputs a single CSV file (`scraped-data.csv`). A standalone HTML dashboard (`index.html` + `dashboard.css`) visualizes the CSV data using Chart.js and Papa Parse.

## Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the scraper
python3 scraper-yahoo-finance-all.py

# Run via wrapper script (creates logs/, logs output)
./run_yahoo-finance-all.sh
```

No tests, no linter, no build step. The project is a single Python script + static HTML dashboard.

## Architecture

### Data Pipeline (`scraper-yahoo-finance-all.py`)
Single-file scraper with three data sources, each with its own fetch function:
- **Yahoo Finance** (`fetch_with_backoff`) — uses `yfinance` with exponential backoff for rate limiting. Configured via `TICKER_CONFIG` dict.
- **Stooq.pl** (`fetch_stooq_data`) — HTTP CSV download. Configured via `STOOQ_TICKERS` dict.
- **NBP** (`fetch_nbp_data`) — XML parsing for Polish central bank interest rates, historical data back to 1998. Configured via `NBP_TICKERS` dict. NBP data is NOT forward-filled and NOT merged with old values — always uses fresh XML state.

Flow: load existing CSV → build full date range → fetch each ticker → merge new data with existing (new overwrites, old preserved; except NBP) → save CSV → generate reports (HTML/TXT/JSON) → optionally send email.

Key constants at top of file: `TICKER_CONFIG`, `STOOQ_TICKERS`, `NBP_TICKERS`, `START_DATE`, `NBP_START_DATE`, `OUTPUT_FILE`, `REPORT_DIR`, `EMAIL_TO`, `SMTP_CONFIG`.

### Web Dashboard (`index.html` + `dashboard.css`)
Self-contained static HTML/CSS/JS. Loads `scraped-data.csv` via Papa Parse, renders interactive table and Chart.js charts. Supports dark/light mode, search, sorting, date range filtering, CSV/SVG export. No build tooling — edit directly.

### PHP Serving (`serve-csv.php`, `serve-reports.php`)
Optional server-side scripts for deployment on a web server. Both include path traversal protection via `basename()`. Hardcoded base paths for the production server.

### Report System (`ReportGenerator` class)
Embedded in the scraper. Generates `reports/report_YYYY-MM-DD.{html,txt,json}` after each run. Email delivery via SMTP or system `mail` command.

## Data Source Conventions

- Ticker configs map symbol → `(column_name, decimal_places)`
- All dates use Warsaw timezone (`Europe/Warsaw`)
- CSV output: `date` column + one column per ticker, named by `col_name`
- NBP interest rates use a different `NBP_START_DATE` (1998) vs Yahoo/Stooq `START_DATE` (2025)

## Deployment

Designed to run as a daily cron job on a VPS. The wrapper script `run_yahoo-finance-all.sh` handles logging. CSV is then copied to a public web server location where `index.html` can access it.
