import os
from dataclasses import dataclass

from lang.base import BaseLang, reg_lang
from models import Compiler
from src.sandbox.sandbox import SandboxParams

TOOLS_PATH = os.path.join(os.getcwd(), "tools")


@dataclass
class _Java(BaseLang):
    def compile(
        self,
        box,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        param = SandboxParams(
            exe_path="/usr/bin/bash",
            args=[
                "compile_java.sh",
                executable_name,
            ],
            stderr=box.gen_filepath("stderr"),
            copy_out_cache_files=[executable_name],
            time_limit=10000,  # 10 sec
            memory_limit=512 << 20,  # 512 MB
            proc_limit=10,
            output_limit=64 << 20,  # 64 MB
            allow_proc=True,
            allow_mount_proc=True
        )
        for src, dst in copyin:
            param.add_copy_in_path(src, dst)
        param.add_copy_in_path(os.path.join(TOOLS_PATH, "compile_java.sh"), "compile_java.sh")
        res = box.run_sandbox([param])
        return res[0]

    def get_execute_command(
        self, executable_name: str, main=None, args: list[str] = None
    ) -> tuple[str, list[str]]:
        if args is None:
            args = []
        command = ["-cp", executable_name, main] + args
        return "/usr/bin/java", command


reg_lang(
    Compiler.java,
    _Java(
        name="java",
        header_ext="",
        source_ext=".java",
        object_ext=".javac",
        executable_ext=".jar",
        allow_thread_count=16,
    ),
)
