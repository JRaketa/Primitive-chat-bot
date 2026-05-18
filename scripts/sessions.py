from typing import Dict, List
import os
from dotenv import load_dotenv
from google import genai
from pydantic import TypeAdapter
from google.genai import types

#crew_llm = os.getenv("MAX_HISTORY_MESSAGES")
#system_prompt = os.getenv("GEMINI_SYSTEM_INSTRUCTION")



class ChatSessionManager:
    """
    Пока в памяти, позже можно заменить на Postgres.
    Хранит полную историю общения с LLM.
    """

    def __init__(self, max_messages: int):
        # { user_id -> { "context": "...", "history": [...] } }
        self._sessions: Dict[str, dict] = {}
        # { user_id : building_id}
        self._current_context: Dict[str, dict] = {}
        # { user_id : gemini_chat}
        self._chats: Dict[str, Dict[str, client.chats]] = {}
        # { building_id : context}
        self._contexts: Dict[str, str] = {}
        # { building_id : file_url}
        self._contexts_url_files: Dict[str, str] = {}
        self.max_messages = max_messages
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = os.getenv("MODEL_ID")
        self.system_prompt = os.getenv("GEMINI_SYSTEM_INSTRUCTION")
        self.context_folder_path = os.getenv("CONTEXTS_FOLDER")
        self.history_adapter = TypeAdapter(list[types.Content])

    def save_context_as_txt(self, building_id: str, context: str):
        with open(self.get_context_file_path(building_id), "w") as f:
            f.write(context)

    def get_context_file_path(self, building_id:str):
        return self.context_folder_path + building_id + ".txt"

    def load_context_to_vec_store(self, building_id:str):
        file_path = self.get_context_file_path(building_id)
        my_file = self.client.files.upload(
            file=file_path)
        return my_file

    def add_context(self, building_id:str, context: str):
        self._contexts[building_id] = context
        self.save_context_as_txt(building_id, context)
        file_path = self.get_context_file_path(building_id)
        file_url = self.load_context_to_vec_store(building_id)
        self._contexts_url_files[building_id] = file_url

    def init_chat(self, user_id, building_id):
        self._chats[user_id] = {building_id: self.get_new_chat()}

    def get_new_chat(self):
        return self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt
                )
            )

    def init_session(self, user_id:str, building_id:str, context: str):
        self.add_context(building_id, context)
        self.init_chat(user_id, building_id)
        self._current_context.update({user_id: building_id})

    def get_context(self, building_id:str):
        return self._contexts.get(building_id, None)

    def get_user_context(self, user_id):
        building_id = self._current_context.get(user_id, None)
        return self.get_context(building_id)

    def get_current_context_id(self, user_id):
        return self._current_context.get(user_id, None)

    def get_chat(self, user_id, building_id):
        chat = self._chats.get(user_id, None)
        if chat == None:
            return None
        chat = chat.get(building_id, None)
        if chat == None:
            return None
        return chat

    def get_history(self, user_id, building_id):
        return self.get_chat(user_id, building_id).get_history()

#    def make_user_prompt(self, question, context):
#        return f"Context: {context}\n\nQuestion: {question}"

    def request_to_llm(self, question, user_id, building_id):
        #context = self.get_user_context(user_id)
        #user_prompt = self.make_user_prompt(question, context)
        chat = self.get_chat(user_id, building_id)

        if chat == None:
            return {"status": "error", "Comment": f"The user chat with id {user_id} has not been created!"}

        file_url = self._contexts_url_files.get(building_id, None)

        if file_url == None:
            return {"status": "error", "Comment": f"Vector store was not created for  {user_id} has not been created!"}
        chat.send_message(
            [
                types.Part(
                    file_data=types.FileData(
                        file_uri=file_url.uri,
                        mime_type=file_url.mime_type
                        )
                    ),
                    question
                ]
            )
        self._chats.update({user_id: {building_id: chat}})
        return {"status": "success"}

    def get_users_ids(self):
        return list(self._current_context.keys())

    def get_history_json(self, user_id, building_id):
        chat_history = self.get_history(user_id, building_id)
        if not chat_history:
            return {
                "status": "empty",
                "comment": f"history is empty for user_id: {user_id} and building_id: {building_id}"
                }
        return self.history_adapter.dump_json(chat_history)

#    def send_mgs_to_llm(self, user_id, building_id, user_request):
#        chat_history = self.get_history(user_id, building_id)
#        if chat_history == None:
#            return {"status": "fail", "comment": f"chat was not initiated for user {user_id}"}
#        request_text = ''
#        response = chat.send_message()
