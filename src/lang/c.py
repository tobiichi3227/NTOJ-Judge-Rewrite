import executor_server
from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler


@dataclass
class _C11(CompiledLang):
    compiler: str
    standard: str

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
                            self.compiler,
                            self.standard,
                            "-O2",
                            "-pipe",
                            "-static",
                            "-s",
                            "-o",
                            executable_name,
                            *sources,
                            *addition_args,
                            "-lm",  # NOTE: Math Library
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
                        "copyIn": copyin,
                        "copyOut": ["stderr"],
                        "copyOutCached": [executable_name],
                        "copyOutMax": 64000000,
                    }
                ]
            }
        )
        return res

    def execute_command(self):
        pass


reg_lang(
    Compiler.gcc_c_11,
    _C11(
        name="c",
        header_ext=".h",
        source_ext=".c",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
        compiler="/usr/bin/gcc",
        standard="-std=gnu11",
    ),
)
reg_lang(
    Compiler.clang_c_11,
    _C11(
        name="c",
        header_ext=".h",
        source_ext=".c",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
        compiler="/usr/bin/clang",
        standard="-std=c11",
    ),
)
