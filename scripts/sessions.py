from typing import Dict, List
import os
from dotenv import load_dotenv
from google import genai
from pydantic import TypeAdapter
from google.genai import types
from pprint import pprint
from uuid import uuid4
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
        # { user_id : list(building_id)}
        self._user_contexts_registered: Dict[str, list] = {}
        # { user_id : {building_id: gemini_chat}}
        self._chats: Dict[str, Dict[str, client.chats]] = {}
        # { user_id : {building_id: {subsession_id: gemini_chat}}}
        self._subsession: Dict[str, Dict[str, Dict[str, client.chats]]] = {}
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

    #def init_subsession(sessions, user_id, building_id, subsession_id):
        # Создаём вложенность, если её нет: user_id -> {}
#        user_dict = sessions.setdefault(user_id, {})

        # Создаём/получаем словарь building_id внутри user_id
#        building_dict = user_dict.setdefault(building_id, {})

        # Добавляем subsession_id (если такой уже есть — перезапишет, если нужно только при отсутствии, см. ниже)
#        building_dict[subsession_id] = self.get_new_chat()

#        return sessions

    def update_subsession(
        self, user_id: str,
        building_id: str, subsession_id: str
        ):
        """."""

        user_sessions = self._subsession.get(user_id)
        if user_sessions != None:
            user_subsessions = user_sessions.get(building_id)
            if user_subsessions != None:
                self._subsession[user_id][building_id][subsession_id] = self.get_new_chat()
            else:
                self._subsession.update({
                    user_id: {
                        building_id: {
                            subsession_id: self.get_new_chat()
                            }
                        }
                    })
        else:
            self._subsession.update({
                user_id: {
                    building_id: {
                        subsession_id: self.get_new_chat()
                        }
                    }
                })


    def init_subsession(self, user_id: str, building_id: str):
        # { user_id : {building_id: {subsession_id: gemini_chat}}}
        subsession_id = str(uuid4())

        self.update_subsession(
            user_id, building_id, subsession_id
            )
        return subsession_id


    def get_user_subsessions_report(self, user_subsessions):
        buildings_ids_list = list(user_subsessions.keys())
        report_dict = {}
        for buildings_id in buildings_ids_list:
            subsessions_list = list(user_subsessions.get(buildings_id).keys())
            report_dict[buildings_id] = subsessions_list
        return report_dict


    def get_user_subsessions(self, user_id):
        user_subsessions = self._subsession.get(user_id)
        if user_subsessions == None:
            return {
                "status": "error",
                "user_id": user_id,
                "user_subsessions": [],
                "comment": "subsessions list is empty"
            }
        user_subsessions_list = list(user_subsessions.keys())
        return {
            "status": "success",
            "user_id": user_id,
            "user_subsessions": user_subsessions_list,
            "comment": ""
        }


    def no_subsession_responce(self, user_id, building_id):
        return {
            "status": "error",
            "user_id": user_id,
            "building_id": building_id,
            "comment": "no subsessions registered"}

    def subsessions_list_responce(
        self, user_id,
        building_id, building_sub):
        return {
            "user_id": user_id,
            "building_id": building_id,
            "subsessions_list": list(building_sub.keys())}

    def get_subsessions_list(self, user_id, building_id):
        user_sub = self._subsession.get(user_id)
        if user_sub != None:
            building_sub = user_sub.get(building_id)
            if building_sub != None:
                if list(building_sub.keys()):
                    return self.subsessions_list_responce(
                        user_id, building_id, building_sub)
                else:
                    return self.no_subsession_responce(user_id, building_id)
            else:
                return self.no_subsession_responce(user_id, building_id)
        else:
            return self.no_subsession_responce(user_id, building_id)

    def init_chat(self, user_id, building_id):
        self._chats[user_id] = {building_id: self.get_new_chat()}


    def get_new_chat(self):
        return self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt
                )
            )

    def init_user_buildings_registries(
        self, user_id:str, building_id:str
        ):
        self._user_contexts_registered.update({
            user_id: [building_id]
            })

    def get_user_buildings_ids(self, user_id):
        if self._user_contexts_registered.get(user_id) == None:
            return []
        return self._user_contexts_registered.get(user_id)

    def get_registered_contexts(self):
        return list(self._contexts.keys())


    def add_building_to_user_context(
        self, user_id:str, building_id:str
        ):
        users_building_ids = self.get_user_buildings_ids(user_id)
        users_building_ids.append(building_id)
        self._user_contexts_registered.update({
            user_id: users_building_ids})

    def update_user_contexts(
        self, user_id:str, building_id:str
        ):
        users_building_ids = self._user_contexts_registered.get(user_id)
        if users_building_ids == None:
            self.init_user_buildings_registries(user_id, building_id)
            return False
        if building_id in users_building_ids:
            return True
        else:
            return False

    def save_context_as_txt(
        self, building_id: str,
        ai_context: str, cadastrial_context: str):
        """."""
        with open(self.get_ai_context_file_path(building_id), "w") as f:
            f.write(ai_context)
        with open(self.get_cadastrial_context_file_path(building_id), "w") as f:
            f.write(cadastrial_context)


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
        if building_id not in self.get_registered_contexts():
            self.update_context(
                building_id, ai_context, cadastrial_context)
            self.save_context_as_txt(
                building_id, ai_context, cadastrial_context
                )
            ai_context_url, cadastrial_context_url = self.load_context_to_vec_store(building_id)
            self._contexts_url_files[building_id] = [
                ai_context_url, cadastrial_context_url
                ]

    def init_session(
        self, user_id:str, building_id:str,
        ai_context: str, cadastrial_context: str
        ):
        """."""
        self.add_context(
            building_id, ai_context, cadastrial_context)

        if building_id in self.get_user_buildings_ids(user_id):
            return {
                "status": "error",
                "user_id": user_id,
                "building_id": building_id,
                "comment": (
                    f"context for pair user_id {user_id} and "
                    f"building_id {building_id} has already been registered")
                }
        self.add_building_to_user_context(user_id, building_id)
        subsession_id = self.init_subsession(
            user_id, building_id)
        return {
            "status": "success",
            "user_id": user_id,
            "building_id": building_id,
            "subsession_id": subsession_id
        }


        self._current_context.update({user_id: building_id})

    def get_context(self, building_id:str):
        return self._contexts.get(building_id, None)

    def get_user_context(self, user_id):
        building_id = self._current_context.get(user_id, None)
        return self.get_context(building_id)

    def get_current_context_id(self, user_id):
        return self._current_context.get(user_id, None)

    def get_chat(
        self, user_id: str,
        building_id: str, subsession_id: str
        ):
        user_sessions = self._subsession.get(user_id)
        if user_sessions == None:
            return None
        user_subsessions = user_sessions.get(building_id)
        if user_subsessions == None:
            return None
        chat = user_subsessions.get(subsession_id)
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

    def get_history(
        self, user_id: str,
        building_id: str, subsession_id: str
        ):
        chat = self.get_chat(
            user_id, building_id, subsession_id
            )
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

    def request_to_llm(self, question, user_id, building_id, subsession_id):
        #context = self.get_user_context(user_id)
        #user_prompt = self.make_user_prompt(question, context)
        chat = self.get_chat(user_id, building_id, subsession_id)
        print("chat:", chat)
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
        print("chat:", chat)
        self._subsession.update({
            user_id: {
                building_id: {
                    subsession_id: chat
                }
            }
        })
#        return {"status": "success"}

    def get_users_ids(self):
        return list(self._subsession.keys())

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
