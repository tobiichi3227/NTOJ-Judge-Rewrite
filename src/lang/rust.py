from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler
from sandbox.sandbox import SandboxParams


@dataclass
class _Rust(CompiledLang):
    def compile(
        self,
        box,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        param = SandboxParams(
            exe_path="/usr/bin/rustc",
            args=[
                "-O",
                "-o",
                executable_name,
                sources[0],
                *addition_args,
            ],
            stderr=box.gen_filepath("stderr"),
            copy_out_cache_files=[executable_name],
            time_limit=10000,  # 10 sec
            memory_limit=1024 << 20,  # 1024 MB
            proc_limit=10,
            output_limit=64 << 20,  # 64 MB
            allow_proc=True,
            allow_mount_proc=False
        )
        for src, dst in copyin:
            param.add_copy_in_path(src, dst, True)
        res = box.run_sandbox([param])
        return res[0]


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
