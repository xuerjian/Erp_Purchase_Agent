#配置信息
import os
from dotenv import load_dotenv
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
#项目的根目录加载到内存中
os.environ["BASE_DIR"] = str(BASE_DIR)


def load_env(env_name: str = None):
    """
    env_name: test / prod / dev
    加载对应的环境变量文件
    """
    env_file_map = {
        "dev": BASE_DIR / ".env",
        "test": BASE_DIR / ".env.test",
        "prod": BASE_DIR / ".env.prod",
    }

    # 如果传入环境名称，加载指定env文件
    if env_name and env_name in env_file_map:
        env_path = env_file_map[env_name]
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            print(f"已加载环境配置: {env_path.name}")
        else:
            raise FileNotFoundError(f"环境文件不存在：{env_path}")
    else:
        # 默认加载 .env（本地开发）
        load_dotenv()

# ========== 读取配置，做成全局配置对象 ==========
# class Settings:
#     ENV: str = os.getenv("ENV", "dev")
#     API_BASE_URL: str = os.getenv("API_BASE_URL")
#     REDIS_URL: str = os.getenv("REDIS_URL")
#     MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8090"))
#     LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
#     LLM_API_KEY: str = os.getenv("LLM_API_KEY")
#
# settings = Settings()