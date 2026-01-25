# Yahoo Financial Market Dashboard v.1.5.1
# Copyright (C) 2025 Tomasz Lebioda <tlebioda@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# Author: Tomasz Lebioda
# Email: tlebioda@gmail.com

import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import pandas as pd
from datetime import datetime
import pytz
import time
import random
import os
import subprocess
import json
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import io
import warnings

# Filter warnings
warnings.filterwarnings("ignore")

# Backoff configuration
MAX_RETRIES = 5
BASE_WAIT = 60
PER_TICKER_MIN = 1
PER_TICKER_MAX = 5

def fetch_with_backoff(symbol, start, end):
    wait = BASE_WAIT
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.Ticker(symbol).history(start=start, end=end)
            # Throttle even on success to avoid bursts
            time.sleep(random.uniform(PER_TICKER_MIN, PER_TICKER_MAX))
            return df
        except YFRateLimitError:
            print(f"[{symbol}] Rate limited (attempt {attempt}/{MAX_RETRIES}). Sleeping {wait}s…")
            jitter = wait * 0.2
            time.sleep(wait + random.uniform(-jitter, jitter))
            wait *= 2
    print(f"[{symbol}] FAILED after {MAX_RETRIES} retries – skipping.")
    return pd.DataFrame(columns=["Close"])

# Ticker configuration: symbol -> (column name, decimal places)
TICKER_CONFIG = {
    "^GDAXI":   ("DAX", 2),
    "000001.SS":("China Shanghai SE Composite", 2),
    "^FTSE":    ("the UK FTSE 100", 2),
    "^GSPTSE":  ("Canada S&P/TSX Composite", 2),
    "^GSPC":    ("The US S&P 500", 2),
    "^N225":    ("Japan Nikkei 225", 2),
    "BTC-USD":  ("Bitcoin", 4),
    "ETH-USD":  ("Ethereum", 4),
    "XRP-USD":  ("XRP", 4),
    "SOL-USD":  ("Solana", 4),
    "DOGE-USD": ("DOGE", 4),
    "USDT-USD": ("USDT", 4),
    "TSLA":     ("Tesla", 2),
    "SPAX.PVT": ("SPAX.PVT", 2),
    "PLN=X":    ("USD/PLN", 4),
    "EURPLN=X": ("EUR/PLN", 4),
    "AMZN":     ("Amazon", 2),
    "GBPPLN=X": ("GBP/PLN", 4),
    "CL=F":     ("Crude Oil", 4),
    "NG=F":     ("Natural Gas", 4),
    "GC=F":     ("Gold", 4),
    "SI=F":     ("Silver", 4),
    "TA35.TA":  ("TA35", 2),
    "ILS=X":    ("USD/ILS", 4),
#    "WIG20.WA": ("WIG20", 2)
    "NVDA":     ("NVIDIA", 2),
    "CDR.WA":   ("CD Projekt", 2),
    "^IXIC":    ("NASDAQ Composite", 2),
    "^DJI":     ("Dow Jones Industrial Average", 2),
    "KGH.WA":   ("KGHM", 2),
    "GOOG":     ("Alphabet", 2),
    "ADBE":     ("Adobe", 2),
    "AAPL":     ("Apple", 2),
    "MSFT":     ("Microsoft", 2),
    "META":     ("Meta", 2),
    "JPM":      ("JP Morgan", 2),
    "BRK-B":    ("Berkshire Hathaway", 2),
}

START_DATE = "2025-01-01"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraped-data.csv")
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
EMAIL_TO = "tomasz.lebioda@wyborcza.pl"

# SMTP Configuration (optional - leave empty to use system mail command)
SMTP_CONFIG = {
    "enabled": False,  # Set to True to use SMTP instead of mail command
    "server": "smtp.gmail.com",  # SMTP server address
    "port": 587,  # SMTP port (587 for TLS, 465 for SSL)
    "use_tls": True,  # Use TLS encryption
    "username": "",  # Your email username
    "password": "",  # Your email password or app password
    "from_email": ""  # From email address
}

# Stooq Configuration
STOOQ_TICKERS = {
    "wig20": ("WIG20", 2),
    "wig": ("WIG", 2),
    "wig_nrchom": ("WIG Nieruchomości", 2),
    "inpt.pl": ("InPost", 2)
}

STOOQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_stooq_data(symbol, start, end):
    """
    Fetch historical data from Stooq.pl (CSV)
    URL format: https://stooq.pl/q/d/l/?s=<symbol>&i=d
    """
    url = f"https://stooq.pl/q/d/l/?s={symbol}&i=d"
    print(f"   (Stooq: {url})", end=" ")
    
    try:
        response = requests.get(url, headers=STOOQ_HEADERS, timeout=10)
        response.raise_for_status()
        
        # Stooq returns "No data" in body sometimes or just HTML if blocked/error
        content = response.text
        if "No data" in content or "<html" in content.lower():
            if "<html" in content.lower():
                print("⚠️ (HTML response/blocked)", end=" ")
            return pd.DataFrame()

        # Read CSV
        df = pd.read_csv(io.StringIO(content))
        
        # Rename Polish columns if present
        df.rename(columns={
            "Data": "Date", 
            "Zamkniecie": "Close",
            "Otwarcie": "Open",
            "Najwyzszy": "High",
            "Najnizszy": "Low",
            "Wolumen": "Volume"
        }, inplace=True)

        # Stooq CSV columns: Date, Open, High, Low, Close, Volume
        if "Date" not in df.columns or "Close" not in df.columns:
            return pd.DataFrame()
            
        # Parse Dates
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        
        # Filter by date range
        mask = (df.index >= start) & (df.index <= end)
        df = df.loc[mask]
        
        return df[["Close"]]

    except Exception as e:
        print(f"⚠️ (Stooq error: {str(e)})", end=" ")
        return pd.DataFrame()

def get_today_date():
    warsaw = pytz.timezone("Europe/Warsaw")
    return datetime.now(warsaw).strftime("%Y-%m-%d")

def get_current_datetime():
    warsaw = pytz.timezone("Europe/Warsaw")
    return datetime.now(warsaw).strftime("%Y-%m-%d %H:%M:%S")

