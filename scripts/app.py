from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status, Body, Query
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field
import os
import requests
from dotenv import load_dotenv
import base64
import json
from pprint import pprint

load_dotenv()

import sys
sys.path.append('./scripts')

from sessions import ChatSessionManager
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
1. Initiate a session for user with **user_id** about buiding with **building_id**. Use **/api/building/start** method.
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

    class StartResponse(BaseModel):
        status: str = Field(examples=[
            "success", "error"
            ])
        user_id: str = Field(example="u123")
        building_id: str = Field(example="b456")
        subsession_id: str = Field(examples=[
            "a3f7c9b1-2d8e-4a5c-901b-3e7f6d8a2c4d", ""])
        comment: str = Field(examples=[
            "", "Pair has been registered"
            ])


    @app.post(
        "/api/building/start",
        response_model=StartResponse)
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
        To initiate a chat with **user_id** about **building_id** you must send **facade_img** and **roof_img** *(jpeg, png)*><br/>
        to get context from ai analysis. <br/>
        **building_json** - cadastrial data in json format, **json_description** - description of **building_json**'s keys in json format'.
        Note! Send **str(building_json)** and **str(json_description)** in this API.
        All collected text data is used in QA agent. To read all collected text data about **building_id** use **/api/building/building_context**.

        Re-registration for pair (**user_id** and **building_id**) is not possible.<br/>
        In this case API returnd **Pair user_id <{user_id}> and building_id <{building_id}> has been registered.**.

        **ARGS:**
        * **user_id**: str
        * **building_id**: str
        * **image1**: UploadFile
        * **image2**: UploadFile
        * **building_json**: str(json),
        * **json_description**: str(json)

        **RETURNS (json):**<br/>
        ```json
        {
            "status": "success",
            "user_id": user_id,
            "building_id": building_id,
            "subsession_id": subsession_id
        }
        ```

        In case all data about the building was collected and recorded by backend successfully.<br/>
        Otherwise it returns error with status code and the error explanation.

        **subsession_id** is an idententifier of a chat about specific building. It keeps chat history.
        If you need to create one more subsession for **user_id** about **building_id**, for example about different topic, use **/api/building/init_subsession** method.
        """

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        buildings_ids = chat_manager.get_user_buildings_ids(user_id)

        if buildings_ids != None:
            if building_id in buildings_ids:
                return StartResponse(
                    status = "error",
                    user_id = user_id,
                    building_id = building_id,
                    subsession_id = "",
                    comment = "Pair has been registered"
                )

        try:
            if building_id not in chat_manager.get_registered_contexts():
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

                facade_bytes = await facade_img.read()
                roof_bytes = await roof_img.read()

                facade_base64 = base64.b64encode(facade_bytes).decode("utf-8")
                roof_base64 = base64.b64encode(roof_bytes).decode("utf-8")

                resp = requests.post(
                    analysis_api_url,
                    json=get_payload(facade_base64, roof_base64),
                    timeout=90,
                    )

                if resp.status_code != 200:
                    print(resp)
                    raise HTTPException(
                        status_code=500,
                        detail=f"analysis api error: {resp.json()}")

                ai_data = resp.json()
                ai_context = json2md(ai_data)

                if not ai_context:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "status": "error",
                            "user_id": user_id,
                            "building_id": building_id,
                            "comment":"empty building text from analysis API"})

                init_session_responce = chat_manager.init_session(
                    user_id=user_id,
                    building_id=building_id,
                    ai_context=ai_context,
                    cadastrial_context=cadastrial_context)
            else:
                init_session_responce = chat_manager.init_session(
                    user_id=user_id,
                    building_id=building_id,
                    ai_context="",
                    cadastrial_context="")

            return StartResponse(
                status = init_session_responce.get("status"),
                user_id = user_id,
                building_id = building_id,
                subsession_id = init_session_responce.get("subsession_id"),
                comment = init_session_responce.get("comment")
            )

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

    class InitSubsessionRequest(BaseModel):
        user_id: str
        building_id: str

    class InitSubsessionResponse(BaseModel):
        status: str = Field(examples=[
            "success", "error"
            ])
        user_id: str = Field(example="u123")
        building_id: str = Field(example="b456")
        subsession_id: str = Field(examples=[
            "a3f7c9b1-2d8e-4a5c-901b-3e7f6d8a2c4d", ""
            ])

    @app.post(
        "/api/building/init_subsession",
        response_model=InitSubsessionResponse)
    async def init_subsession(
        payload: InitSubsessionRequest
    ):

        users_building_ids = chat_manager.get_user_buildings_ids(payload.user_id)

        if type(users_building_ids) == list:
            if payload.building_id in users_building_ids:
                subsession_id = chat_manager.init_subsession(
                    payload.user_id, payload.building_id)
                return InitSubsessionResponse(
                    status = "success",
                    subsession_id = subsession_id,
                    user_id = payload.user_id,
                    building_id = payload.building_id
                    )
            else:
                return InitSubsessionResponse(
                    status = "error",
                    subsession_id = "",
                    user_id = payload.user_id,
                    building_id = payload.building_id
                    )
        else:
            return InitSubsessionResponse(
                status = "error",
                subsession_id = "",
                user_id = payload.user_id,
                building_id = payload.building_id
                )


    class HistoryRequest(BaseModel):
        user_id: str = Field(...)
        building_id: str = Field(...)
        subsession_id: str = Field(...)

    class ChatMessage(BaseModel):
        role: Literal["user", "assistant", "system"]
        content: str

    class HistoryRespoce(BaseModel):
        status: str = Field(examples=[
            "success", "error"
            ])
        user_id: str = Field(example="string")
        building_id: str = Field(example="string")
        subsession_id: str = Field(examples=[
            "a3f7c9b1-2d8e-4a5c-901b-3e7f6d8a2c4d", ""
            ])
        comment: str = Field(example="string")
        history: List = Field(example=[
            [
                {"role": "user", "content": "How many floors?"},
                {"role": "model", "content": "The building has 6 floors."},
            ]
        ])

    @app.get(
        "/api/building/history",
        response_model=HistoryRespoce)
    def get_history(
        user_id: str = Query(...),
        building_id: str = Query(...),
        subsession_id: str = Query(...)
        ):
        """**Returns chat bot history for **user_id** and **building_id**.**

        **ARGS:**
        * **user_id:** str
        * **building_id:** str
        * **subsession_id:** str

        **RETURNS:**
        * **history:** list of jsons

        **HISTORY FORMAT:**
        ```
        [
            {'role': 'user', 'content': <text>},
            {'role': 'system', 'content': <text>},
            {'role': 'user', 'content': <text>},
            ... ...
        ]
        ```
        """
        try:
            hist = chat_manager.get_history(
                user_id, building_id, subsession_id
                )
#            print("hist:", chat_manager._subsession)
            if hist:
                return HistoryRespoce(
                    status = "success",
                    comment =  "",
                    history = hist,
                    user_id = user_id,
                    building_id = building_id,
                    subsession_id = subsession_id
                    )
            return HistoryRespoce(
                status = "success",
                comment =  "empty",
                history = [],
                user_id = user_id,
                building_id = building_id,
                subsession_id = subsession_id
                )
        except Exception as e:
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "line_number": sys.exc_info()[2].tb_lineno,
                "file": sys.exc_info()[2].tb_frame.f_code.co_filename
                }
            pprint(error_details)
#            print("_subsessionS:", chat_manager._subsession)
            return HistoryRespoce(
                status = "error",
                comment =  "Chat was not initiated",
                history = [],
                user_id = user_id,
                building_id = building_id,
                subsession_id = subsession_id
                )

    class UsersRespoce(BaseModel):
        users_ids: List = Field(examples=[
            ["usr_id1", "usr_id2"]
            ])

    @app.get(
        "/api/building/users",
        response_model=UsersRespoce)
    def get_users():
        """**Returns list of registered users id.**

        Requires no params.
        """
        return UsersRespoce(
            users_ids = chat_manager.get_users_ids()
        )

    class BuildingContextRequest(BaseModel):
        building_id: str = Field(example="string")

    class BuildingContextRespoce(BaseModel):
        status: str = Field(examples=[
            "success", "error"
            ])
        building_id: str = Field(example="string")
        cadastrial_context: str = Field(example="### Context in MD format")
        ai_context: str = Field(example="### Context in MD format")
        comment: str = Field(example="string")



    @app.get(
        "/api/building/building_context",
        response_model=BuildingContextRespoce)
    def get_context(
        building_id: str = Query(...)
        ):
        """Building's context is all text data was collected on registration **/api/building/start**.
        Context is used as knowledge base for the QA agent.
        **Returns context  for **building_id**.**

        **ARGS:**
        * **building_id:** str

        **RETURNS:**
        * If context of *building_id* exists in DB returns json:
        ```json
        {
            "status": "success",
            "context": build_context,
            "building_id": building_id
        }
        ```
        * Otherwise, a json is returned with error description.
        """
        build_context = chat_manager.get_context(building_id)
        if build_context:
            return BuildingContextRespoce(
                status = "success",
                cadastrial_context = build_context.get("cadastrial_context", ""),
                ai_context = build_context.get("ai_context", ""),
                building_id = building_id,
                comment = ""
                )
        return BuildingContextRespoce(
            status = "error",
            cadastrial_context = build_context.get("cadastrial_context", ""),
            ai_context = build_context.get("ai_context", ""),
            building_id = building_id,
            comment = "Context was not loaded"
            )

    class UserSessionRequest(BaseModel):
        user_id: str = Field(example="string")

    class UserSessionRespoce(BaseModel):
        status: str = Field(examples=[
            "success", "error"
            ])
        user_id: str = Field(example="b456")
        buidings_ids: List = Field(
            example=["B_id_1", "B_id_1", "B_id_1"]
            )
        comment: str = Field(example="string")


    @app.get(
        "/api/building/user_sessions",
        response_model=UserSessionRespoce)
    def get_user_contexts(
        user_id: str = Query(...)
    ):
        """**Returns all **building_ids** that **user_id** requested for analysis.**

        **ARGS:**
        * *user_id:* str

        **RETURNS:**
        * If **user_id** has requested info about several **building_ids** returns the next *json*:  list of building's ids: list:<br/>
        **{
            "status": "success",
            "comment": "not empty",
            "buidings_ids": [<building_id>, <building_id>, ...]
        }**
        * If **user_id** has not requested info about any building returns the next json:<br/>
        **{"status": "success", "comment": "empty", "buidings_ids": []}**
        * In case of any error returns:
        **{"status": "error", "comment": <error text>}**
        """
        try:
            buildings_ids = chat_manager.get_user_buildings_ids(user_id)
            if buildings_ids:
                return UserSessionRespoce(
                    user_id = user_id,
                    status = "success",
                    buidings_ids = buildings_ids,
                    comment = ""
                    )
            return UserSessionRespoce(
                user_id = user_id,
                status = "error",
                buidings_ids = [],
                comment = "empty"
                )
        except Exception as ex:
            return UserSessionRespoce(
                user_id = user_id,
                status = "error",
                buidings_ids = [],
                comment = ex
                )

    class SubsessionsRequest(BaseModel):
        user_id: str = Field(...)
        building_id: str = Field(...)

    class SubsessionsRespoce(BaseModel):
        status: str = Field(examples=[
            "success", "error"
            ])
        user_id: str = Field(example="b456")
        building_id: str = Field(example="u123")
        subsessions_list: List = Field(example=[["id_123", "id_54"]])
        comment: str = Field(example="")


    @app.get(
        "/api/building/subsessions",
        response_model=SubsessionsRespoce)
    def get_user_subsessions(
        user_id: str = Query(...),
        building_id: str = Query(...)
        ):
        try:
            subsess_responce = chat_manager.get_subsessions_list(
                user_id, building_id
                )
            return SubsessionsRespoce(
                status=subsess_responce.get("status"),
                user_id=user_id,
                building_id=building_id,
                subsessions_list=subsess_responce.get("subsessions_list"),
                comment=subsess_responce.get("comment")
                )
        except Exception as e:
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "line_number": sys.exc_info()[2].tb_lineno,
                "file": sys.exc_info()[2].tb_frame.f_code.co_filename
                }
            pprint(error_details)
            return SubsessionsRespoce(
                status="error",
                user_id=user_id,
                building_id=building_id,
                subsessions_list=[],
                comment=str(e)
                )

    class ChatRequest(BaseModel):
        user_id: str
        building_id: str
        subsession_id: str
        user_request: str

    class ChatMessage(BaseModel):
        role: Literal["user", "assistant", "system"]
        content: str

    class ChatResponse(BaseModel):
        status: str = Field(example="success")
        user_id: str = Field(example="u123")
        building_id: str = Field(example="b456")
        subsession_id: str = Field(example="s789")
        comment: str = Field(example="string")
        model_respoce: str = Field(example="string")
        #List[ChatMessage] = Field(
        #    default_factory=list,
        #    example=[
        #        {"role": "user", "content": "How many floors?"},
        #        {"role": "model", "content": "The building has 6 floors."},
        #    ],
        #)

    @app.post(
        "/api/building/chat",
        response_model=ChatResponse,          # <-- это обязательно
        summary="Chat with model",
        #description=".",
        )
    def chat(
        user_id: str = Query(...),
        building_id: str = Query(...),
        subsession_id: str = Query(...),
        user_request: str = Query(...)
        ):

        try:
            chat_response = chat_manager.request_to_llm(
                user_request,
                user_id,
                building_id,
                subsession_id,
                )
            return ChatResponse(
                status=chat_response.get("status"),
                user_id=user_id,
                building_id=building_id,
                subsession_id=subsession_id,
                comment = chat_response.get("comment"),
                model_respoce=chat_response.get("last_responce", ""),
                )
        except Exception as e:
            import sys, traceback, pprint
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "line_number": sys.exc_info()[2].tb_lineno,
                "file": sys.exc_info()[2].tb_frame.f_code.co_filename,
                }
            pprint.pprint(error_details)
            return ChatResponse(
                status="error",
                user_id=user_id,
                building_id=building_id,
                subsession_id=subsession_id,
                comment = e,
                model_respoce=""
                )
    return app

app = create_app()
