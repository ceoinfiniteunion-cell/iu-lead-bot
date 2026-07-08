import asyncio
import os
import subprocess
import sys
from bot.main import main as bot_main

if __name__ == "__main__":
    port = os.environ.get("PORT", "8000")
    print(f"Starting uvicorn on port {port}", flush=True)
    proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "api:app",
        "--host", "0.0.0.0",
        "--port", port
    ])
    print(f"uvicorn PID: {proc.pid}", flush=True)
    asyncio.run(bot_main())
