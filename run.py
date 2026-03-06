"""
Surebet Detection System - Entry Point
Run: python run.py
"""
import os
import sys
import uvicorn

# Ensure we can import the backend package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))

    print(f"""
    ╔════════════════════════════════════════╗
    ║   🎯 Surebet Detection System v1.0    ║
    ║   Real-time Sports Arbitrage Monitor  ║
    ╚════════════════════════════════════════╝

    Server: http://{host}:{port}
    API Docs: http://{host}:{port}/docs
    Dashboard: http://localhost:{port}

    Press Ctrl+C to stop
    """)

    uvicorn.run(
        "backend.api.main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="info",
        access_log=True,
    )
