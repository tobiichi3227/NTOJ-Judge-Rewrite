from dataclasses import dataclass
import os

from models import Compiler


@dataclass
class BaseLang:
    name: str
    header_ext: str
    source_ext: str
    object_ext: str
    executable_ext: str
    allow_thread_count: int

    def compile(
        self,
        copyin: dict[str, dict],
        sources: list[str],
        addition_args: list[str],
        executable_name: str,
    ) -> dict:
        return {}

    def get_execute_command(
        self, executable_name, main=None, args: list[str] = None
    ) -> list[str]:
        return []


class CompiledLang(BaseLang):
    def get_execute_command(self, executable_name, main=None, args: list[str] = None):
        if args is None:
            args = []

        command = [os.path.join(".", executable_name)]
        command.extend(args)

        return command


langs: dict[Compiler, BaseLang] = {}


def reg_lang(compiler: Compiler, lang: BaseLang):
    langs[compiler] = lang


def init_langs():
    from lang import c, cpp, python3, rust, java, asm
