
import os
from typing import List, Any, Dict

#mcp客户端
class CreateVisualTool:


    __CHART_SUFFIX = ("_chart",)

    __KEEP_SUFFIX = ("_map", "_diagram", "_graph")

    __TABLE_TEMPLATE = """
                        ## Chart Type Quick Reference
                        
                        **通用可选参数（几乎所有图表）:** `width`(默认600), `height`(默认400), `title`, `theme`("default"|"academy"|"dark"), `style`({backgroundColor, palette, texture})
                        
                        ### category-value 模式
                        | chart_type | data: [{...}] | 特有可选参数 |
                        |-----------|------|---------|
                        | bar | `{category, value}` | group(bool), stack(bool) |
                        | column | `{category, value}` | group(bool), stack(bool) |
                        | pie | `{category, value}` | innerRadius(0-1, 环形图) |
                        | funnel | `{category, value}` | — |
                        | treemap | `{name, value, children?}` | — |
                        | word_cloud | `{text, value}` | — |
                        
                        ### time-value 模式
                        | chart_type | data: [{...}] | 特有可选参数 |
                        |-----------|------|---------|
                        | line | `{time, value, group?}` | style.lineWidth |
                        | area | `{time, value, group?}` | stack(bool) |
                        
                        ### 分布/统计模式
                        | chart_type | data: [{...}] | 特有可选参数 |
                        |-----------|------|---------|
                        | boxplot | `{category, value, group?}` | style.startAtZero |
                        | violin | `{category, value, group?}` | style.startAtZero |
                        | histogram | `[number, ...]` (纯数字数组) | binNumber(int) |
                        | scatter | `{x, y, group?}` | — |
                        
                        ### 多维度/流向/集合
                        | chart_type | data: [{...}] | 特有可选参数 |
                        |-----------|------|---------|
                        | radar | `{name, value, group?}` | style.lineWidth |
                        | sankey | `{source, target, value}` | nodeAlign("left"&#124;"right"&#124;"center"&#124;"justify") |
                        | venn | `{value, sets: [str], label?}` | — |
                        | waterfall | `{category, value?, isIntermediateTotal?, isTotal?}` | style.palette({positiveColor, negativeColor, totalColor}) |
                        | dual_axes | 见下方说明 | — |
                        
                        ### 特殊图表（非 data 驱动或特殊结构）
                        | chart_type | 核心参数 | 说明 |
                        |-----------|---------|------|
                        | liquid | **`percent`**(0-1, 必填) | 不是 data! shape: "circle"\|"rect"\|"pin"\|"triangle" |
                        | organization | `data: {name, description?, children: [{name, description?, children: [...]}]}` | 层级树, orient: "vertical"\|"horizontal" |
                        | mind_map | `data: {name, children: [{name, children: [...]}]}` | 层级树, 最大深度3 |
                        | fishbone_diagram | `data: {name, children: [{name, children: [...]}]}` | 层级树, 最大深度3 |
                        | flow_diagram | `data: {nodes: [{name}], edges: [{source, target, name?}]}` | 节点+边 |
                        | network_graph | `data: {nodes: [{name}], edges: [{source, target, name?}]}` | 节点+边 |
                        
                        ### dual_axes 特殊格式
                        ```
                        chart_config = {
                          "categories": ["2023", "2024", "2025"],
                          "series": [
                            {"type": "column", "data": [91.9, 99.1, 101.6], "axisYTitle": "销售额"},
                            {"type": "line", "data": [0.055, 0.06, 0.062], "axisYTitle": "利润率"}
                          ]
                        }
                        // 注意: line 的 data 建议 < 1 (表示比率)
                        ```
                        ### 地图
                        | chart_type | 核心参数 | 说明 |
                        |-----------|---------|------|
                        | district_map | **`title`**(必填) + `data: {name, dataType?, dataLabel?, dataValue?, dataValueUnit?, subdistricts?, showAllSubdistricts?}` | 中国行政区划, 见参考文件 |
                        | pin_map | **`title`**(必填) + `data: [str, ...]` | POI 名称数组, 可选 markerPopup |
                        | path_map | **`title`**(必填) + `data: [{data: [str, ...]}]` | 路线数组, 每组是一条路线 |
                        
                        > **不确定 chart_config 的具体字段和格式时，先 `read_file("/skills/purchase/chart_params.md")` 查看完整参数说明和示例。**
                        """.strip()


    async def handle_tools(self,chart_mcp_tools: list):
        """
        :对工具进行筛选合并处理。chart_mcp_tools列表的数据都是以generate_开头的工具名
        :return:
        """
        tools_map={}
        hit=False
        other_tools: List[Any] = []
        for tool in chart_mcp_tools:

            #获取每个工具的后缀
            tool_name_suffix= os.name[len[tool.name]:]
            #_chart 获取以_chart结尾但是不只有_chart的工具
            if self.process_tool(tool,tools_map,self.__CHART_SUFFIX):
                hit =True
                continue
            hit = self.process_tool(tool, tools_map, self.__KEEP_SUFFIX)
            if not hit:
                other_tools.append(tool)


        # 动态生成工具描述（紧凑速查表）
        tool_desc = self.__build_tool_desc(tools_map)

        from langchain_core.tools import tool


        @tool
        async def create_visual_tool(type: str, confog: dict[str, Any]) -> str:

            tool_temp = tools_map.get(type)

            if not tool_temp:
                types = ",".join(sorted(tool_temp.keys()))
                return (
                    f"Error: Unknown chart type '{type}'. "
                    f"Available types: {types}")
            result = await tool_temp.ainvoke(confog)
            return result


        # 注入动态生成的描述
        create_visual_tool.name = "create_visual_tool"
        create_visual_tool.desc = tool_desc
        return create_visual_tool, other_tools




    def __process_data(tool:Any,tool_name_suffix:str,tools_map:Dict[str,Any],tool_suffixes:tuple[str])->bool:
        for tool_suffix in tool_suffixes:
            if tool_name_suffix.endswith(tool_suffix) and tool_name_suffix != tool_suffix:
                # 获取中间字符串作为类型名
                middle_name = tool_name_suffix[:-len(tool_suffix)]
                tools_map[middle_name] = tool
                return True
        return False


    def __build_tool_desc(self,tools_map:Dict[str,Any])-> str:
        tool_list_str = ", ".join(sorted(tools_map.keys()))
        return (
                "Generate a data visualization and return the image URL.\n"
                "\n"
                "Use this tool to create charts, maps, diagrams, or mind maps for analysis reports.\n"
                f"Available chart_type values: {tool_list_str}\n"
                "\n"
                + self.__TABLE_TEMPLATE +
                "\n\n"
                "When unsure about the exact fields for chart_config, read "
                "`/skills/procurement/chart_params.md` first, then call this tool."
        )