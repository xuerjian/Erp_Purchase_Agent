from pathlib import Path
from typing import List,Dict
from langchain_classic.output_parsers import yaml

_REL_CONFIG_PATH=Path(__file__).parent/'configs'

_REQUIRED_FIELDS = ["name", "description", "system_prompt", "tools"]

_OPTION_FIELDS=["model","skills","interrupt_on"]


class SubAgentCreator:

    def __get_sub_agent_config(self)-> List[Dict]:

        #判断配置目录是否存在
        if not _REL_CONFIG_PATH.exists():
            return []

        configs:List[Dict]=[]
        for yaml_file in sorted(_REL_CONFIG_PATH.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    yaml_content=yaml.safe_load(f)

                # 获取yaml文件中没有，但是又是yaml文件中必须要求存在的
                missing_fields = [f for f in _REQUIRED_FIELDS if f not in yaml_content or yaml_content[f] is None]

                if len(missing_fields)==0:
                    continue

                #其中tools必须是非空列表
                if "tools" not in missing_fields:
                    tools_list=yaml_content['tools']
                    if not tools_list or not isinstance(tools_list, list) or len(tools_list)==0:
                        continue


                ## system_prompt 不能为空字符串
                if 'system_prompt' not in missing_fields:
                    system_prompt_content=yaml_content['system_prompt']
                    if not system_prompt_content or not isinstance(system_prompt_content,str) or not system_prompt_content.strip():
                        continue

                configs.append(yaml_content)
            except FileNotFoundError as e:
                print(f"[ERROR] 读取文件失败: {yaml_file} — {e}")
                continue


        return configs

    def get_sub_agents(self,tools: List,
    sub_middleware: Dict[str, List] | None = None,)-> List[Dict]:

        #获取配置信息
        configs=self.__get_sub_agent_config()

        tool_map:Dict[str,object]={}

        for tool in tools:
            tool_name=getattr(tool,'name',None)
            if tool_name :
                tool_map[tool_name]=tool

        subagents=list[Dict]=[]


        for config in configs:

            #获取yaml文件中tools标签的数据
            tool_names=config.get("tools",[])

            seen = set()
            deduplicate_tools = []

            for sub_tool_name in tool_names:

                for tool_name,tool in tool_map.items():

                    if sub_tool_name in tool_name:#匹配
                        name=getattr(tool,"name",id(tool))
                        if name not in seen:
                            seen.add(name)
                            deduplicate_tools.append(tool)


            subagent:Dict[str,object]={
                "name": config["name"],
                "description": config["description"].replace("\n", " ").strip(),
                "system_prompt": config["system_prompt"],
                "tools": deduplicate_tools,
            }

            #复制可选字段的值
            for option_field in _OPTION_FIELDS:
                subagent[option_field] = config[option_field]


            ##处理中间件
            subagent_config_middleware = list(config.get("middleware", []))

            if config.get("name") in sub_middleware:
                subagent_config_middleware.append(sub_middleware[config.get("name")])

            if subagent_config_middleware:
                subagent["middleware"]=subagent_config_middleware

            subagents.append(subagent)

        return subagents