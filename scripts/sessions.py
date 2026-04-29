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
        self._chats: Dict[str, client.chats] = {}
        # { building_id : context}
        self._contexts: Dict[str, str] = {}
        self.max_messages = max_messages
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = os.getenv("MODEL_ID")
        self.system_prompt = os.getenv("GEMINI_SYSTEM_INSTRUCTION")
        self.history_adapter = TypeAdapter(list[types.Content])


    def add_context(self, building_id:str, context: str):
        self._contexts[building_id] = context

    def get_context(self, building_id:str):
        return self._contexts.get(building_id, None)

    def get_user_context(self, user_id):
        building_id = self._current_context.get(user_id, None)
        return self.get_context(building_id)

    def set_current_context_id(self, user_id, building_id):
        self.init_chat(user_id)
        self._current_context.update({user_id: building_id})

    def get_current_context_id(self, user_id):
        return self._current_context.get(user_id, None)

    def get_new_chat(self):
        return self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt
                )
            )

    def init_chat(self, user_id):
        self._chats[user_id] = self.get_new_chat()

    def get_history(self, user_id):
        chat = self._chats.get(user_id, None)
        if chat != None:
            return chat.get_history()
        return None

    def make_user_prompt(self, question, context):
        return f"Context: {context}\n\nQuestion: {question}"

    def request_to_llm(self, question, user_id):
        context = self.get_user_context(user_id)
        user_prompt = self.make_user_prompt(question, context)
        chat = self._chats.get(user_id, None)

        if chat == None:
            return {"status": "error", "Comment": f"The user chat with id {user_id} has not been created!"}
        chat.send_message(user_prompt)
        self._chats.update({user_id: chat})
        return {"status": "success"}

    #def make_request_text(self, user_request, user_id):




    def get_users_ids(self):
        return list(self._current_context.keys())

    def get_history_json(self, user_id):
        chat_history = self.get_history(user_id)
        if not chat_history:
            return {"status": "empty", "comment": f"history is empty for user {user_id}"}
        return history_adapter.dump_json(chat_history)

    def send_mgs_to_llm(self, user_id, user_request):
        chat_history = self.get_history(user_id)
        if chat_history == None:
            return {"status": "fail", "comment": f"chat was not initiated for user {user_id}"}
        request_text = ''
        response = chat.send_message()
