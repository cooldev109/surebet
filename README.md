# 🎯 Surebet Detection System

Real-time sports arbitrage (surebet) detector for Dominican Republic betting sites.

## Monitored Bookmakers
| Casa | URL | Método |
|------|-----|--------|
| **Betcris** | betcris.do | Scraping + API |
| **JuancitoSport** | juancitosport.com.do | Scraping |
| **HDLinea** | hdlinea.com.do | Scraping ASP |

## Sports Tracked
- 🏀 NBA, NCAA Basketball, EuroLiga
- 🏈 NFL, NCAA Football
- ⚾ MLB
- 🏒 NHL
- ⚽ Soccer, Champions League, EuroCopa

---

## Quick Start

### Option 1: Local Installation
```bash
# Windows
install.bat

# Then start
start.bat
```

### Option 2: Manual Setup
```bash
# 1. Python environment
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build frontend
cd frontend
npm install && npm run build
cd ..

# 4. Configure (optional)
copy .env.example .env
# Edit .env for email alerts, intervals, etc.

# 5. Run
python run.py
```

### Option 3: Docker
```bash
cd frontend && npm run build && cd ..
docker-compose up -d
```

---

## Access
- **Dashboard**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **WebSocket**: ws://localhost:8000/ws

---

## How It Works

### Surebet Algorithm
A surebet exists when the sum of implied probabilities across all outcomes is **< 1.0**:

```
IP_home = 1 / odds_home_bookmaker_A
IP_away = 1 / odds_away_bookmaker_B
Total_IP = IP_home + IP_away

If Total_IP < 1.0:  → SUREBET (guaranteed profit)
If Total_IP < 1.05: → NEAR SUREBET (monitor closely)

Profit margin = (1 - Total_IP) / Total_IP × 100%
```

### Optimal Stake Distribution
For a $1,000 bankroll:
```
Stake_A = IP_home / Total_IP × $1,000
Stake_B = IP_away / Total_IP × $1,000
```
Both outcomes yield identical profit regardless of result.

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | System status |
| `GET /api/opportunities` | Current surebets |
| `GET /api/odds` | Raw odds data |
| `GET /api/calculator` | Stake calculator |
| `GET /api/history` | Historical opportunities |
| `GET /api/bookmakers` | Registered bookmakers |
| `GET /api/sports` | Tracked sports |
| `POST /api/scrape/trigger` | Manual scrape trigger |
| `WS /ws` | Real-time WebSocket feed |

### Opportunities Filter Example
```
GET /api/opportunities?type=surebet&sport=NBA&min_margin=1.0
```

---

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPE_INTERVAL` | 30 | Seconds between scraping cycles |
| `NEAR_SUREBET_THRESHOLD` | 1.05 | Max IP to flag near-surebets |
| `ALERT_THRESHOLD` | 0.01 | Min profit % for email alerts |
| `SMTP_*` | — | Email notification settings |
| `DATABASE_URL` | SQLite | Database connection |

---

## Project Structure

```
surebet/
├── backend/
│   ├── scrapers/          # Bookmaker scrapers
│   │   ├── base_scraper.py
│   │   ├── betcris_scraper.py
│   │   ├── juancito_scraper.py
│   │   └── hdlinea_scraper.py
│   ├── algorithms/        # Surebet detection
│   │   └── surebet_detector.py
│   ├── api/               # FastAPI backend
│   │   └── main.py
│   ├── database/          # SQLAlchemy models
│   │   ├── models.py
│   │   └── session.py
│   └── alerts/            # WebSocket + Email alerts
│       └── notifier.py
├── frontend/              # React dashboard
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── Dashboard.jsx
│           ├── OpportunitiesPanel.jsx
│           ├── OddsTable.jsx
│           └── Calculator.jsx
├── tests/                 # Unit tests
│   └── test_surebet_detector.py
├── requirements.txt
├── run.py
├── install.bat
└── docker-compose.yml
```

---

## Important: Geo-Restriction

**Betcris** and **HDLinea** are geo-restricted to Dominican Republic IPs.
The application MUST run on a server physically located in the Dominican Republic
(or behind a DR-based VPN/proxy) for these scrapers to receive odds data.

| Bookmaker | Status from outside DR |
|-----------|----------------------|
| JuancitoSport | Works (BOSS Wagering platform, login-only restriction) |
| Betcris | Blocked — shows "Acceso no disponible desde tu ubicación" |
| HDLinea | Blocked — returns empty game table (ASP server-side restriction) |

**JuancitoSport** works from anywhere as long as credentials are valid.
Confirmed sports available in JuancitoSport BOSS sidebar: NBA, NCAA BASKET, COLLEGE BASEBALL, Soccer leagues.

### HDLinea Sport IDs (confirmed)
| Sport | ID |
|-------|----|
| NBA | 13 |
| MLB | 12 |
| NHL | 14 |
| NCAA Basketball (C-BK) | 17 |
| Soccer | 23 |
| EuroLiga (EU-BK) | 56 |

---

## Notes for Production
- **Run on a DR server** — Betcris and HDLinea require Dominican Republic IPs
- Add proxy rotation for scraping to avoid IP blocks
- Consider upgrading from SQLite to PostgreSQL for high volume
- Set up monitoring/alerting (e.g., Datadog, Sentry)
- Use a process manager like PM2 or systemd for auto-restart
