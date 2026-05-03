from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from typing import List, Dict, Any
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv
import base64

from scripts.sessions import ChatSessionManager

load_dotenv()

crew_llm = os.getenv("CREW_LLM")
analysis_api_url = os.getenv("ANALYSIS_API_URL")
max_messages = os.getenv("MAX_HISTORY_MESSAGES")

def get_payload(facade_base64, roof_base64):
    payload = {
        "request_id": "demo-001",
        "images": [
            {
                "image_id": "facade-001",
                "role": "facade",
                "image_base64": facade_base64,
                "mime_type": "image/jpeg",
                "metadata": {},
            },
            {
                "image_id": "roof-001",
                "role": "roof",
                "image_base64": roof_base64,
                "mime_type": "image/jpeg",
                "metadata": {},
            },
        ],
        "context": {},
    }
    return payload

def create_app():
    # Регистрация роутов и настройка приложения
    app = FastAPI(title="Building Agent API")

    chat_manager = ChatSessionManager(max_messages=50)

    # --- Pydantic модели для чата ---
    class ChatRequest(BaseModel):
        user_id: str
        message: str


    class ChatResponse(BaseModel):
        result: str
        user_id: str
        response: str
        history_length: int

    @app.post("/api/building/start")
    async def start_building_session(
        user_id: str = Form(...),
        buiding_id: str = Form(...),
        facade_img: UploadFile = File(...),
        roof_img: UploadFile = File(...),
    ):
        """
        - user_id: str
        - buiding_id: str
        - image1: UploadFile
        - image2: UploadFile
        """
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        # Читаем байты обоих изображений
        facade_bytes = await facade_img.read()
        roof_bytes = await roof_img.read()

        try:
            facade_base64 = base64.b64encode(facade_bytes).decode("utf-8")
            roof_base64 = base64.b64encode(roof_bytes).decode("utf-8")

            resp = requests.post(
                analysis_api_url,
                json=get_payload(facade_base64, roof_base64),
                timeout=30,
            )


            if resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"analysis api error: {resp.json()}")

            data = resp.json()
            building_text = str(data)

            if not building_text:
                raise HTTPException(
                    status_code=500,
                    detail="empty building text from analysis API")
            else:
                chat_manager.add_context(
                    building_id=buiding_id, context=building_text)
                chat_manager.set_current_context_id(
                    user_id=user_id, building_id=buiding_id)

                return {"status": "registered"}

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"analysis api failed: {e}")

    @app.post("/api/building/history")
    def get_history(
        user_id: str = Form(...)
    ):
        """
        ARGS:
            - user_id: str
        RETURNS:
            - user_history: json
        """
        return chat_manager.get_history_json(user_id)

    @app.get("/api/building/users")
    def get_users():
        """
        """
        return chat_manager.get_users_ids()

    @app.post("/api/building/context")
    def get_context(
        user_id: str = Form(...)
    ):
        """
        """
        return chat_manager.get_user_context(user_id)


    @app.post("/api/building/chat")
    def chat(
        user_id: str = Form(...),
        user_request: str = Form(...)
    ):
        resp = chat_manager.request_to_llm(user_request, user_id)
        return resp

    return app

app = create_app()
