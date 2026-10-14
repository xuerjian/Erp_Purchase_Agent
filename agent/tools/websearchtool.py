import os

from langchain.tools import tool

from zai import ZhipuAiClient

# llm = ChatOpenAI(
#     model="qwen-plus",
#     api_key=os.getenv("LLM_API_KEY"),
#     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
#     extra_body={"enable_search": True} # 开启平台原生web_search
# )

# 创建React Agent，模型自动调用web搜索
# agent = create_react_agent(llm, tools=[])

ZhipuAiClient(api_key=os.getenv("ZHIPU_API_KEY"))
#from langchain_openai import ChatOpenAI

@tool
def web_search_tool(query:str):
    # resp = agent.invoke({"messages": [("user", query)]})
    try:
        resp=ZhipuAiClient.web_search().web_search(search_engine="search_pro",
                search_query=query,
                count=3,  # 返回结果的条数，范围1-50，默认10
                search_recency_filter="noLimit", # 搜索指定日期范围内的内容
                 )
        if resp.search_result:
            return "\n\n".join([d.content for d in resp.search_result])
        return '没有搜索到任何内容！'
    except Exception as e:
        return f"搜索失败: {e}"
