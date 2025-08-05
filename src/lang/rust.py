import executor_server
from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler


@dataclass
class _Rust(CompiledLang):
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
                            "/usr/bin/rustc",
                            "-O",
                            "-o",
                            executable_name,
                            sources[0],
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


reg_lang(
    Compiler.rust,
    _Rust(
        name="rust",
        header_ext="",
        source_ext=".rs",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
    ),
)
