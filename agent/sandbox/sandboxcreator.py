from datetime import timedelta

from opensandbox import SandboxSync
from agent.manage.sandboxbackendmanage import SandboxManage

def create_sandbox(config,image=None,sandbox_id=None,**kwargs)-> SandboxManage:
    sandbox =None
    new_created=False
    if bool(sandbox_id)==True:
        try:
            sandbox=SandboxSync.connect(sandbox_id=sandbox_id,connection_config=config)
        except:
            sandbox_id=None #沙箱连接异常时重置sandbox_id

    if not sandbox_id:
        new_created=True
        sandbox = SandboxSync.create(image=image,
                                     #entrypoint=, #镜像地址
                                     timeout=timedelta(minutes=30),
                                     env={"PYTHON_VERSION": "3.12"},
                                     resource={"cpu": "4", "memory": "16Gi"},
                                     connection_config=config)

        
    return SandboxManage(sandbox=sandbox,new_created=new_created)