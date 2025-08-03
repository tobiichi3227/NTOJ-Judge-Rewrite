import os
import executor_server
from dataclasses import dataclass

from lang.base import BaseLang, reg_lang
from models import Compiler

TOOLS_PATH = os.path.join(os.getcwd(), "tools")


@dataclass
class _Python(BaseLang):
    def compile(
        self,
        copyin: dict[str, dict],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        res = executor_server.exec(
            {
                "cmd": [
                    {
                        "args": [
                            "/usr/bin/bash",
                            "compile_python3.sh",
                            sources[0].removesuffix(self.source_ext),
                            executable_name,
                        ],
                        "env": ["PATH=/usr/bin:/bin"],
                        "files": [
                            {"content": ""},
                            {"content": ""},
                            {"name": "stderr", "max": 102400},
                        ],
                        "cpuLimit": 10000000000,  # 10 sec
                        "memoryLimit": 536870912,  # 512M (256 << 20)
                        "procLimit": 10,
                        "copyIn": {
                            "compile_python3.sh": {
                                "src": os.path.join(TOOLS_PATH, "compile_python3.sh")
                            },
                            **copyin,
                        },
                        "copyOut": ["stderr"],
                        "copyOutCached": [executable_name],
                        "copyOutMax": 64000000,
                    }
                ]
            }
        )
        return res

    def get_execute_command(
        self, executable_name, main=None, args: list[str] = None
    ) -> list[str]:
        if args is None:
            args = []
        command = ["/usr/bin/python3", executable_name]
        command.extend(args)
        return command


reg_lang(
    Compiler.python3,
    _Python(
        name="python",
        header_ext="",
        source_ext=".py",
        object_ext=".pyc",
        executable_ext=".pyz",
        allow_thread_count=1,
    ),
)
