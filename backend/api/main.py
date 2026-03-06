"""
Surebet Detection System - FastAPI Backend
Main application entry point with REST API + WebSocket support.
"""
import asyncio
import os
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
from loguru import logger

from ..database.session import get_db, init_db
from ..database.models import (
    Bookmaker, Sport, SportEvent, OddsRecord, SurebetOpportunity
)
from ..scrapers import (
    BetcrisScraper, JuancitoScraper, HDLineaScraper, OddsData, SCRAPER_REGISTRY
)
from ..algorithms import SurebetDetector, SurebetResult
from ..alerts.notifier import ws_manager, email_notifier, telegram_notifier


# --- Auth Configuration ---
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "surebet2024")
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "24"))

# In-memory token store: {token: expiry_datetime}
_auth_tokens: dict[str, datetime] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


# --- Configuration ---
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "30"))
NEAR_SUREBET_THRESHOLD = float(os.getenv("NEAR_SUREBET_THRESHOLD", "1.05"))
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.01"))

detector = SurebetDetector(
    surebet_threshold=1.0,
    near_surebet_threshold=NEAR_SUREBET_THRESHOLD,
)

# In-memory cache for latest odds and opportunities
latest_odds: list[OddsData] = []
latest_opportunities: list[SurebetResult] = []
scraping_status = {
    "is_running": False,
    "last_scrape": None,
    "total_odds": 0,
    "total_opportunities": 0,
    "total_surebets": 0,
    "errors": [],
}

# Tracks event_keys already alerted this session to avoid re-alerting every cycle
_alerted_surebet_keys: set[str] = set()
_alerted_near_keys: set[str] = set()


# --- Lifespan (startup/shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Starting Surebet Detection System...")
    await init_db()
    logger.info("Database initialized.")

    # Start background scraping task
    task = asyncio.create_task(scraping_loop())
    logger.info(f"Scraping loop started (interval: {SCRAPE_INTERVAL}s)")

    yield  # App runs here

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Surebet system shutdown.")


