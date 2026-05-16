from config import history_path, knowledge_path, max_split_char_number, user, md5_path, chunk_overlap, chunk_size, separators,vector_path, embedding_model_name
import os
import hashlib
import json
from datetime import datetime
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

embedding_function = OllamaEmbeddings(model=embedding_model_name)
spliter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,       # 分割后的文本段最大长度
        chunk_overlap=chunk_overlap,     # 连续文本段之间的字符重叠数量
        separators=separators,       # 自然段落划分的符号
        length_function=len,                # 使用Python自带的len函数做长度统计的依据
    )     # 文本分割器的对象
vector_store = Chroma(
        collection_name="SteamGames",
        embedding_function=embedding_function,
        persist_directory=vector_path
    )
def check_md5(input_str :str, encoding='utf-8'):
    if not os.path.exists(md5_path):
        open(md5_path, 'w', encoding='utf-8').close()
        return False
    else:
        str_bytes = input_str.encode(encoding=encoding)
        # 创建md5对象
        md5_obj = hashlib.md5()     # 得到md5对象
        md5_obj.update(str_bytes)   # 更新内容（传入即将要转换的字节数组）
        md5_hex = md5_obj.hexdigest()       # 得到md5的十六进制字符串
        with open(md5_path, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                line = line.strip()     # 处理字符串前后的空格和回车
                if line == md5_hex:
                    return True         # 已处理过
        return False
        
def update_md5(input_str :str, encoding='utf-8'):
    str_bytes = input_str.encode(encoding=encoding)

    # 创建md5对象
    md5_obj = hashlib.md5()     # 得到md5对象
    md5_obj.update(str_bytes)   # 更新内容（传入即将要转换的字节数组）
    md5_hex = md5_obj.hexdigest()       # 得到md5的十六进制字符串
    with open(md5_path, 'a', encoding="utf-8") as f:
        f.write(md5_hex + '\n')

def addKnowledge(Knowledge: str, filename):
    
    if(check_md5(Knowledge)):
        return f"[Failed]The {filename} already exists"
        
    if len(Knowledge) > max_split_char_number:
        knowledge_chunks: list[str] = spliter.split_text(Knowledge)
    else:
        knowledge_chunks = [Knowledge]
        
    metadata = {
        "source": filename,
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operator": user,
    }
    vector_store.add_texts(
        knowledge_chunks,
        metadatas = [metadata for _ in knowledge_chunks]
    )
    update_md5(Knowledge)
    
    return f"[Success]Add {filename} into vector database"

if __name__ == '__main__':
    for file_name in os.listdir(knowledge_path):
        file_path = os.path.join(knowledge_path, file_name)
        if not file_name.endswith('.json'):
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                text = json.dumps(data, ensure_ascii=False)        
                res = addKnowledge(text, file_name)
                print(res)
        except Exception as e:
            print(f"读取 {file_name} 时出错: {e}")

