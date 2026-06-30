from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status, Body
from typing import List, Dict, Any
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv
import base64
import json
from pprint import pprint

load_dotenv()

import sys
sys.path.append('./scripts')

from chat_manager import ChatSessionManager
#chat_manager = ChatSessionManager(max_messages=50)
#print(hasattr(chat_manager, 'init_session'))



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

def concatenate_building_jsons(
    b_json: str,
    json_description: str):
    return f"###JSON with building parameters\n{b_json}\n###Description of the JSON keys\n{json_description}"

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
1. Initiate session for user with **user_id** about buiding with **building_id**. Use **/api/building/start** method.
2. Send user's prompt to LLM using **/api/building/chat**. LLM's responces is stored in history.
3. To get history use **/api/building/history**.
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
        building_id: str = Form(...),
        facade_img: UploadFile = File(...),
        roof_img: UploadFile = File(...),
        building_json: str = Body(...),
        json_description: str = Form(...)
    ):
        """
        **Session initiation.** <br/>
        To initiate a chat with `user_id` about `building_id` you must send `facade_img` and `roof_img` *(jpeg, png)*>.<br/>
        This two images are sent to AI module for exterior analysis. AI module returns analysis as text. <br/>
        Text data from other sources about this building is collected by backend of this API using `building_id` *(coming soon)*.<br/>
        All collected text data is used in QA agent. To read all collected text data about `building_id` use `/api/building/building_context`.

        Re-registration for pair (`user_id` and `building_id`) is not possible.<br/>
        In this case API returnd `Pair user_id <{user_id}> and building_id <{building_id}> has been registered.`.

        **ARGS:**
        * *user_id*: str
        * *building_id*: str
        * *image1*: UploadFile
        * *image2*: UploadFile

        **RETURNS:**
        * *{"status": "registered"}*: json - in case all data about the building was collected and recorded by backend successfully.<br/>
        Otherwise it returns error with status code and the error explanation.
        """

        try:
            building_info = json.loads(building_json)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid building_json: {e.msg}"
                )

        try:
            json_description = json.loads(json_description)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid json_description: {e.msg}"
                )

        building_info_str = str(building_info)
        json_description_str = str(json_description)
        cadastrial_context = concatenate_building_jsons(
            building_info_str,
            json_description_str)

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        buildings_ids = chat_manager.get_user_contexts(user_id)

        if type(buildings_ids) == list:
            if building_id in buildings_ids:
                return {
                    "status": "error",
                    "user_id": user_id,
                    "building_id": building_id,
                    "comment": f"Pair user_id <{user_id}> and building_id <{building_id}> has been registered."
                    }

        # Читаем байты обоих изображений
        facade_bytes = await facade_img.read()
        roof_bytes = await roof_img.read()

        try:
            facade_base64 = base64.b64encode(facade_bytes).decode("utf-8")
            roof_base64 = base64.b64encode(roof_bytes).decode("utf-8")

            resp = requests.post(
                analysis_api_url,
                json=get_payload(facade_base64, roof_base64),
                timeout=90,
            )

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"analysis api error: {resp.json()}")

            ai_data = resp.json()
            ai_context = json2md(ai_data)

            if not ai_context:
                raise HTTPException(
                    status_code=500,
                    detail="empty building text from analysis API")
            else:
                chat_manager.init_session(
                    user_id=user_id,
                    building_id=building_id,
                    ai_context=ai_context,
                    cadastrial_context=cadastrial_context)

                return {
                    "status": "registered",
                    "user_id": user_id,
                    "building_id": building_id}

        except Exception as e:
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "line_number": sys.exc_info()[2].tb_lineno,
                "file": sys.exc_info()[2].tb_frame.f_code.co_filename
                }
            pprint(error_details)
            raise HTTPException(
                status_code=500,
                detail=f"analysis api failed: {error_details}"
                )

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
                return {
                    "status": "success", "history": hist,
                    "user_id": user_id, "building_id": building_id}
            return {
                "status": "success", "comment": f"History for user_id <{user_id}> and building_id <{building_id}",
                "history": [], "user_id": user_id, "building_id": building_id}
        except Exception as e:
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "line_number": sys.exc_info()[2].tb_lineno,
                "file": sys.exc_info()[2].tb_frame.f_code.co_filename
                }

            return {
                "status": "error", "user_id": user_id,
                "building_id": building_id,
                "comment": f"Chat for user_id <{user_id}> and building_id <{building_id}> was not initiated."
                }

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
            return {
                "status": "success",
                "context": build_context,
                "building_id": building_id
                }
        return {
            "status": "error",
            "building_id": building_id,
            "comment": f"There is no context for building_id <{building_id}>"}

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
        try:
            chat_manager.request_to_llm(user_request, user_id, building_id)
            return {
                "status": "success",
                "user_id": user_id,
                "building_id": building_id
                }
        except Exception as e:
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "line_number": sys.exc_info()[2].tb_lineno,
                "file": sys.exc_info()[2].tb_frame.f_code.co_filename
                }
            pprint(error_details)
            return {
                "status": "error",
                "user_id": user_id,
                "building_id": building_id,
                "comment": error_details
                }

    return app

app = create_app()
