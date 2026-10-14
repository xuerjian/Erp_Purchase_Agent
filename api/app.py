from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from api import chat, history, check_health
from contextmanager.webcontextmanager import lifespan

app = FastAPI(title="内部采购", version="1.0",lifespan=lifespan)

# CORS跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 注册路由
# ============================================================
# 对话相关接口
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
# 历史记录相关接口
app.include_router(history.router, prefix="/api", tags=["历史记录"])
# 历史记录相关接口
app.include_router(check_health.router, prefix="/api", tags=["服务健康检查"])

