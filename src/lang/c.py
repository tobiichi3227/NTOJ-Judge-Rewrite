from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler
from sandbox.sandbox import ChallengeBox, SandboxParams


@dataclass
class _C11(CompiledLang):
    compiler: str
    standard: str

    def compile(
        self,
        box: ChallengeBox,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        param = SandboxParams(
            exe_path=self.compiler,
            args=[
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
            stderr=box.gen_filepath("stderr"),
            copy_out_cache_files=[executable_name],
            time_limit=10000,  # 10 sec
            memory_limit=512 << 20,  # 512 MB
            proc_limit=10,
            output_limit=64 << 20,  # 64 MB
            allow_proc=True,
            allow_mount_proc=False,
            # TODO: cpuset
        )
        for src, dst in copyin:
            param.add_copy_in_path(src, dst, True)
        res = box.run_sandbox([param])
        return res[0]

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
