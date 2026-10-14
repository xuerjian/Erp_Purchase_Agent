#技能管理工具
from datetime import datetime,timezone

from agent.agentconfig import redis_store

from langchain_core.tools import tool

from agent.agentconfig import AGENT_SCOPE_MAP

class SkillManageTool:

    @classmethod
    async def assign_skills(self,sandbox_backend, skills_namespace):


        @tool
        async def assign_skills_tool(agent_name:str, skill_name:str)->str|None:
            #给子agent安装技能(后续可以扩展改进针对不同的用户，安装不同技能)


            if agent_name not in AGENT_SCOPE_MAP:
                return f"错误：未知 Agent '{agent_name}'。可用: {", ".join(AGENT_SCOPE_MAP.keys())}"


            #获取当前智能体所在的域范围
            scope=AGENT_SCOPE_MAP[agent_name]
            #技能文件原始路径
            source_path=f"/skills/manage/{skill_name}"
            #目标文件
            target_path=f"/skills/{scope}/{skill_name}"

            #验证源技能是否存在
            valid = sandbox_backend.execute(f"test -f {source_path}/SKILL.md")
            if not valid or valid.exit_code != 0:
                return (
                    f"错误：技能 '{skill_name}' 在 {source_path}/ 下不存在。\n"
                    f"请先完成技能下载/创建和测试。"
                )

            #判断agent是否是主agent
            if "manage" == agent_name:
                seg_result="主 Agent 技能已就位，无需复制"
            else:
                #创建目录路径，并复制文件到该目录下
                result = sandbox_backend.execute(
                    f"mkdir -p {target_path} && cp -r {source_path}/* {target_path}/"
                )

                #判断是否复制成功
                if not result or result.exit_code != 0:
                    return f"复制技能{skill_name}失败：\n{result.output}"

                #成功后，查询目标scope的技能列表。查询后不管查询是否成功将结果输出
                ls_result = sandbox_backend.execute(f"ls {target_path}/")

                seg_result = (
                    f"✅ 已复制到沙箱 {target_path}/\n"
                    f"文件:\n{ls_result.output.strip()}"
                )


            #将技能文件持久化到store--->>RedisStore
            skill_persist=await self.__persist_skill_to_store(sandbox_backend,skills_namespace,scope,skill_name)

            # 清理/skills/manage/目录下的 *.zip、*.tar.gz、*.tar、*.tgz等后缀的skill技能压缩包
            remove_response = self.__remove_all(sandbox_backend)

            return (
                f"✅ 技能 '{skill_name}' 已分配给 Agent '{agent_name}'（scope: {scope}）\n"
                f"{seg_result}\n"
                f"{skill_persist}\n"
                f"{remove_response}"
            )

        assign_skills_tool.name=assign_skills_tool
        return assign_skills_tool

    async def __persist_skill_to_store(self,sandbox_backend,  namespace:str, scope: str, skill_name: str)->str:

        source_dir = f"/skills/manage/{skill_name}"


        # 查找目录下的文件
        find_result = sandbox_backend.execute(f"find {source_dir} -type f")

        if find_result.exit_code != 0:
            return f"⚠️ 持久化失败：无法列出 {source_dir}/ 下的文件"


        #获取目标文件
        file_paths = [p.strip() for p in find_result.output.strip().split("\n")]

        if not file_paths:
            return "持久化跳过：源目录为空"


        count=0
        now = datetime.now(timezone.utc).isoformat()
        for file_path in file_paths:
            #截取路径，获取持久化存储技能
            key_temp=file_path[len("/skills/manage/"):]
            store_key=f'/{scope}/{key_temp}'


            try:
                ##下载文件
                download_responses = sandbox_backend.download(file_path)
                if not download_responses and download_responses[0].err:
                    continue
                content_str= str(download_responses[0].content)

                await redis_store.amset(namespace, store_key, {
                    "content": [content_str],
                    "created_at": now,
                    "modified_at": now,
                })

                count+=1
            except:
                continue

        return f"持久化完成：{count} 个文件 → StoreBackend /persisted-skills/{scope}/{skill_name}/"


    def __remove_all(self,sandbox_backend):
        """
        清理/skill/manage 目录下下载的skill技能压缩包
        :param sandbox_backend:
        :return:
        """

        command_params='*.tar *.tar.bz2 *.zip *.tgz *.tar.gz *.tar.xz'

        command=f"cd /skills/main/ && rm -f {command_params} 2>/dev/null; ls {command_params} 2>/dev/null || echo 'none'"

        result=sandbox_backend.execute(command)

        output = result.output.strip()
        if output == "none" or not output:
            return "压缩技能包已清理"
        else:
            return f"压缩技能包清理（残留: {output}）"