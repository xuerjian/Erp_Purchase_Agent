from fastmcp import FastMCP
# 导入各个分组的注册函数
from mcpserver.interface.suppliertool import register_supplier_tool
from mcpserver.interface.parttool import register_part_tool
from mcpserver.interface.ordertool import register_order_tool
from mcpserver.interface.inventorytool import register_inventory_tool
from mcpserver.serverconfig import MCP_HOST, MCP_PORT, MCP_PATH
from mcpserver.httpbase import mcp_lifespan


mcp=FastMCP(name="",instructions="调用Java后端具体业务数据接口"
            ,version="1.0.0",
            language="Java",
            lifespan=mcp_lifespan
            )

# 注册所有分组
register_supplier_tool(mcp)
register_part_tool(mcp)
register_order_tool(mcp)
register_inventory_tool(mcp)


def main():

    # 启动 Streamable HTTP 服务
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH
    )
    # 注意：run() 会阻塞，且 lifespan 会在服务器关闭时自动清理资源


if __name__ == "__main__":
    main()