from dataclasses import dataclass
import os
import glob

from models import CompilationTarget, Challenge, SandboxStatus, Status, MessageType, Compiler
from problem.mixins import UserProgramMixin, CheckerMixin
from lang.base import langs
from sandbox.sandbox import SandboxResult

@dataclass(slots=True)
class UserProgramCompilationTarget(CompilationTarget):
    context: 'UserProgramMixin'

    def can_compile(self, chal: 'Challenge') -> bool:
        if self.context.has_grader:
            lang = langs[self.context.userprog_compiler]
            grader_folder_path = os.path.join(chal.res_path, "grader", lang.name)
            if not os.path.exists(grader_folder_path):
                chal.result.total_result.status = Status.JudgeError
                chal.result.total_result.ie_message = f"{lang.name} version grader not support, please contact administrator or problem setter."
                chal.result.total_result.message_type = MessageType.TEXT
                return False

            if self.context.userprog_compiler == Compiler.python3:
                grader_path = os.path.join(grader_folder_path, "grader.py")
                if not os.path.exists(grader_path):
                    chal.result.total_result.status = Status.JudgeError
                    chal.result.total_result.ie_message = "Python3 version grader need grader.py, but file not found.\n please contact administrator or problem setter."
                    chal.result.total_result.message_type = MessageType.TEXT
                    return False
        return True

    def get_source_files(self, chal: 'Challenge') -> list[tuple[str, str]]:
        lang = langs[self.context.userprog_compiler]
        copy_in = [(chal.code_path, f"a{lang.source_ext}")]

        if self.context.has_grader:
            grader_folder_path = os.path.join(chal.res_path, "grader", lang.name)
            for name in os.listdir(grader_folder_path):
                if os.path.isdir(os.path.join(grader_folder_path, name)):
                    continue

                copy_in.append((os.path.join(grader_folder_path, name), name))
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        lang = langs[self.context.userprog_compiler]
        sources = [f"a{lang.source_ext}"]
        if self.context.has_grader:
            if self.context.userprog_compiler in [
                Compiler.clang_c_11,
                Compiler.clang_cpp_17,
                Compiler.gcc_c_11,
                Compiler.gcc_cpp_17,
            ]:
                for sourcefile in glob.glob(
                    f"{chal.res_path}/grader/{lang.name}/*{lang.source_ext}"
                ):
                    sources.append(os.path.basename(sourcefile))

            if self.context.userprog_compiler == Compiler.python3:
                sources.append("grader.py")
                sources.reverse()

        return sources

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        return self.context.userprog_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return self.context.userprog_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        return f"a{langs[self.context.userprog_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file: str):
        self.context.userprog_path = chal.box.get_file(file)

    def on_compile_failure(self, chal: 'Challenge', res: SandboxResult):
        stderr = chal.box.get_file("stderr")
        if stderr:
            with open(stderr) as f:
                chal.result.total_result.ce_message = f.read()
            chal.box.delete_file("stderr")

        chal.result.total_result.message_type = MessageType.TEXT
        if res.status in [SandboxStatus.NonzeroExitStatus, SandboxStatus.Signalled]:
            chal.result.total_result.status = Status.CompileError

        elif res.status in [
            SandboxStatus.TimeLimitExceeded,
            SandboxStatus.MemoryLimitExceeded,
            SandboxStatus.OutputLimitExceeded,
        ]:
            chal.result.total_result.status = Status.CompileLimitExceeded
        elif res.status == SandboxStatus.RunnerError:
            chal.result.total_result.status = Status.InternalError

@dataclass(slots=True)
class CheckerCompilationTarget(CompilationTarget):
    context: 'CheckerMixin'
    def can_compile(self, chal: 'Challenge') -> bool:
        assert self.context.checker_compiler
        lang = langs[self.context.checker_compiler]
        checker_name = f"checker{lang.source_ext}"
        checker_path = os.path.join(chal.res_path, "checker")
        if not os.path.exists(os.path.join(checker_path, checker_name)):
            chal.result.total_result.status = Status.JudgeError
            chal.result.total_result.ie_message = f"{checker_name} not found, please contact administrator or problem setter"
            chal.result.total_result.message_type = MessageType.TEXT
            return False
        return True

    def get_source_files(self, chal: 'Challenge') -> list[tuple[str, str]]:
        assert self.context.checker_compiler
        lang = langs[self.context.checker_compiler]
        checker_name = f"checker{lang.source_ext}"
        checker_path = os.path.join(chal.res_path, "checker")
        copy_in = [(os.path.join(checker_path, checker_name), checker_name)]

        for name in os.listdir(checker_path):
            if os.path.isdir(name):
                continue

            copy_in.append((os.path.join(checker_path, name), name))
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        assert self.context.checker_compiler
        return [f"checker{langs[self.context.checker_compiler].source_ext}"]

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        assert self.context.checker_compiler
        return self.context.checker_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return self.context.checker_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        assert self.context.checker_compiler
        return f"checker{langs[self.context.checker_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file: str):
        self.context.checker_path = chal.box.get_file(file)

    def on_compile_failure(self, chal: 'Challenge', res: SandboxResult):
        chal.result.total_result.status = Status.JudgeError
        chal.result.total_result.message_type = MessageType.TEXT
        stderr = chal.box.get_file("stderr")
        if stderr:
            with open(stderr) as f:
                chal.result.total_result.ce_message = f.read()
            chal.box.delete_file("stderr")