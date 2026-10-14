from api.app import app

# API 服务标题
API_TITLE = "DeepAgent Chat API"
# API 版本
API_VERSION = "1.0.0"


@app.get("/health", tags=["系统"])
async def health_check():
    """
    健康检查接口

    用于检查服务是否正常运行
    """
    return {
        "status": "healthy",
        "service": API_TITLE,
        "version": API_VERSION
    }