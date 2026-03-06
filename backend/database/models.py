"""
Database models for the Surebet Detection System.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Index, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Bookmaker(Base):
    """Registered bookmakers/betting sites."""
    __tablename__ = "bookmakers"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    url = Column(String(500), nullable=False)
    scraper_class = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    last_scraped = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    odds = relationship("OddsRecord", back_populates="bookmaker")

    def __repr__(self):
        return f"<Bookmaker {self.name}>"


class Sport(Base):
    """Sports categories."""
    __tablename__ = "sports"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)  # e.g., 'NBA', 'NFL'
    is_active = Column(Boolean, default=True)

    events = relationship("SportEvent", back_populates="sport")


class SportEvent(Base):
    """Sporting events/games."""
    __tablename__ = "sport_events"

    id = Column(Integer, primary_key=True)
    sport_id = Column(Integer, ForeignKey("sports.id"), nullable=False)
    home_team = Column(String(200), nullable=False)
    away_team = Column(String(200), nullable=False)
    event_date = Column(DateTime, nullable=True)
    league = Column(String(200), nullable=True)
    status = Column(String(50), default="scheduled")  # scheduled, live, finished
    normalized_key = Column(String(500), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sport = relationship("Sport", back_populates="events")
    odds = relationship("OddsRecord", back_populates="event")
    surebets = relationship("SurebetOpportunity", back_populates="event")

    __table_args__ = (
        Index("idx_event_normalized_key", "normalized_key"),
        Index("idx_event_date", "event_date"),
    )


class OddsRecord(Base):
    """Historical odds snapshots from bookmakers."""
    __tablename__ = "odds_records"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("sport_events.id"), nullable=False)
    bookmaker_id = Column(Integer, ForeignKey("bookmakers.id"), nullable=False)
    market_type = Column(String(50), nullable=False)  # '1X2', 'moneyline', 'spread', 'total'
    outcome = Column(String(100), nullable=False)  # 'home', 'away', 'draw', 'over', 'under'
    odds_value = Column(Float, nullable=False)
    handicap = Column(Float, nullable=True)  # For spread/total bets
    raw_odds = Column(String(20), nullable=True)  # Original format (e.g., '-110', '+150')
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    event = relationship("SportEvent", back_populates="odds")
    bookmaker = relationship("Bookmaker", back_populates="odds")

    __table_args__ = (
        Index("idx_odds_event_bookmaker", "event_id", "bookmaker_id"),
        Index("idx_odds_timestamp", "timestamp"),
        Index("idx_odds_market", "market_type", "outcome"),
    )


class SurebetOpportunity(Base):
    """Detected surebet and near-surebet opportunities."""
    __tablename__ = "surebet_opportunities"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("sport_events.id"), nullable=False)
    opportunity_type = Column(String(20), nullable=False)  # 'surebet' or 'near_surebet'
    market_type = Column(String(50), nullable=False)
    profit_margin = Column(Float, nullable=False)  # Positive = profit, negative = loss
    total_implied_prob = Column(Float, nullable=False)  # Sum of implied probabilities
    details = Column(Text, nullable=False)  # JSON with full bet details
    is_active = Column(Boolean, default=True)
    alerted = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)

    event = relationship("SportEvent", back_populates="surebets")

    __table_args__ = (
        Index("idx_surebet_type", "opportunity_type"),
        Index("idx_surebet_active", "is_active"),
        Index("idx_surebet_detected", "detected_at"),
    )
