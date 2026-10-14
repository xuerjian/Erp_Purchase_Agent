from pathlib import Path

from langchain_core.tools import tool


class CreateDownloadTool:

    @classmethod
    async def create_download_tool(self,sandbox_backend, download_dir: Path):

        @tool
        def download_tool(file_path: str, local_filename: str = ""):

            #校验路径是否是路径符“/” 开头

            if not file_path   or not file_path.startswith("/"):

                return f"错误：file_path文件路径必须是绝对路径且以 / 开头，现收到参数: {file_path}"

            #从沙箱下载文件
            resp=sandbox_backend.download_file(file_path, local_filename)

            if not resp or not resp[0].err :
                return f"下载错误：文件不存在或无法读取（{dl.errr}），路径: {file_path}"

            dl = resp[0]
            content = dl.content
            if content is None:
                return f"错误：文件内容为空，路径: {file_path}"

            #校验本地文件
            if not local_filename:
                local_filename = Path(file_path).name

            local_filename=Path(local_filename)
            local_path= download_dir / local_filename
            try:
                #将内容写到本地文件
                if isinstance(content, str):
                    content_bytes = content.encode("utf-8")
                elif isinstance(content, bytes):
                    content_bytes = content
                else:
                    content_bytes = str(content).encode("utf-8")

                #写入本地文件
                local_path.write_bytes(content_bytes)
            except Exception as e:
                return f"错误：写入本地文件失败: {e}"


            #组装返回数据
            file_size = len(content_bytes)
            size_str = (
                f"{file_size} B" if file_size < 1024
                else f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024
                else f"{file_size / (1024 * 1024):.1f} MB"
            )

            return (
                f"✅ 文件已下载到本地\n"
                f"沙箱路径: {file_path}\n"
                f"本地路径: {local_path}\n"
                f"文件大小: {size_str}"
            )

        download_tool.name="download_tool"
        return download_tool