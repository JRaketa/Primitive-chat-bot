from typing import Dict, List
import os
from dotenv import load_dotenv
from google import genai
from pydantic import TypeAdapter
from google.genai import types
from pprint import pprint
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
        # { user_id : {building_id: gemini_chat}}
        self._chats: Dict[str, Dict[str, client.chats]] = {}
        # { building_id : context}
        self._contexts: Dict[str, Dict[str, str]] = {}
        # { building_id : file_url}
        self._contexts_url_files: Dict[str, str] = {}
        self.max_messages = max_messages
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = os.getenv("MODEL_ID")
        self.system_prompt = os.getenv("GEMINI_SYSTEM_INSTRUCTION")
        self.context_folder_path = os.getenv("CONTEXTS_FOLDER")
        self.history_adapter = TypeAdapter(list[types.Content])

    def save_context_as_txt(
        self, building_id: str,
        ai_context: str, cadastrial_context: str):
        """."""
        with open(self.get_ai_context_file_path(building_id), "w") as f:
            f.write(ai_context)
        with open(self.get_cadastrial_context_file_path(building_id), "w") as f:
            f.write(cadastrial_context)

    def get_ai_context_file_path(self, building_id:str):
        return self.context_folder_path + "_ai_context_" + building_id + ".txt"

    def get_cadastrial_context_file_path(self, building_id:str):
        return self.context_folder_path + "_cadastrial_context_" + building_id + ".txt"

    def load_context_to_vec_store(self, building_id:str):
        ai_context_path = self.get_ai_context_file_path(
            building_id)
        cadastrial_context_path = self.get_cadastrial_context_file_path(
            building_id)

        ai_context_url = self.client.files.upload(
            file=ai_context_path)
        cadastrial_context_url = self.client.files.upload(
            file=cadastrial_context_path)
        return ai_context_url, cadastrial_context_url

    def update_context(
        self, building_id:str,
        ai_context: str, cadastrial_context: str
        ):
        """Updates context for building_id"""
        self._contexts.update({
            building_id: {
                "ai_context": ai_context,
                "cadastrial_context": cadastrial_context
            }
        })

    def add_context(
        self, building_id:str,
        ai_context:str, cadastrial_context:str
        ):
        """."""
        self.update_context(
            building_id, ai_context, cadastrial_context)
        self.save_context_as_txt(
            building_id, ai_context, cadastrial_context
            )
        #file_path = self.get_context_file_path(building_id)
        ai_context_url, cadastrial_context_url = self.load_context_to_vec_store(building_id)
        self._contexts_url_files[building_id] = [
            ai_context_url, cadastrial_context_url
            ]

    def init_chat(self, user_id, building_id):
        self._chats[user_id] = {building_id: self.get_new_chat()}

    def get_user_contexts(self, user_id):
        user_chats = self._chats.get(user_id)
        if user_chats != None:
            return list(user_chats.keys())
        return None


    def get_new_chat(self):
        return self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt
                )
            )

    def init_session(self, user_id:str, building_id:str,
        ai_context: str, cadastrial_context: str):

        """."""
        self.add_context(
            building_id, ai_context, cadastrial_context)
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

    def get_role(self, msg):
        return msg.model_dump()['role']

    def get_text(self, msg):
        for part in msg.model_dump()['parts']:
            if part.get('text') != None:
                return part.get('text')

    def extract_replica_from_parts(self, msg):
        role = self.get_role(msg)
        text = self.get_text(msg)
        return {"role": role, "text": text}

    def extract_history(self, chat):
        history = []
        for msg in chat.get_history():
            history.append(self.extract_replica_from_parts(msg))
        return history

    def get_history(self, user_id, building_id):
        chat = self.get_chat(user_id, building_id)
        return self.extract_history(chat)

    def create_parts(self, files_urls):
        """."""
        all_parts = []
        for f_url in files_urls:
            all_parts.append(
                types.Part(
                    file_data=types.FileData(
                        file_uri=f_url.uri,
                        mime_type=f_url.mime_type)
                        ))
        return all_parts

    def request_to_llm(self, question, user_id, building_id):
        #context = self.get_user_context(user_id)
        #user_prompt = self.make_user_prompt(question, context)
        chat = self.get_chat(user_id, building_id)

        if chat == None:
            return {"status": "error", "Comment": f"The user chat with user_id '{user_id}' and building_id '{building_id}' has not been created!"}

        files_urls = self._contexts_url_files.get(building_id, None)

        if files_urls == None:
            return {
                "status": "error",
                "Comment": f"Vector store was not created for  {user_id} has not been created!"}

        all_parts = self.create_parts(files_urls)
        all_parts.append(question)
        chat.send_message(all_parts)

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
