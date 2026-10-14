#mcp客户端
import os

from langchain_mcp_adapters.client import MultiServerMCPClient


JOIN_STR="."
MCP_URL_STR="url"
MCP_TRANSPORT_STR="transport"

class McpClient:

    async def get_mcp_tools(self,mcp_name:str)-> list[BaseTool]:

        #获取mcp服务相关配置信息
        mcp_server_url=os.getenv(mcp_name.upper()+JOIN_STR+MCP_URL_STR)
        mcp_server_transport=os.getenv(mcp_name.upper()+JOIN_STR+MCP_TRANSPORT_STR)
        mcp_config={mcp_name:{
            MCP_URL_STR:mcp_server_url,
            MCP_TRANSPORT_STR:mcp_server_transport
        }}

        mcp_client=MultiServerMCPClient(mcp_config)

        mcp_tools=await mcp_client.get_tools(server_name=mcp_name)
        return mcp_tools


    # async def handle_tools(chart_mcp_tools: list):
    #     """
    #     :对工具进行筛选合并处理。chart_mcp_tools列表的数据都是以generate_开头的工具名
    #     :return:
    #     """
    #     tools_map={}
    #     hit=False
    #     other_tools: List[Any] = []
    #     for tool in chart_mcp_tools:
    #
    #         #获取每个工具的后缀
    #         tool_name_suffix=name[len[tool.name]:]
    #         #_chart 获取以_chart结尾但是不只有_chart的工具
    #         if self.process_tool(tool,tools,__CHART_SUFFIX):
    #             hit =True
    #             continue
    #         hit = self.process_tool(tool, tools, __KEEP_SUFFIX)
    #         if not hit:
    #             other_tools.append(t)
    #
    #
    #     # 动态生成工具描述（紧凑速查表）
    #     tool_desc = self.__build_tool_desc(tools_map)
    #
    #     @tool
    #     async def create_visualization(type: str, confog: dict[str, Any]) -> str:
    #
    #         tool_temp = tools_map.get(type)
    #
    #         if not tool_temp:
    #             types = ",".join(sorted(tool_map.keys()))
    #             return (
    #                 f"Error: Unknown chart type '{chart_type}'. "
    #                 f"Available types: {types}")
    #         result = await chart_tool.ainvoke(chart_config)
    #
    #         # 注入动态生成的描述
    #         create_visualization.name = "create_visualization"
    #         create_visualization.desc = tool_desc
    #         return result
    #
    #
    #
    #
    # def __process_data(tool:Any,tools_map:Dict[str,Any],tool_suffixes:tuple[str])->bool:
    #     for tool_suffix in tool_suffixes:
    #         if tool_name_suffix.endswith(tool_suffix) and tool_name_suffix != tool_suffix:
    #             # 获取中间字符串作为类型名
    #             middle_name = tool_name_suffix[:-len(tool_suffix)]
    #             tools_map[middle_name] = tool
    #             return True
    #     return False
    #
    #
    # def __build_tool_desc(self,tools_map:Dict[str,Any])-> str:
    #     tool_list_str = ", ".join(sorted(tool_map.keys()))
    #     return (
    #             "Generate a data visualization and return the image URL.\n"
    #             "\n"
    #             "Use this tool to create charts, maps, diagrams, or mind maps for analysis reports.\n"
    #             f"Available chart_type values: {tool_list_str}\n"
    #             "\n"
    #             + _COMPACT_TABLE +
    #             "\n\n"
    #             "When unsure about the exact fields for chart_config, read "
    #             "`/skills/procurement/chart_params.md` first, then call this tool."
    #     )