from dataclasses import dataclass

from lang.base import BaseLang, reg_lang
from models import Compiler
from sandbox.sandbox import ChallengeBox

@dataclass
class _Text(BaseLang):
    def compile(
        self,
        box: ChallengeBox,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ):
        return NotImplemented

    def get_execute_command(
        self, executable_name: str, main=None, args: list[str] = None
    ) -> tuple[str, list[str]] :
        if args is None:
            args = []
        command = [executable_name] + args
        return "/usr/bin/cat", command

    def need_compile(self) -> bool:
        return False


reg_lang(
    Compiler.text,
    _Text(
        name="text",
        header_ext="",
        source_ext=".txt",
        object_ext="",
        executable_ext=".txt",
        allow_thread_count=1,
    ),
)
