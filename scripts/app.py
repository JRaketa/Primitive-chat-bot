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

def json2md(responce_json):
    results = responce_json['results']

    context = "# Building parameters\n"
    for res in results.keys():
        params = results[res]
        for sub_key in params.keys():
            sub_val = params[sub_key]
            if sub_key != "confidence":
                context += res.replace("_", " ") + ": " + str(sub_val) + '\n'
    return context

descr = """# Quick Start
1. Initiate session for user with `user_id` about buiding with `buiding_id`. Use `/api/building/start` method.
2. 
        
"""

def create_app():
    # Регистрация роутов и настройка приложения
    app = FastAPI(
        title="Building Agent API",
        description=descr, 
        debug=True)

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
        **Session initiation.** <br/>
        To initiate a chat with `user_id` about `buiding_id` you must send `facade_img` and `roof_img` *(jpeg, png)*>.<br/>
        This two images are sent to AI module for exterior analysis. AI module returns analysis as text. <br/>
        Text data from other sources about this building is collected by backend of this API using `buiding_id` *(coming soon)*.<br/> 
        All collected text data is used in QA agent. To read all collected text data about `buiding_id` use `/api/building/building_context`.

        Re-registration for pair (`user_id` and `buiding_id`) is not possible.<br/>
        In this case API returnd `Pair user_id <{user_id}> and buiding_id <{buiding_id}> has been registered.`.
        
        **ARGS:**
        * *user_id*: str
        * *buiding_id*: str
        * *image1*: UploadFile
        * *image2*: UploadFile
        
        **RETURNS:**
        * *{"status": "registered"}*: json - in case all data about the building was collected and recorded by backend successfully.<br/>
        Otherwise it returns error with status code and the error explanation.
        """
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        buildings_ids = chat_manager.get_user_contexts(user_id)
        if type(buildings_ids) == list:
            if buiding_id in buildings_ids:
                return {"status": "error", "comment": f"Pair user_id <{user_id}> and buiding_id <{buiding_id}> has been registered."}
        
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
            building_text = json2md(data)

            if not building_text:
                raise HTTPException(
                    status_code=500,
                    detail="empty building text from analysis API")
            else:
                chat_manager.init_session(
                    user_id=user_id,
                    building_id=buiding_id,
                    context=building_text)

                return {"status": "registered"}

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"analysis api failed: {e}")

    @app.post("/api/building/history")
    def get_history(
        user_id: str = Form(...),
        building_id: str = Form(...)
    ):
        """**Returns chat bot history for `user_id` and `building_id`.**
        
        **ARGS:**
        * *user_id:* str
        * *building_id:* str
        **RETURNS:**
        * *user_history:* list of jsons
            
        **HISTORY FORMAT:**
        [
            {'role': 'user', 'content': <text>},
            {'role': 'system', 'content': <text>},
            {'role': 'user', 'content': <text>},
            ... ...
        ]"""
        try:
            hist = chat_manager.get_history(user_id, building_id)
            if hist:
                return {"status": "success", "history": hist}
            return {"status": "success", "comment": f"History for user_id <{user_id}> and building_id <{building_id}", "history": []}
        except Exception as e:
            return {"status": "error", "comment": f"Chat for user_id <{user_id}> and building_id <{building_id}> was not initiated."}

    @app.get("/api/building/users")
    def get_users():
        """**Returns list of registered users id.**
        
        Requires no params.
        """
        return chat_manager.get_users_ids()

    @app.post("/api/building/building_context")
    def get_context(
        building_id: str = Form(...)
    ):
        """**Returns context  for `building_id`.**

        Building's context is all text data was collected on registration `/api/building/start`.
        Context is used as knowledge base for the QA agent. 

        **ARGS:**
        * *building_id:* str
        
        **RETURNS:**
        * If context of *building_id* exists in DB returns json: `{"status": "success", "context": build_context}`
        * Otherwise, the next json is returned if no user requested info about *building_id*: <br/>
        `{"status": "error", "comment": f"There is no context for building_id <building_id>"}`
        """
        build_context = chat_manager.get_context(building_id)
        if build_context:
            return {"status": "success", "context": build_context}
        return {"status": "error", "comment": f"There is no context for building_id <{building_id}>"}

    @app.post("/api/building/user_contexts")
    def get_user_contexts(
        user_id: str = Form(...)
    ):
        """**Returns all `building_ids` that `user_id` requested for analysis.**
        
        **ARGS:**
        * *user_id:* str
        
        **RETURNS:**
        * If `user_id` has requested info about several `building_ids` returns the next *json*:  list of building's ids: list:<br/>
        `{
            "status": "success", 
            "comment": "not empty", 
            "buidings_ids": [<building_id>, <building_id>, ...]
        }`
        * If `user_id` has not requested info about any building returns the next json:<br/>
        `{"status": "success", "comment": "empty", "buidings_ids": []}`
        * In case of any error returns: 
        `{"status": "error", "comment": <error text>}`
        """
        try:
            buildings_ids = chat_manager.get_user_contexts(user_id)
            if buildings_ids:
                return {"status": "success", "comment": "not empty", "buidings_ids": buildings_ids}
            return {"status": "success", "comment": "empty", "buidings_ids": []}
        except Exception as ex:
            return {"status": "error", "comment": ex}
            
       
    @app.post("/api/building/chat")
    def chat(
        user_id: str = Form(...),
        building_id: str = Form(...),
        user_request: str = Form(...)
    ):
        """**Chat with model**
              
        **ARGS:**
        * *user_id:* str
        * *building_id*: str
        * *user_request*: str

        **RETURNS:**
        * {"status": "success"}: json - in case of succesfull 
        """ 
        return chat_manager.request_to_llm(user_request, user_id, building_id)

    return app

app = create_app()
