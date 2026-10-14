from contextlib import asynccontextmanager

from fastapi import FastAPI
import os

from agentcreator import AgentCreator
from config.config import load_env

@asynccontextmanager
async def lifespan(app: FastAPI):

    # 服务启动前执行
    env_type = os.getenv("ENV_TYPE")  # 由启动脚本传入 dev / test / prod
    load_env(env_type)

    #os.getenv()#获取配置信息

    # 初始化 Agent
    await AgentCreator().instance.initialize()

    yield

    print("===============服务已关闭====================")
