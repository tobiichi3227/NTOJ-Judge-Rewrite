import os
import glob

from models import CompilationTarget, Challenge, GoJudgeStatus, Status, MessageType, Compiler
from lang.base import langs

class BatchUserProgramTarget(CompilationTarget):
    def can_compile(self, chal: 'Challenge') -> bool:
        if chal.has_grader:
            lang = langs[chal.userprog_compiler]
            grader_folder_path = os.path.join(chal.res_path, "grader", lang.name)
            if not os.path.exists(grader_folder_path):
                chal.result.total_result.status = Status.JudgeError
                chal.result.total_result.ie_message = f"{lang.name} version grader not support, please contact administrator or problem setter."
                chal.result.total_result.message_type = MessageType.TEXT
                return False

            if chal.userprog_compiler == Compiler.python3:
                grader_path = os.path.join(grader_folder_path, "grader.py")
                if not os.path.exists(grader_path):
                    chal.result.total_result.status = Status.JudgeError
                    chal.result.total_result.ie_message = "Python3 version grader need grader.py, but file not found.\n please contact administrator or problem setter."
                    chal.result.total_result.message_type = MessageType.TEXT
                    return False
        return True

    def get_source_files(self, chal: 'Challenge') -> dict[str, dict]:
        lang = langs[chal.userprog_compiler]
        copy_in = {f"a{lang.source_ext}": {"src": chal.code_path}}

        if chal.has_grader:
            grader_folder_path = os.path.join(chal.res_path, "grader", lang.name)
            for name in os.listdir(grader_folder_path):
                if os.path.isdir(os.path.join(grader_folder_path, name)):
                    continue

                copy_in[name] = {"src": os.path.join(grader_folder_path, name)}
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        lang = langs[chal.userprog_compiler]
        sources = [f"a{lang.source_ext}"]
        if chal.has_grader:
            if chal.userprog_compiler in [
                Compiler.clang_c_11,
                Compiler.clang_cpp_17,
                Compiler.gcc_c_11,
                Compiler.gcc_cpp_17,
            ]:
                for sourcefile in glob.glob(
                    f"{chal.res_path}/grader/{lang.name}/*{lang.source_ext}"
                ):
                    sources.append(os.path.basename(sourcefile))

            if chal.userprog_compiler == Compiler.python3:
                sources.append("grader.py")
                sources.reverse()

        return sources

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        return chal.userprog_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return chal.userprog_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        return f"a{langs[chal.userprog_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file_id: str):
        chal.userprog_id = file_id

    def on_compile_failure(self, chal: 'Challenge', res: dict):
        chal.result.total_result.ce_message = res['files']['stderr']
        chal.result.total_result.message_type = MessageType.TEXT
        if res['status'] == GoJudgeStatus.NonzeroExitStatus:
            chal.result.total_result.status = Status.CompileError

        elif res['status'] in [
            GoJudgeStatus.TimeLimitExceeded,
            GoJudgeStatus.MemoryLimitExceeded,
            GoJudgeStatus.FileError,
        ]:
            chal.result.total_result.status = Status.CompileLimitExceeded


class BatchCheckerTarget(CompilationTarget):
    def can_compile(self, chal: 'Challenge') -> bool:
        assert chal.checker_compiler
        lang = langs[chal.checker_compiler]
        checker_name = f"checker{lang.source_ext}"
        checker_path = os.path.join(chal.res_path, "checker")
        if not os.path.exists(os.path.join(checker_path, checker_name)):
            chal.result.total_result.status = Status.JudgeError
            chal.result.total_result.ie_message = f"{checker_name} not found, please contact administrator or problem setter"
            chal.result.total_result.message_type = MessageType.TEXT
            return False
        return True

    def get_source_files(self, chal: 'Challenge') -> dict[str, dict]:
        lang = langs[chal.userprog_compiler]
        checker_name = f"checker{lang.source_ext}"
        checker_path = os.path.join(chal.res_path, "checker")
        copy_in = {checker_name: {"src": os.path.join(checker_path, checker_name)}}

        for name in os.listdir(checker_path):
            if os.path.isdir(name):
                continue

            copy_in[name] = {"src": os.path.join(checker_path, name)}
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        assert chal.checker_compiler
        return [f"checker{langs[chal.checker_compiler].source_ext}"]

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        assert chal.checker_compiler
        return chal.checker_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return chal.checker_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        assert chal.checker_compiler
        return f"checker{langs[chal.checker_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file_id: str):
        chal.checker_id = file_id

    def on_compile_failure(self, chal: 'Challenge', res: dict):
        chal.result.total_result.status = Status.JudgeError
        chal.result.total_result.ie_message = res['files']['stderr']
        chal.result.total_result.message_type = MessageType.TEXT