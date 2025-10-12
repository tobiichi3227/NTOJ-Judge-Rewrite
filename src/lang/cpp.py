from dataclasses import dataclass

from lang.base import CompiledLang, reg_lang
from models import Compiler
from sandbox.sandbox import ChallengeBox, SandboxParams


@dataclass
class _Cpp17(CompiledLang):
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
            ],
            stderr=box.gen_filepath("stderr"),
            copy_out_cache_files=[executable_name],
            time_limit=10000,  # 10 sec
            memory_limit=512 << 20,  # 256 MB
            proc_limit=10,
            output_limit=64 << 20,  # 64 MB
            allow_proc=True,
            allow_mount_proc=False,
            # TODO: cpuset
            extra_env=["PATH=/usr/bin:/bin"],
        )
        for src, dst in copyin:
            param.add_copy_in_path(src, dst)
        res = box.run_sandbox([param])
        return res[0]

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
