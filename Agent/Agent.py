from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict, HumanMessage, AIMessage
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import Sequence
import os, json
from config import user, model_name, embedding_model_name, history_path, vector_path, knowledge_path, md5_path, chunk_size, chunk_overlap,  separators, max_split_char_number
import hashlib
from datetime import datetime
import sys


class Agent(BaseChatMessageHistory):
    def __init__(self, session_id, storage_path, vector_path):
        self.model = OllamaLLM(model=model_name)
        self.str_parser = StrOutputParser()
        self.session_id = session_id        
        self.storage_path = storage_path    
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "As a professional Steam data analysis and game recommendation expert, you will provide concise and professional answers to user questions, primarily based on the known references and chat historyI have provided. References: {context}"),
                MessagesPlaceholder(variable_name="history"),
                ("user", "The user asks：{input}")
            ]
        )
        self.file_path = os.path.join(self.storage_path, self.session_id)
        self.embedding_function = OllamaEmbeddings(model=embedding_model_name)
        self.vector_store = Chroma(
            collection_name="SteamGames",
            embedding_function=self.embedding_function,
            persist_directory=vector_path
        )
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,      
            chunk_overlap=chunk_overlap,    
            separators=separators,       
            length_function=len,               
        )    
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def print_prompt(self, prompt):
        print(prompt.to_string())
        print("=" * 20)
        return prompt

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
       
        all_messages = list(self.messages)      
        all_messages.extend(messages)          
        new_messages = [message_to_dict(message) for message in all_messages]
      
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(new_messages, f, ensure_ascii=False)
    
    def check_md5(self, input_str :str, encoding='utf-8'):
        if not os.path.exists(md5_path):
            open(md5_path, 'w', encoding='utf-8').close()
            return False
        else:
            str_bytes = input_str.encode(encoding=encoding)

            # 创建md5对象
            md5_obj = hashlib.md5()     
            md5_obj.update(str_bytes)  
            md5_hex = md5_obj.hexdigest()      
            with open(md5_path, 'r', encoding='utf-8') as f:
                for line in f.readlines():
                    line = line.strip()    
                    if line == md5_hex:
                        return True        
            return False
        
    def update_md5(self, input_str :str, encoding='utf-8'):
        str_bytes = input_str.encode(encoding=encoding)

        # 创建md5对象
        md5_obj = hashlib.md5()     
        md5_obj.update(str_bytes)  
        md5_hex = md5_obj.hexdigest()       
        with open(md5_path, 'a', encoding="utf-8") as f:
            f.write(md5_hex + '\n')
    
    def addKnowledge(self, Knowledge: str, filename: str):
        if(self.check_md5(Knowledge)):
            return f"[Failed]The {filename} already exists"
        
        if len(Knowledge) > max_split_char_number:
            knowledge_chunks: list[str] = self.spliter.split_text(Knowledge)
        else:
            knowledge_chunks = [Knowledge]
        
        metadata = {
            "source": filename,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator": user,
        }
        self.vector_store.add_texts(
            knowledge_chunks,
            metadatas = [metadata for _ in knowledge_chunks]
        )
        self.update_md5(Knowledge)
        return f"[Success]Add {filename} into vector database"

    @property
    def messages(self) -> list[BaseMessage]:
      
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                messages_data = json.load(f)   
                return messages_from_dict(messages_data)
        except FileNotFoundError:
            return []

    def clear(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    def format_func(self, docs: list[Document]):
        if not docs:
            return "No related References"

        return "\n\n".join(
        [
            f"Reference {i+1}:\n{doc.page_content}"
            for i, doc in enumerate(docs)
        ]
    )

    def Call(self, question: str, k=3, verbose=False):
        retriever = self.vector_store.as_retriever(search_kwargs={"k": k}) 
        chain = (
            {"input":RunnablePassthrough(), "context": retriever | self.format_func, "history": lambda _ : self.messages[-10:]} |
            self.prompt |
            # self.print_prompt |
            self.model |
            self.str_parser
        )
        res = chain.stream(question)
        response = ""
        for chunk in res:
            if verbose:
                print(chunk, end="", flush=True)
            response += chunk
        
        self.add_messages([
            HumanMessage(content=question),
            AIMessage(content=response)
        ])

        return response

    
            


if __name__ == '__main__':
    SteamAgent = Agent(user, history_path, vector_path)


    # for file_name in os.listdir(knowledge_path):
    #     file_path = os.path.join(knowledge_path, file_name)
    #     if not file_name.endswith('.json'):
    #         continue
    #     try:
    #         with open(file_path, 'r', encoding='utf-8') as f:
    #             data = json.load(f)
    #             text = json.dumps(data, ensure_ascii=False)        
    #             res = SteamAgent.addKnowledge(text, file_name)
    #             print(res)
    #     except Exception as e:
    #         print(f"Read {file_name} error, {e}")

    #  python Agent.py "how about the \"outer wilds\""
    input_question =  sys.argv[1]
    SteamAgent.Call(input_question)