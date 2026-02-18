#!/usr/bin/env python3
"""Entry point for Pi Dashboard."""

import uvicorn
from app.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
