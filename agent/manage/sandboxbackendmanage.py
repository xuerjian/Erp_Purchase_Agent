import logging
from pathlib import Path

from deepagents.backends.protocol import FileDownloadResponse, FileUploadResponse, ExecuteResponse
from opensandbox import SandboxSync
from deepagents.backends.sandbox import BaseSandbox
from numbers import Number

import os

from opensandbox.models import WriteEntry

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


class SandboxManage(BaseSandbox):

    _sandbox:SandboxSync

    _default_time_out=60 * 60

    _sync_polling_interval=0.1

    __new_created=False


    # 沙箱中非交互式 shell 不会加载 /etc/profile，需要手动注入环境变量
    SANDBOX_PATH_ENV_VARIABLE = (
        "/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin:"
        "/opt/go/1.25.5/bin:"
        "/opt/node/v22.2.0/bin:"
        "/usr/lib/jvm/java-21-openjdk-amd64/bin:"
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )

    def __init__(self,sandbox:SandboxSync,new_created:bool,timeout: int = 60 * 60,
            sync_polling_interval: Number  = 0.1, ):
        self._sandbox = sandbox
        self._default_time_out = timeout
        self._sync_polling_interval = sync_polling_interval
        self.__new_created=new_created

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:

        #执行sell 指令

        scrypt_text=f'export PATH="{self.SANDBOX_PATH_ENV_VARIABLE}:$PATH" '
        try:
            if self.__new_created:
                scrypt_text+="&&{command}"
            #执行脚本
            result=self._sandbox.commands.run(scrypt_text)
            logger.debug(f"Execute command环境变量初始化已完成: {command}")
            #脚本执行结果，输出日志
            stdout = ""
            stderr = ""

            if result.logs.stdout:
                stdout = "\n".join([message.text for message in result.logs.stdout])
                logger.debug(f"命令标准输出长度：{len(stdout)} 字符")

            if result.logs.stderr:
                stderr = "\n".join([message.text for message in result.logs.stderr])
                logger.error(f"命令标准错误长度：{len(stderr)} 字符")
                # 合并输出
                if stderr and stderr.strip():
                    stdout += f"\n<stderr>{stderr.strip()}</stderr>"

            return ExecuteResponse(
                output=stdout,
                exit_code=result.exit_code or 0,
                truncated=False,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"执行命令时发生错误：{error_msg}", exc_info=True)
            return ExecuteResponse(
                output="命令执行异常",
                exit_code=500,
                truncated=False,
            )

    @property
    def id(self) -> str:
        return self._sandbox.id

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        result:list[FileUploadResponse]=None;
        if files and len(files)>0:
            result=[]
            send_files:list[WriteEntry]=None;
            for remote_sandbox_path,content in files:
                if(remote_sandbox_path.startswith("/")):
                    if(send_files is None):
                        send_files=[]
                    if(isinstance(content, bytes)):
                        try:
                            content_decode=content.decode("utf-8")
                            #对文件追加权限
                            send_files.append(WriteEntry(path=remote_sandbox_path, data=content_decode, mode=0o644))
                        except Exception as e:
                            logger.error(f"上传skills文件数据解码异常{e}")
                    else:
                        send_files.append(WriteEntry(path=remote_sandbox_path, data=content, mode=0o644))
                    result.append(FileUploadResponse(path=remote_sandbox_path, error=None))
                else:
                    result.append(FileUploadResponse(path=remote_sandbox_path, error="invalid_path"))

            if send_files is None and len(send_files)>0:
                self._sandbox.files.write_files(send_files)

        return result


    #初始化文件
    def init_files(self):

        #将本地文件上传到远程sandbox
        files=[]
        local_skills_path=Path(os.getenv("BASE_DIR")+str(os.getenv("LOCAL_SKILLS_PATH")))

        if local_skills_path.exists():
            for skill_dir in local_skills_path.iterdir():
                if skill_dir.is_dir():
                    for local_dir_file in skill_dir.rglob("*"):
                        if(local_dir_file.is_file()):
                            #根据不同系统，转换成相对应的路径符号
                            file_relative_path=local_dir_file.relative_to(local_skills_path).as_posix()
                            #拼接成远程沙箱路径
                            remote_sandbox_path=f"{os.getenv("SANDBOX_SKILLS_PATH")}/{file_relative_path}"
                            files.append((local_dir_file, remote_sandbox_path))


        if files.__len__() > 0:
            send_files=None;
            for local_dir_file, remote_sandbox_path in files:
                local_content=None;
                if local_dir_file.exists():
                    #验证沙箱内文件是否存在,如果存在对比本地文件和远程文件内容是否一致，不一致更新远程
                    valid=self.execute(f"test -e {remote_sandbox_path} ", timeout=self._default_time_out)
                    if valid.exit_code == 0:
                        #证明文件存在
                        download_result=self.download_files(remote_sandbox_path)
                        if download_result and download_result[0]:
                            result=download_result[0]
                            if(result.content and not result.error):
                                if(isinstance(result.content, str)):
                                    remote_content=result.content.encode("utf-8")
                                    local_content=local_dir_file.read_bytes()
                                    #判断文件内容是否一致
                                    if(local_content==remote_content):
                                        continue

                if send_files is None:
                    send_files=[]
                if local_content is None:
                    local_content = local_dir_file.read_bytes()
                send_files.append({remote_sandbox_path,local_content})

            #上传skill文件到远程沙盒
            if send_files.__len__()>0:
                self.upload_files(files=send_files)



    def download(self,file_paths:list[str]|None):
        if not file_paths and len(file_paths)>0:
            return
        
        responses: list[FileDownloadResponse] = []

        for file_path,content in file_paths:
            if self.download(file_path,content):
                continue

        return responses

    def download(self,file_path:str|None,content: bytes,responses: list[FileDownloadResponse])->bool:

        if not file_path.startswith("/"):
            responses.append(FileDownloadResponse(path=file_path,content="文件路径异常，路径不是以系统路径符开始的", error="invalid_path"))
            return True

        content = self._sandbox.files.read_file(file_path)

        #转换为bytes

        content_bytes=content.encode(encoding="utf-8")  if isinstance(content, str) else content
        responses.append(FileDownloadResponse(path=file_path,content=content_bytes, error="invalid_path"))
        return False

        # if(isinstance(content, bytes)):
        #     try:
        #         content_str=content.decode("utf-8")
        #     except:
        #         content_str = content.decode("gbk")
        # else:
        #     content_str=str(content)
        #
        # upload_entries.append(WriteEntry(path=file_path, data=content_str, mode=0o644))
        #
        # responses.append(FileUploadResponse(path=file_path, error=None))