# --- App ---
app = FastAPI(
    title="Surebet Detection System",
    description="Real-time sports arbitrage opportunity detector",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Middleware ---
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Protect all /api/* routes except /api/auth/login."""
    path = request.url.path
    # Allow login and non-API routes through without auth
    if not path.startswith("/api/") or path == "/api/auth/login":
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    expiry = _auth_tokens.get(token) if token else None

    if not expiry or datetime.utcnow() > expiry:
        if token:
            _auth_tokens.pop(token, None)
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    return await call_next(request)


# --- Background Scraping Loop ---
async def scraping_loop():
    """Continuous scraping loop that runs every SCRAPE_INTERVAL seconds."""
    global latest_odds, latest_opportunities, scraping_status

    scrapers = [BetcrisScraper(), JuancitoScraper(), HDLineaScraper()]

    while True:
        try:
            scraping_status["is_running"] = True
            scraping_status["errors"] = []
            all_odds = []

            logger.info("Starting scraping cycle...")

            # HDLinea is HTTP-based (fast) — run concurrently with itself
            # Betcris and JuancitoSport both use Playwright, run sequentially
            # to avoid two headless browsers competing for resources
            hdlinea_scraper = scrapers[2]  # HDLineaScraper
            playwright_scrapers = scrapers[:2]  # Betcris, JuancitoSport

            # HDLinea runs first (fast, no browser)
            hdlinea_result = await hdlinea_scraper.scrape()
            if isinstance(hdlinea_result, Exception):
                logger.error(f"{hdlinea_scraper.name}: {hdlinea_result}")
                scraping_status["errors"].append(str(hdlinea_result))
            else:
                all_odds.extend(hdlinea_result)
                logger.info(f"{hdlinea_scraper.name}: {len(hdlinea_result)} odds collected")

            # Playwright scrapers run one at a time
            for scraper in playwright_scrapers:
                try:
                    result = await scraper.scrape()
                    all_odds.extend(result)
                    logger.info(f"{scraper.name}: {len(result)} odds collected")
                except Exception as e:
                    err_msg = f"{scraper.name}: {str(e)}"
                    logger.error(err_msg)
                    scraping_status["errors"].append(err_msg)

            latest_odds = all_odds
            scraping_status["total_odds"] = len(all_odds)

            # Run surebet detection
            opportunities = detector.detect(all_odds)
            latest_opportunities = opportunities

            surebets = [o for o in opportunities if o.is_profitable]
            near_surebets = [o for o in opportunities if not o.is_profitable]

            scraping_status["total_opportunities"] = len(opportunities)
            scraping_status["total_surebets"] = len(surebets)
            scraping_status["last_scrape"] = datetime.utcnow().isoformat()

            logger.info(
                f"Cycle complete: {len(all_odds)} odds, "
                f"{len(surebets)} surebets, {len(near_surebets)} near-surebets"
            )

            # Broadcast status update to WebSocket clients
            await ws_manager.broadcast_status(scraping_status)

            # Broadcast all current opportunities via WebSocket
            for opp in opportunities:
                await ws_manager.broadcast_opportunity(opp)

            # --- Alert only on NEW surebets (not re-alerted every cycle) ---
            current_surebet_keys = {o.event_key for o in opportunities if o.is_profitable}
            current_near_keys    = {o.event_key for o in opportunities if not o.is_profitable}

            for opp in opportunities:
                alert_key = f"{opp.event_key}:{opp.market_type}"

                if opp.is_profitable and alert_key not in _alerted_surebet_keys:
                    # Newly confirmed surebet — fire all channels
                    _alerted_surebet_keys.add(alert_key)
                    await email_notifier.send_alert(opp)
                    await telegram_notifier.send_surebet(opp)
                    logger.info(f"Alerts sent for new surebet: {alert_key}")

                elif not opp.is_profitable and alert_key not in _alerted_near_keys:
                    # Newly detected near-surebet — Telegram only (if configured)
                    _alerted_near_keys.add(alert_key)
                    await telegram_notifier.send_near_surebet(opp)

            # Expire keys for surebets that are no longer present
            gone_surebets = {k for k in _alerted_surebet_keys
                             if k.split(":")[0] not in current_surebet_keys}
            _alerted_surebet_keys.difference_update(gone_surebets)

            gone_near = {k for k in _alerted_near_keys
                         if k.split(":")[0] not in current_near_keys}
            _alerted_near_keys.difference_update(gone_near)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Scraping loop error: {e}")
            scraping_status["errors"].append(str(e))
        finally:
            scraping_status["is_running"] = False

        await asyncio.sleep(SCRAPE_INTERVAL)


# --- REST API Routes ---

@app.post("/api/auth/login")
async def login(credentials: LoginRequest):
    """Authenticate and receive an access token."""
    if credentials.username != DASHBOARD_USERNAME or credentials.password != DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(32)
    _auth_tokens[token] = datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)
    logger.info(f"Login: user '{credentials.username}' authenticated.")
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Invalidate the current access token."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        _auth_tokens.pop(token, None)
    return {"message": "Logged out"}


@app.get("/")
async def root():
    """Serve the frontend dashboard."""
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist", "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"message": "Surebet Detection System API", "docs": "/docs", "status": "/api/status"}


@app.get("/api/status")
async def get_status():
    """Get current system status."""
    return {
        "status": "running",
        "scrape_interval": SCRAPE_INTERVAL,
        "near_surebet_threshold": NEAR_SUREBET_THRESHOLD,
        "connected_clients": len(ws_manager.active_connections),
        **scraping_status,
    }


@app.get("/api/opportunities")
async def get_opportunities(
    type: Optional[str] = Query(None, description="'surebet' or 'near_surebet'"),
    sport: Optional[str] = Query(None, description="Sport code filter (NBA, NFL, etc.)"),
    min_margin: Optional[float] = Query(None, description="Minimum profit margin %"),
):
    """Get current surebet/near-surebet opportunities."""
    opps = latest_opportunities

    if type:
        opps = [o for o in opps if o.opportunity_type == type]

    if sport:
        opps = [o for o in opps if o.sport_code.upper() == sport.upper()]

    if min_margin is not None:
        opps = [o for o in opps if o.profit_margin >= min_margin]

    return {
        "count": len(opps),
        "opportunities": [o.to_dict() for o in opps],
        "last_update": scraping_status.get("last_scrape"),
    }


@app.get("/api/odds")
async def get_odds(
    sport: Optional[str] = Query(None),
    bookmaker: Optional[str] = Query(None),
):
    """Get latest raw odds."""
    odds = latest_odds

    if sport:
        odds = [o for o in odds if o.sport_code.upper() == sport.upper()]

    if bookmaker:
        odds = [o for o in odds if o.bookmaker.lower() == bookmaker.lower()]

    return {
        "count": len(odds),
        "odds": [
            {
                "bookmaker": o.bookmaker,
                "sport": o.sport_code,
                "league": o.league,
                "home_team": o.home_team,
                "away_team": o.away_team,
                "market": o.market_type,
                "outcome": o.outcome,
                "odds": o.odds_value,
                "raw": o.raw_odds,
                "event_date": o.event_date.isoformat() if o.event_date else None,
            }
            for o in odds
        ],
    }


@app.get("/api/bookmakers")
async def get_bookmakers(db: AsyncSession = Depends(get_db)):
    """Get registered bookmakers."""
    result = await db.execute(select(Bookmaker))
    bookmakers = result.scalars().all()
    return [
        {
            "id": bm.id,
            "name": bm.name,
            "url": bm.url,
            "is_active": bm.is_active,
            "last_scraped": bm.last_scraped.isoformat() if bm.last_scraped else None,
        }
        for bm in bookmakers
    ]


@app.get("/api/sports")
async def get_sports(db: AsyncSession = Depends(get_db)):
    """Get tracked sports."""
    result = await db.execute(select(Sport).where(Sport.is_active == True))
    sports = result.scalars().all()
    return [
        {"id": s.id, "name": s.name, "code": s.code}
        for s in sports
    ]


@app.get("/api/calculator")
async def calculate_stakes(
    odds_a: float = Query(..., description="Odds for outcome A (decimal)"),
    odds_b: float = Query(..., description="Odds for outcome B (decimal)"),
    odds_c: Optional[float] = Query(None, description="Odds for outcome C (draw, optional)"),
    bankroll: float = Query(100.0, description="Total bankroll amount"),
):
    """
    Calculate surebet stakes and profit for given odds.
    Works for 2-way and 3-way markets.
    """
    from ..scrapers.base_scraper import decimal_to_implied_prob

    if odds_c:
        # 3-way market
        ip_a = decimal_to_implied_prob(odds_a)
        ip_b = decimal_to_implied_prob(odds_b)
        ip_c = decimal_to_implied_prob(odds_c)
        total_ip = ip_a + ip_b + ip_c
        legs = [
            {"outcome": "A", "odds": odds_a, "ip": ip_a, "stake_pct": ip_a / total_ip * 100, "stake": bankroll * ip_a / total_ip},
            {"outcome": "Draw", "odds": odds_b, "ip": ip_b, "stake_pct": ip_b / total_ip * 100, "stake": bankroll * ip_b / total_ip},
            {"outcome": "B", "odds": odds_c, "ip": ip_c, "stake_pct": ip_c / total_ip * 100, "stake": bankroll * ip_c / total_ip},
        ]
    else:
        # 2-way market
        ip_a = decimal_to_implied_prob(odds_a)
        ip_b = decimal_to_implied_prob(odds_b)
        total_ip = ip_a + ip_b
        legs = [
            {"outcome": "A", "odds": odds_a, "ip": ip_a, "stake_pct": ip_a / total_ip * 100, "stake": bankroll * ip_a / total_ip},
            {"outcome": "B", "odds": odds_b, "ip": ip_b, "stake_pct": ip_b / total_ip * 100, "stake": bankroll * ip_b / total_ip},
        ]

    profit_margin = (1 - total_ip) / total_ip * 100
    is_surebet = total_ip < 1.0

    # Calculate payout for each winning scenario
    payouts = []
    for leg in legs:
        payout = leg["stake"] * leg["odds"]
        payouts.append({
            "outcome": leg["outcome"],
            "stake": round(leg["stake"], 2),
            "stake_pct": round(leg["stake_pct"], 2),
            "payout": round(payout, 2),
            "profit": round(payout - bankroll, 2),
        })

    return {
        "is_surebet": is_surebet,
        "total_implied_prob": round(total_ip, 6),
        "profit_margin": round(profit_margin, 4),
        "bankroll": bankroll,
        "legs": payouts,
    }


@app.get("/api/history")
async def get_history(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    type: Optional[str] = Query(None),
):
    """Get historical surebet opportunities from database."""
    query = select(SurebetOpportunity).order_by(
        desc(SurebetOpportunity.detected_at)
    )

    if type:
        query = query.where(SurebetOpportunity.opportunity_type == type)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    records = result.scalars().all()

    return {
        "count": len(records),
        "items": [
            {
                "id": r.id,
                "type": r.opportunity_type,
                "market": r.market_type,
                "margin": r.profit_margin,
                "details": json.loads(r.details),
                "detected_at": r.detected_at.isoformat(),
                "is_active": r.is_active,
            }
            for r in records
        ],
    }


@app.get("/api/telegram/status")
async def telegram_status():
    """Get Telegram bot configuration and active state."""
    return {
        "configured": telegram_notifier.enabled,
        "active": telegram_notifier.active,
        "near_surebets": telegram_notifier.alert_near,
    }


@app.post("/api/telegram/toggle")
async def telegram_toggle():
    """Toggle Telegram notifications on or off."""
    if not telegram_notifier.enabled:
        raise HTTPException(
            status_code=503,
            detail="Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
    telegram_notifier.active = not telegram_notifier.active
    state = "enabled" if telegram_notifier.active else "disabled"
    logger.info(f"Telegram notifications {state} by user.")
    return {"active": telegram_notifier.active}


@app.post("/api/telegram/test")
async def test_telegram():
    """Send a test Telegram message to verify bot configuration."""
    if not telegram_notifier.enabled:
        raise HTTPException(
            status_code=503,
            detail="Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars."
        )
    ok = await telegram_notifier.send_test()
    if ok:
        return {"message": "Test message sent. Check your Telegram chat."}
    raise HTTPException(status_code=500, detail="Failed to send Telegram message. Check your token/chat_id.")


@app.post("/api/scrape/trigger")
async def trigger_scrape():
    """Manually trigger a scraping cycle."""
    if scraping_status["is_running"]:
        raise HTTPException(status_code=409, detail="Scraping already in progress")

    asyncio.create_task(scraping_loop())
    return {"message": "Scraping triggered"}


# --- WebSocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query("")):
    """
    WebSocket endpoint for real-time opportunity alerts.

    Messages sent to client:
    - type: "opportunity" -> new surebet/near-surebet detected
    - type: "status"      -> scraping cycle update
    - type: "odds_update" -> odds changed for an event
    """
    # Validate auth token
    expiry = _auth_tokens.get(token) if token else None
    if not expiry or datetime.utcnow() > expiry:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(websocket)
    try:
        # Send current opportunities on connect
        await websocket.send_json({
            "type": "init",
            "opportunities": [o.to_dict() for o in latest_opportunities],
            "status": scraping_status,
        })

        # Keep connection alive, receive pings
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client messages (e.g., filter requests)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat", "ts": datetime.utcnow().isoformat()})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await ws_manager.disconnect(websocket)


# --- Mount Static Files (React Build) ---
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")
