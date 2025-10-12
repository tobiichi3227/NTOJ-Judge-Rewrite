import os
from dataclasses import dataclass

from lang.base import BaseLang, reg_lang
from models import Compiler
from sandbox.sandbox import ChallengeBox, SandboxParams

TOOLS_PATH = os.path.join(os.getcwd(), "tools")


@dataclass
class _Python(BaseLang):
    def compile(
        self,
        box: ChallengeBox,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        param = SandboxParams(
            exe_path="/usr/bin/bash",
            args=[
                "compile_python3.sh",
                sources[0].removesuffix(self.source_ext),
                executable_name,
            ],
            stderr=box.gen_filepath("stderr"),
            copy_out_cache_files=[executable_name],
            time_limit=10000,  # 10 sec
            memory_limit=512 << 20,  # 512 MB
            proc_limit=10,
            output_limit=64 << 20,  # 64 MB
            allow_proc=True,
            allow_mount_proc=False
        )
        for src, dst in copyin:
            param.add_copy_in_path(src, dst)
        param.add_copy_in_path(os.path.join(TOOLS_PATH, "compile_python3.sh"), "compile_python3.sh")
        res = box.run_sandbox([param])
        return res[0]

    def get_execute_command(
        self, executable_name: str, main=None, args: list[str] = None
    ) -> tuple[str, list[str]] :
        if args is None:
            args = []
        command = [executable_name] + args
        return "/usr/bin/python3", command


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
