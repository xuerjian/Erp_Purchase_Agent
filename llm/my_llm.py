
from langchain_community.chat_models import ChatTongyi
from langchain_openai import ChatOpenAI

#阿里的通用大模型
# llm=ChatTongyi(model="qwen3.7-plus",streaming=True,
#                api_key="sk-ws-H.REDDIIH.XSEx.MEQCIAVO0fweooUwKWxBwmETA2nFqIGVXLTT0iwVnvuNBHXVAiB-p0O7uwDYWX_K57z2jvrFMWw-bPXrjoiEDnxivwKgLg",
#                 top_p=0.9,
#                max_retries=50
#                )


llm = ChatOpenAI(
    model="qwen3.7-plus",
    temperature=1.1,
    openai_api_key="sk-ws-H.REDDIIH.XSEx.MEQCIAVO0fweooUwKWxBwmETA2nFqIGVXLTT0iwVnvuNBHXVAiB-p0O7uwDYWX_K57z2jvrFMWw-bPXrjoiEDnxivwKgLg",
    openai_api_base="https://llm-jjahfel84vu866j1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    max_tokens=131072,
    extra_body= {"enable_thinking": False}
)