from langchain_core.tools import tool
from langgraph.types import interrupt


@tool(description="查询订单信息会中途中断监控我的操作")
def query_order_info_tool(missing_fields: str, collected_data: str):
    """当日订单数据不完整时，请求人工补充缺少字段时
    调用此工具会暂停执行，在终端展示缺失字段和已收集数据
    等待人工输入补充信息后恢复


    :param missing_fields:
    :param collected_data:
    :return:
    """

    result=interrupt({
        "type": "query_order_info",
        "missing_fields": missing_fields,
        "collected_data": collected_data,
    })

    from langchain_classic.tools import json
    return json.dumps(result)