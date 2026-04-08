# Financial Reporting Pipeline

[![CI](https://github.com/HamzaLatif02/finpipe/actions/workflows/ci.yml/badge.svg)](https://github.com/HamzaLatif02/finpipe/actions/workflows/ci.yml)
[![Lint](https://github.com/HamzaLatif02/finpipe/actions/workflows/lint.yml/badge.svg)](https://github.com/HamzaLatif02/finpipe/actions/workflows/lint.yml)
[![codecov](https://codecov.io/gh/HamzaLatif02/finpipe/branch/main/graph/badge.svg)](https://codecov.io/gh/HamzaLatif02/finpipe)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![Flask](https://img.shields.io/badge/flask-3.x-green.svg)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/docker-ready-blue?logo=docker)](https://github.com/HamzaLatif02/finpipe/blob/main/DOCKER.md)

A full-stack web application that runs a complete financial data pipeline for any asset available on Yahoo Finance. Select a ticker, configure a time period and interval, and the app fetches price history, computes key metrics, generates six analytical charts, and produces a downloadable PDF report — all from a single form submission. Reports can also be delivered automatically by email on a daily, weekly, or monthly schedule configured entirely from the browser.

Built with Flask and React. Developed with [Claude Code](https://claude.ai/code).

---

## Live Demo

[Live Demo](https://financial-pipeline-webapp.onrender.com/)

---

## Screenshots

<p align="center">
  <img src="https://github.com/user-attachments/assets/f2944ffe-4788-4ec2-ba18-b07f136c9402"" width="1200"/>
</p>
<p align="center"><i>Figure 1: Parameters selection for analysis.</i></p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/15d975f6-ec79-467a-96c4-a895acaf2010" width="1200"/>
</p>
<p align="center"><i>Figure 2: Analysis results.</i></p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/03146ae0-2b0b-49c8-a262-c0778ded97d8" width="1200"/>
</p>
<p align="center"><i>Figure 3: Schedule report menu.</i></p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/efaa8aca-cfef-4666-a748-c56811d03fe9" width="1300"/>
</p>
<p align="center"><i>Figure 4: PDF Report sample.</i></p>

---

## Features

- **30+ pre-loaded assets** across five categories: Stocks, ETFs, Crypto, Forex, and Commodities
- **Custom ticker support** — enter any Yahoo Finance symbol with live validation before running
- **Configurable period and interval** — from 1 month to 5 years, at daily, weekly, or monthly granularity
- **Key financial metrics** — total return, annualised return, Sharpe ratio, max drawdown, volatility, best and worst single-day returns, average daily volume
- **Six analytical charts** — candlestick, price with moving averages, cumulative return, drawdown, monthly returns heatmap, and a summary statistics table
- **Downloadable PDF report** — all metrics and charts compiled into a single document
- **Automated email delivery** — schedule reports to arrive daily, weekly, or monthly via Gmail SMTP
- **Schedule management** — view and cancel active scheduled reports from the browser
- **Run history** — reload charts and reports from any previous pipeline run without re-fetching data

---

## Tech Stack

### Backend

| Library | Purpose |
|---|---|
| Flask | HTTP server and REST API |
| APScheduler | Background job scheduling with cron triggers |
| yfinance | Market data from Yahoo Finance |
| pandas | Data cleaning and quantitative analysis |
| matplotlib / mplfinance | Chart generation |
| fpdf2 | PDF report generation |
| SQLite | Run history and asset metadata storage |
| smtplib | Email delivery via SMTP |
| gunicorn | Production WSGI server |

### Frontend

| Library | Purpose |
|---|---|
| React | UI framework |
| Vite | Build tool and dev server |
| Tailwind CSS | Styling |
| Axios | HTTP client |
| lucide-react | Icons |

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Gmail account with an [App Password](https://support.google.com/accounts/answer/185833) (required only for email features)

### 1. Clone the repository

```bash
git clone https://github.com/HamzaLatif02/financial_reporting_pipeline_webapp.git
cd financial_reporting_pipeline_webapp
```

### 2. Set up the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```
FLASK_ENV=development
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_gmail_address@gmail.com
SMTP_PASSWORD=your_16_char_app_password
REPORT_RECIPIENT=recipient@example.com
```

`SMTP_USER` and `SMTP_PASSWORD` are only required if you use the email or scheduling features.

### 4. Start the Flask backend

```bash
cd backend
python app.py
```

The API is available at `http://localhost:5001`.

### 5. Start the React frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies all `/api` requests to the Flask backend.

---

## Docker

Run the entire app with a single command:

```bash
git clone https://github.com/HamzaLatif02/finpipe.git
cd finpipe
cp .env.example .env   # fill in your credentials
docker compose up --build
```

Then open [http://localhost:8000](http://localhost:8000).

See [DOCKER.md](DOCKER.md) for full Docker documentation including `docker run` usage, environment variables, and data persistence.

---

## Deployment

The app is configured for deployment to [Render](https://render.com) via [`render.yaml`](./render.yaml). The build script ([`build.sh`](./build.sh)) installs Python dependencies, builds the React frontend, and gunicorn serves both the API and the compiled static files from a single process.

### Required environment variables

Set these in the Render dashboard under **Environment → Environment Variables**:

| Variable | Description |
|---|---|
| `FLASK_ENV` | Set to `production` |
| `SMTP_HOST` | SMTP server hostname (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (e.g. `587`) |
| `SMTP_USER` | Gmail address used to send reports |
| `SMTP_PASSWORD` | 16-character Gmail App Password |
| `REPORT_RECIPIENT` | Default recipient added to all scheduled report emails |

> **Free tier note:** Render's free tier spins down instances after 15 minutes of inactivity. Use a service such as [cron-job.org](https://cron-job.org) to ping `/api/health` every 10 minutes to keep the instance warm and ensure scheduled jobs fire on time.

---

## Project Structure

```
financial_reporting_pipeline_webapp/
│
├── analysis.py              # Financial metrics and series computation
├── charts.py                # Chart generation (matplotlib, mplfinance, seaborn)
├── cleaner.py               # Data cleaning and derived column computation
├── config.py                # Absolute path constants (DATA_DIR, CHARTS_DIR, etc.)
├── db.py                    # SQLite schema and query layer
├── fetcher.py               # Yahoo Finance data fetching (yfinance)
├── report.py                # PDF report generation (fpdf2)
├── requirements.txt
├── render.yaml              # Render deployment configuration
├── build.sh                 # Production build script
├── .python-version          # Pins Python 3.11 on Render
│
├── backend/
│   ├── app.py               # Flask application factory and server entry point
│   ├── scheduler.py         # APScheduler setup, job persistence, SMTP email helper
│   └── api/
│       ├── assets.py        # GET /api/assets — categories, periods, intervals, ticker validation
│       ├── pipeline.py      # POST /api/pipeline/run, GET /api/pipeline/status
│       ├── reports.py       # GET /api/reports — chart image and PDF file serving
│       └── schedule.py      # POST /api/schedule/add, DELETE /remove, GET /list
│
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/
│       │   └── client.js          # Axios wrapper for all API endpoints
│       └── components/
│           ├── AssetSelector.jsx  # Category tabs, asset cards, custom ticker validation
│           ├── ChartViewer.jsx    # Tabbed chart display with loading skeletons
│           ├── Dashboard.jsx      # Post-run results layout
│           ├── ErrorBoundary.jsx  # Global React error boundary
│           ├── MetricsPanel.jsx   # Summary statistics cards
│           ├── ReportDownload.jsx # PDF download button
│           ├── ScheduleManager.jsx # Active scheduled jobs table
│           └── ScheduleModal.jsx  # Schedule creation form
│
├── data/                    # Runtime output (gitignored)
│   ├── raw/                 # Downloaded price CSVs and asset info JSON
│   ├── clean/               # Cleaned and enriched price CSVs
│   ├── charts/              # Generated chart PNGs
│   ├── reporting.db         # SQLite database
│   └── scheduled_jobs.json  # Persisted APScheduler job state
│
└── tests/
    └── test_cleaner.py
```

---

## Disclaimer

This application is for educational purposes only. Nothing it produces constitutes financial advice. All data is sourced from Yahoo Finance via the `yfinance` library and may be delayed or inaccurate. Do not make investment decisions based on the output of this tool.
