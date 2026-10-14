import os
from datetime import datetime
from typing import Dict, Any


from agentconfig import mongo_client

class MongoDBService:

    __FIELD_MAX_LENGTH = 500_000

    #获取当前会话的历史消息
    async def get_history_messages_in_current_session(self,thread_id:str):

        database=mongo_client.get_database(os.getenv("MGDB_DATABASE_NAME",default="context_db"))
        collection=database.get_collection("history_messages_in_session")

        #获取游标
        cursor=collection.find({"thread_id":thread_id}).sort("index",1)

        docs = list(cursor)

        if not docs:
            return None

        return [doc["message"] for doc in docs]



    #保存会话消息
    async def save_display_messages(self, thread_id: str, messages: list[Dict[str, Any]]) -> bool:
        database = mongo_client.get_database(os.getenv("MGDB_DATABASE_NAME", default="context_db"))
        collection = database.get_collection("history_messages_in_session")

        collection.delete_many({"thread_id":thread_id})

        collection.create_index([("thread_id", 1), ("index", 1)])

        if not messages:
            return False
        now = datetime.now()
        docs = None
        for i, message in enumerate(messages):
            message=self.__trunc_message_by_fields()
            if docs is None:
                docs=[]
            docs.append({
                "thread_id":thread_id,
                "index":i,
                "message":message,
                "updated_at":now,
            })
        collection.insert_many(docs)
        return True


    def __trunc_message_by_fields(self,message: Dict[str, Any]) -> Dict[str, Any]:
        for field in ("text","args","content"):
            if field in message and isinstance(message[field], str) and len(message[field]) > self.__FIELD_MAX_LENGTH :
                message[field] = message[field][:self.__FIELD_MAX_LENGTH]
            return message
