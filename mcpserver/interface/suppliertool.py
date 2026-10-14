from fastmcp import FastMCP, Context
import json

# 分组名称
GROUP_NAME = "supplier"
def register_supplier_tool(mcp: FastMCP):
    """注册供应商分组的所有工具"""

    @mcp.tool(name=f"{GROUP_NAME}_query")
    async def query_suppliers(name: str, ctx: Context) -> list:
        """
        按名称模糊搜索供应商。

        Args:
            name: 供应商名称（模糊查询），必填
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        try:
            response = await http_client.get("/suppliers/search", params={"name": name})
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]
            return result.get("data", [])
        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']

    @mcp.tool(name=f"{GROUP_NAME}_page")
    async def supplier_page(
            current: int = 1,
            size: int = 10,
            name: str = None,
            status: int = None,
            credit_rating: str = None, ctx: Context=None
    ) -> str:
        """分页查询供应商列表。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            name: 供应商名称（可选，模糊匹配）
            status: 合作状态（可选）：1=合作中, 0=已停止
            credit_rating: 信用评级（可选）：A/B/C/D

        Returns:
            分页供应商数据JSON，包含 records, total, current, size, pages
        """
        params = {
            "current": current,
            "size": size,
            "name": name,
            "status": status,
            "creditRating": credit_rating,
        }
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = await http_client.get("/api/suppliers/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(name=f"{GROUP_NAME}_get")
    async def supplier_get(id: int,ctx: Context) -> str:
        """获取单个供应商的详细信息。

        Args:
            id: 供应商ID

        Returns:
            供应商详细信息JSON，包含 supplierCode, name, contactPerson, phone, email, address, creditRating, status
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = http_client.get(f"/api/suppliers/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(name=f"{GROUP_NAME}_create")
    async def supplier_create(
            supplier_code: str,
            name: str,
            contact_person: str = None,
            phone: str = None,
            email: str = None,
            address: str = None,
            credit_rating: str = None,
            status: int = 1, ctx: Context=None
    ) -> str:
        """创建新供应商。

        Args:
            supplier_code: 供应商编码（必填）
            name: 供应商名称（必填）
            contact_person: 联系人
            phone: 联系电话
            email: 邮箱
            address: 地址
            credit_rating: 信用评级 A/B/C/D
            status: 合作状态 1=合作中 0=停止

        Returns:
            创建结果JSON
        """
        data = {
            "supplierCode": supplier_code,
            "name": name,
            "contactPerson": contact_person,
            "phone": phone,
            "email": email,
            "address": address,
            "creditRating": credit_rating,
            "status": status,
        }
        # 移除 None 值
        data = {k: v for k, v in data.items() if v is not None}
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = await http_client.post("/api/suppliers/create", json_data=data)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(name=f"{GROUP_NAME}_update_status")
    async def supplier_update_status(id: int, status: int, ctx: Context) -> str:
        """更新供应商合作状态。

        Args:
            id: 供应商ID
            status: 新状态 1=合作中 0=已停止

        Returns:
            操作结果JSON
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = await http_client.patch(
            f"/api/suppliers/update-status/{id}", params={"status": status}
        )
        return json.dumps(result, ensure_ascii=False, indent=2)