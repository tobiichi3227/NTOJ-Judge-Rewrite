from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler
from src.sandbox.sandbox import SandboxParams


@dataclass
class _Asm(CompiledLang):
    compiler: str

    def compile(
        self,
        box,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        param = SandboxParams(
            exe_path=self.compiler,
            args=[
                "-o",
                executable_name,
                *sources,
                *addition_args,
                "-lm",  # NOTE: Math Library
            ],
            stderr=box.gen_filepath("stderr"),
            copy_out_cache_files=[executable_name],
            time_limit=10000,  # 10 sec
            memory_limit=512 << 20,  # 512 MB
            proc_limit=10,
            output_limit=64 << 20,  # 64 MB
            allow_proc=True,
        )
        for src, dst in copyin:
            param.add_copy_in_path(src, dst)
        res = box.run_sandbox([param])
        return res[0]

reg_lang(
    Compiler.asm_with_libc,
    _Asm(
        name="asm",
        header_ext="",
        source_ext=".s",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
        compiler="/usr/bin/gcc",
    ),
)
reg_lang(
    Compiler.asm_with_libstdcpp,
    _Asm(
        name="asm",
        header_ext="",
        source_ext=".s",
        object_ext=".o",
        executable_ext="",
        allow_thread_count=1,
        compiler="/usr/bin/g++",
    ),
)