class ReportGenerator:
    def __init__(self):
        self.report_data = {
            "timestamp": get_current_datetime(),
            "date": get_today_date(),
            "start_date": START_DATE,
            "tickers": {},
            "summary": {
                "total_tickers": 0,
                "successful": 0,
                "failed": 0,
                "total_records": 0,
                "missing_values": 0
            },
            "errors": []
        }

    def add_ticker_result(self, symbol, col_name, success, records=0, missing=0, error=None):
        self.report_data["tickers"][symbol] = {
            "name": col_name,
            "success": success,
            "records": records,
            "missing_values": missing,
            "error": str(error) if error else None
        }

        self.report_data["summary"]["total_tickers"] += 1
        if success:
            self.report_data["summary"]["successful"] += 1
            self.report_data["summary"]["total_records"] += records
            self.report_data["summary"]["missing_values"] += missing
        else:
            self.report_data["summary"]["failed"] += 1
            if error:
                self.report_data["errors"].append(f"{symbol}: {str(error)}")

    def generate_html_report(self):
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Yahoo Financial Market Dashboard Report - {self.report_data['date']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ background-color: #e8f4f8; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .success {{ color: #28a745; font-weight: bold; }}
        .failed {{ color: #dc3545; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #007bff; color: white; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .error {{ background-color: #fee; padding: 10px; border-radius: 5px; margin: 5px 0; }}
        .footer {{ margin-top: 40px; text-align: center; color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Yahoo Financial Market Dashboard Report</h1>
        <p><strong>Execution time:</strong> {self.report_data['timestamp']}</p>
        <p><strong>Data range:</strong> {self.report_data['start_date']} - {self.report_data['date']}</p>

        <div class="summary">
            <h2>📈 Summary</h2>
            <p>Total tickers: <strong>{self.report_data['summary']['total_tickers']}</strong></p>
            <p>Successfully downloaded: <span class="success">{self.report_data['summary']['successful']}</span></p>
            <p>Failed: <span class="failed">{self.report_data['summary']['failed']}</span></p>
            <p>Total records: <strong>{self.report_data['summary']['total_records']}</strong></p>
            <p>Missing values: <strong>{self.report_data['summary']['missing_values']}</strong></p>
        </div>

        <h2>📋 Ticker Details</h2>
        <table>
            <tr>
                <th>Symbol</th>
                <th>Name</th>
                <th>Status</th>
                <th>Records</th>
                <th>Missing</th>
            </tr>
"""

        for symbol, data in self.report_data["tickers"].items():
            status = '<span class="success">✅ Success</span>' if data["success"] else '<span class="failed">❌ Error</span>'
            html += f"""
            <tr>
                <td>{symbol}</td>
                <td>{data['name']}</td>
                <td>{status}</td>
                <td>{data['records']}</td>
                <td>{data['missing_values']}</td>
            </tr>
"""

        html += """
        </table>
"""

        if self.report_data["errors"]:
            html += """
        <h2>⚠️ Errors</h2>
"""
            for error in self.report_data["errors"]:
                html += f'        <div class="error">{error}</div>\n'

        html += """
        <div class="footer">
            <p>Yahoo Financial Market Dashboard v.1.5.1 | GNU GPL v3.0</p>
            <p>© 2025 Tomasz Lebioda</p>
        </div>
    </div>
</body>
</html>"""
        return html

    def generate_text_report(self):
        separator = "=" * 50
        dash_line = "-" * 50

        text = "YAHOO FINANCIAL MARKET DASHBOARD REPORT\n"
        text += separator + "\n"
        text += f"Execution time: {self.report_data['timestamp']}\n"
        text += f"Data range: {self.report_data['start_date']} - {self.report_data['date']}\n\n"

        text += "SUMMARY\n"
        text += dash_line + "\n"
        text += f"Total tickers: {self.report_data['summary']['total_tickers']}\n"
        text += f"Successfully downloaded: {self.report_data['summary']['successful']}\n"
        text += f"Failed: {self.report_data['summary']['failed']}\n"
        text += f"Total records: {self.report_data['summary']['total_records']}\n"
        text += f"Missing values: {self.report_data['summary']['missing_values']}\n\n"

        text += "TICKER DETAILS\n"
        text += dash_line + "\n"

        for symbol, data in self.report_data["tickers"].items():
            status = "SUCCESS" if data["success"] else "ERROR"
            text += f"{symbol:<12} {data['name']:<30} {status:<8} Records: {data['records']:<6} Missing: {data['missing_values']}\n"

        if self.report_data["errors"]:
            text += "\nERRORS\n"
            text += dash_line + "\n"
            for error in self.report_data["errors"]:
                text += f"- {error}\n"

        text += "\n" + separator + "\n"
        text += "Yahoo Financial Market Dashboard v.1.5.1 | GNU GPL v3.0\n"
        return text

    def convert_numpy_types(self, obj):
        """Convert numpy types to native Python types for JSON serialization"""
        import numpy as np

        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: self.convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_numpy_types(item) for item in obj]
        else:
            return obj

    def save_reports(self):
        # Create reports directory if it doesn't exist
        Path(REPORT_DIR).mkdir(exist_ok=True)

        date_str = self.report_data['date']

        # Save HTML report
        html_path = Path(REPORT_DIR) / f"report_{date_str}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(self.generate_html_report())

        # Save text report
        text_path = Path(REPORT_DIR) / f"report_{date_str}.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(self.generate_text_report())

        # Save JSON report - convert numpy types first
        json_path = Path(REPORT_DIR) / f"report_{date_str}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json_data = self.convert_numpy_types(self.report_data)
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # Save latest report link
        latest_path = Path(REPORT_DIR) / "latest.txt"
        with open(latest_path, 'w', encoding='utf-8') as f:
            f.write(f"Latest report: {date_str}\n")
            f.write(f"HTML: {html_path.name}\n")
            f.write(f"Text: {text_path.name}\n")
            f.write(f"JSON: {json_path.name}\n")
            f.write(f"\nGenerated at: {self.report_data['timestamp']}\n")

        return html_path, text_path, json_path

    def send_email_smtp(self, text_report, html_report):
        """Send email using SMTP configuration"""
        subject = f"Yahoo Financial Market Dashboard Report - {self.report_data['date']}"

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SMTP_CONFIG['from_email']
            msg['To'] = EMAIL_TO

            # Attach text and HTML parts
            text_part = MIMEText(text_report, 'plain', 'utf-8')
            html_part = MIMEText(html_report, 'html', 'utf-8')
            msg.attach(text_part)
            msg.attach(html_part)

            # Connect to SMTP server
            if SMTP_CONFIG['use_tls']:
                server = smtplib.SMTP(SMTP_CONFIG['server'], SMTP_CONFIG['port'])
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(SMTP_CONFIG['server'], SMTP_CONFIG['port'])

            # Login and send
            server.login(SMTP_CONFIG['username'], SMTP_CONFIG['password'])
            server.send_message(msg)
            server.quit()

            print(f"Yahoo Financial Market Dashboard: ✉️ Report sent via SMTP to {EMAIL_TO}")
            return True

        except Exception as e:
            print(f"Yahoo Financial Market Dashboard: ⚠️ SMTP email error: {e}")
            return False

    def send_email(self, text_report):
        """Tries to send email using configured method"""
        subject = f"Yahoo Financial Market Dashboard Report - {self.report_data['date']}"

        # Try SMTP first if configured
        if SMTP_CONFIG.get('enabled') and SMTP_CONFIG.get('username'):
            html_report = self.generate_html_report()
            if self.send_email_smtp(text_report, html_report):
                return True
            print("Yahoo Financial Market Dashboard: ⚠️ SMTP failed, trying system mail command...")

        # Fallback to mail command
        try:
            # Check if mail command exists
            result = subprocess.run(['which', 'mail'], capture_output=True, text=True)
            if result.returncode != 0:
                print("Yahoo Financial Market Dashboard: ⚠️ 'mail' command not available - report saved locally only")
                print("💡 Tip: Configure SMTP settings in the script for reliable email delivery")
                return False

            # Send email
            process = subprocess.Popen(
                ['mail', '-s', subject, EMAIL_TO],
                stdin=subprocess.PIPE,
                text=True
            )
            process.communicate(input=text_report)

            if process.returncode == 0:
                print(f"Yahoo Financial Market Dashboard: ✉️ Report sent via mail command to {EMAIL_TO}")
                return True
            else:
                print("Yahoo Financial Market Dashboard: ⚠️ Email sending error - report saved locally only")
                print("💡 Tip: Check /var/log/mail.log for details or configure SMTP settings")
                return False

        except Exception as e:
            print(f"Yahoo Financial Market Dashboard: ⚠️ Email sending error: {e}")
            return False

# Initialize report generator
report = ReportGenerator()

# 1) Load existing data if file exists
if os.path.exists(OUTPUT_FILE):
    df_existing = pd.read_csv(OUTPUT_FILE, parse_dates=["date"], index_col="date")
else:
    df_existing = None

# 2) Prepare full date range from START_DATE to today
end_date = get_today_date()
all_dates = pd.date_range(start=START_DATE, end=end_date, freq='D', tz=None)
result_df = pd.DataFrame(index=all_dates)

print("Yahoo Financial Market Dashboard: 🚀 Gathering data from Yahoo Finance...\n")

# 3) For each ticker download history and merge with existing data
combined_tickers = []
# Add Yahoo tickers
for symbol, (col_name, decimals) in TICKER_CONFIG.items():
    combined_tickers.append({"source": "yahoo", "symbol": symbol, "col_name": col_name, "decimals": decimals})
# Add Stooq tickers
for symbol, (col_name, decimals) in STOOQ_TICKERS.items():
    combined_tickers.append({"source": "stooq", "symbol": symbol, "col_name": col_name, "decimals": decimals})

for item in combined_tickers:
    source = item["source"]
    symbol = item["symbol"]
    col_name = item["col_name"]
    decimals = item["decimals"]

    print(f"Yahoo Financial Market Dashboard: ⏳ Downloading {col_name} ({symbol})...", end=" ")

    try:
        if source == "yahoo":
            # Download historical Close with backoff retry
            hist = fetch_with_backoff(symbol, START_DATE, end_date)
        else:
            # Download from Stooq
            hist = fetch_stooq_data(symbol, START_DATE, end_date)

        if not hist.empty:
            print("✅")
            success = True
            error = None
        else:
            print("⚠️ (skipped/empty)")
            success = False
            error = "No data returned"
    except Exception as e:
        print("❌ (error)")
        success = False
        error = str(e)
        hist = pd.DataFrame()

    # Remove timezone if we have DatetimeIndex
    if isinstance(hist.index, pd.DatetimeIndex):
        hist.index = hist.index.tz_localize(None)

    # Prepare series with history
    if not hist.empty:
        series_new = hist["Close"].rename(col_name).round(decimals)
    else:
        series_new = pd.Series(name=col_name, dtype=float)

    # Reindex to full date range
    series_new = series_new.reindex(all_dates)

    # If there was previous data, merge: new overwrites, old preserved
    if df_existing is not None and col_name in df_existing.columns:
        series_existing = df_existing[col_name].reindex(all_dates)
        combined = series_new.combine_first(series_existing)
    else:
        combined = series_new

    # Add to result DF
    result_df[col_name] = combined

    # Collect statistics for report
    records_count = int(combined.notna().sum())
    missing_count = int(combined.isna().sum())
    report.add_ticker_result(symbol, col_name, success, records_count, missing_count, error)

# 4) Save result to CSV
result_df = result_df.reset_index().rename(columns={"index": "date"})
result_df["date"] = result_df["date"].dt.strftime("%Y-%m-%d")
result_df.to_csv(OUTPUT_FILE, index=False)

print(f"\nYahoo Financial Market Dashboard: 🎉 Done. Written to {OUTPUT_FILE} from {START_DATE} to {end_date} 📈")

# Generate and save reports
print("\nYahoo Financial Market Dashboard: 📝 Generating reports...")
html_path, text_path, json_path = report.save_reports()
print(f"Yahoo Financial Market Dashboard: 💾 Reports saved in '{REPORT_DIR}' directory")
print(f"Yahoo Financial Market Dashboard: 📄 View report at: {html_path}")

# Try to send email
text_report = report.generate_text_report()
report.send_email(text_report)
