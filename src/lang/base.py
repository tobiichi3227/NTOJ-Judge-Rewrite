import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from models import Compiler
from sandbox.sandbox import ChallengeBox, SandboxResult


@dataclass
class BaseLang(ABC):
    name: str
    header_ext: str
    source_ext: str
    object_ext: str
    executable_ext: str
    allow_thread_count: int

    @abstractmethod
    def compile(
        self,
        box: ChallengeBox,
        copyin: list[tuple[str, str]],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ) -> SandboxResult:
        return NotImplemented

    @abstractmethod
    def get_execute_command(
        self, executable_name: str, main=None, args: list[str] = None
    ) -> tuple[str, list[str]]:
        return NotImplemented


class CompiledLang(BaseLang):
    def get_execute_command(self, executable_name: str, main=None, args: list[str] = None):
        if args is None:
            args = []

        return os.path.join(".", executable_name), args


langs: dict[Compiler, BaseLang] = {}


def reg_lang(compiler: Compiler, lang: BaseLang):
    langs[compiler] = lang


def init_langs():
    from lang import c, cpp, python3, rust, java, asm