import executor_server
from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler


@dataclass
class _Cpp17(CompiledLang):
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

    def execute(self):
        pass


reg_lang(
    Compiler.gcc_cpp_17,
    _Cpp17(
        name="cpp",
        header_ext=".h",
        source_ext=".cpp",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
        compiler="/usr/bin/g++",
        standard="-std=gnu++17",
    ),
)
reg_lang(
    Compiler.clang_cpp_17,
    _Cpp17(
        name="cpp",
        header_ext=".h",
        source_ext=".cpp",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
        compiler="/usr/bin/clang++",
        standard="-std=c++17",
    ),
)
