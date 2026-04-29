from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from typing import List, Dict, Any
from pydantic import BaseModel
import os
import requests

app = FastAPI(title="Analysis API")

json_data = {
  "request_id": "req-001",
  "results": {
    "floor_count": {
      "floors": 6,
      "confidence": 0.88,
    }
  },
  "flags": [],
  "debug": {
    "has_facade": True,
    "has_roof": True
  }
}

@app.post("/analyse")
async def start_building_session(
    image1: UploadFile = File(...),
    image2: UploadFile = File(...),
):
    return json_data
