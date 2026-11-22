"""Entry point. Renode's Python egg runs `python app.py` and provides SERVER_PORT."""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or 8000)
    uvicorn.run("app.main:app", host=os.environ.get("HOST", "0.0.0.0"), port=port,
                reload=os.environ.get("DEV_RELOAD") == "1", proxy_headers=True,
                forwarded_allow_ips="*")
