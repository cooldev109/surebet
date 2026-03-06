"""
Database session management.
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./surebet.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Dependency for FastAPI routes."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables and seed initial data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _seed_initial_data()


async def _seed_initial_data():
    """Seed bookmakers and sports on first run."""
    from .models import Bookmaker, Sport

    async with async_session_maker() as session:
        from sqlalchemy import select

        # Seed bookmakers
        bookmakers_data = [
            {
                "name": "Betcris",
                "url": "https://www.betcris.do/",
                "scraper_class": "BetcrisScraper",
            },
            {
                "name": "JuancitoSport",
                "url": "https://www.juancitosport.com.do/deportes/",
                "scraper_class": "JuancitoScraper",
            },
            {
                "name": "HDLinea",
                "url": "http://hdlinea.com.do/lineas.asp",
                "scraper_class": "HDLineaScraper",
            },
        ]

        for bm_data in bookmakers_data:
            result = await session.execute(
                select(Bookmaker).where(Bookmaker.name == bm_data["name"])
            )
            if not result.scalar_one_or_none():
                session.add(Bookmaker(**bm_data))

        # Seed sports
        sports_data = [
            {"name": "NBA Basketball", "code": "NBA"},
            {"name": "NFL Football", "code": "NFL"},
            {"name": "MLB Baseball", "code": "MLB"},
            {"name": "NHL Hockey", "code": "NHL"},
            {"name": "NCAA Basketball", "code": "NCAAB"},
            {"name": "NCAA Football", "code": "NCAAF"},
            {"name": "EuroLiga Basketball", "code": "EUROL"},
            {"name": "UEFA Champions League", "code": "UCL"},
            {"name": "EuroCopa", "code": "EURO"},
            {"name": "Soccer", "code": "SOC"},
        ]

        for sp_data in sports_data:
            result = await session.execute(
                select(Sport).where(Sport.code == sp_data["code"])
            )
            if not result.scalar_one_or_none():
                session.add(Sport(**sp_data))

        await session.commit()
