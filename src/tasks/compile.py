import os
import glob
from models import (
    MessageType,
    Task,
    TaskEntry,
    Challenge,
    GoJudgeStatus,
    Status,
    CompileTaskType,
    Compiler,
)

from lang.base import langs


class CompileTask(Task):
    def __init__(self, compile_task_type: CompileTaskType):
        self.compile_task_type = compile_task_type

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        # NOTE: Check CE / CLE / JE
        if chal.result.total_result.status is not None:
            return False

        return True

    def run(self, chal: Challenge, task: TaskEntry):
        if self.compile_task_type == CompileTaskType.USER:
            lang = langs[chal.userprog_compiler]
            sources = [f"a{lang.source_ext}"]
            copy_in = {f"a{lang.source_ext}": {"src": chal.code_path}}
            if chal.has_grader:
                grader_path = os.path.join(chal.res_path, "grader", lang.name)
                if not os.path.exists(grader_path):
                    chal.result.total_result.status = Status.JudgeError
                    chal.result.total_result.ie_message = f"{lang.name} version grader not support, please contact administrator or problem setter"
                    chal.result.total_result.message_type = MessageType.TEXT
                    return

                for name in os.listdir(grader_path):
                    if os.path.isdir(name):
                        continue

                    copy_in[name] = {"src": os.path.join(grader_path, name)}

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

            res = lang.compile(
                copy_in, sources, chal.userprog_compile_args, f"a{lang.executable_ext}"
            )

        elif self.compile_task_type == CompileTaskType.CHECKER:
            assert chal.checker_compiler
            lang = langs[chal.checker_compiler]
            checker_name = f"checker{lang.source_ext}"
            checker_path = os.path.join(chal.res_path, "checker")
            copy_in = {checker_name: {"src": os.path.join(checker_path, checker_name)}}
            sources = [checker_name]
            if not os.path.exists(os.path.join(checker_path, checker_name)):
                chal.result.total_result.status = Status.JudgeError
                chal.result.total_result.ie_message = f"{checker_name} not found, please contact administrator or problem setter"
                chal.result.total_result.message_type = MessageType.TEXT
                return

            for name in os.listdir(checker_path):
                if os.path.isdir(name):
                    continue

                copy_in[name] = {"src": os.path.join(checker_path, name)}

            res = lang.compile(
                copy_in, sources, chal.checker_compile_args, f"a{lang.executable_ext}"
            )

        else:
            assert False, "TODO: custom summary"

        assert res
        res = res["results"][0]

        if res["status"] == GoJudgeStatus.Accepted:
            if self.compile_task_type == CompileTaskType.USER:
                chal.userprog_id = res["fileIds"][f"a{lang.executable_ext}"]
            elif self.compile_task_type == CompileTaskType.CHECKER:
                chal.checker_id = res["fileIds"][f"a{lang.executable_ext}"]
        else:
            if self.compile_task_type == CompileTaskType.USER:
                chal.result.total_result.ce_message = res["files"]["stderr"]
                chal.result.total_result.message_type = MessageType.TEXT
                if res["status"] == GoJudgeStatus.NonzeroExitStatus:
                    chal.result.total_result.status = Status.CompileError
                elif res["status"] in [
                    GoJudgeStatus.TimeLimitExceeded,
                    GoJudgeStatus.MemoryLimitExceeded,
                    GoJudgeStatus.FileError,
                ]:
                    chal.result.total_result.status = Status.CompileLimitExceeded
            else:
                chal.result.total_result.ie_message = res["files"]["stderr"]
                chal.result.total_result.message_type = MessageType.TEXT
                chal.result.total_result.status = Status.JudgeError

    def finish(self, chal: Challenge, task: TaskEntry):
        pass
