import decimal
import os

from models import (
    Challenge,
    CheckerType,
    MessageType,
    SandboxStatus,
    Status,
    Task,
    TaskEntry,
    TestData,
    Compiler,
)


from lang.base import langs
from problem.mixins import CheckerMixin, UserProgramMixin
from sandbox.sandbox import SandboxParams

DEFAULT_CHECKER = {
    CheckerType.DIFF: "lcmp",
    CheckerType.DIFF_STRICT: "fcmp",
    CheckerType.DIFF_FLOAT4: "rcmp4",
    CheckerType.DIFF_FLOAT6: "rcmp6",
    CheckerType.DIFF_FLOAT9: "rcmp9",
}
DEFAULT_CHECKER_PATH = os.path.join(os.getcwd(), "default-checker")


class ScoringTask(Task):
    def __init__(self, testdata: TestData):
        self.testdata = testdata

    def set_testdata_result_je(self, chal: Challenge, reason: str):
        testdata_result = chal.result.testdata_results[self.testdata.id]
        testdata_result.status = Status.JudgeError
        testdata_result.memory = 0
        testdata_result.time = 0
        testdata_result.message = reason
        testdata_result.message_type = MessageType.TEXT

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        assert isinstance(chal.problem_context, CheckerMixin)
        # NOTE: Check CE / CLE / JE
        if chal.result.total_result.status in [
            Status.CompileError,
            Status.CompileLimitExceeded,
            Status.JudgeError,
        ]:
            return False

        # NOTE: TOJ Format Checker allow all status
        if chal.problem_context.checker_type != CheckerType.TOJ:
            return (
                chal.result.testdata_results[self.testdata.id].status == Status.Accepted
            )
        return True

    def run(self, chal: Challenge, task: TaskEntry):
        assert isinstance(chal.problem_context, CheckerMixin)
        assert chal.problem_context.checker_type not in [CheckerType.TOJ, CheckerType.IOREDIR], (
            "TODO: CheckerType TOJ and IOREDIR"
        )
        testdata_result = chal.result.testdata_results[self.testdata.id]
        if chal.problem_context.checker_type in [
            CheckerType.DIFF,
            CheckerType.DIFF_STRICT,
            CheckerType.DIFF_FLOAT4,
            CheckerType.DIFF_FLOAT6,
            CheckerType.DIFF_FLOAT9,
        ]:
            # TODO: random "in", "out", "ans" string for security
            exec, args = langs[Compiler.clang_cpp_17].get_execute_command(
                "checker", args=["in", "out", "ans"]
            )
            param = SandboxParams(
                exe_path=exec,
                args=args,
                time_limit=chal.limits.time // 10**6,
                memory_limit=chal.limits.memory // 1024,
                stack_limit=65536,
                proc_limit=1,
            )
            param.add_copy_in_path(
                os.path.join(
                    DEFAULT_CHECKER_PATH,
                    DEFAULT_CHECKER[chal.problem_context.checker_type],
                ),
                "checker",
            )
            param.add_copy_in_path(self.testdata.inputpath, "in")
            param.add_copy_in_path(self.testdata.outputpath, "out")
            assert self.testdata.useroutput_path
            param.add_copy_in_path(self.testdata.useroutput_path, "ans")
            res = chal.box.run_sandbox([param])[0]
            if res.status == SandboxStatus.Normal:
                testdata_result.status = Status.Accepted
            else:
                chal.result.testdata_results[self.testdata.id].status = Status.WrongAnswer

        elif chal.problem_context.checker_type in [
            CheckerType.CMS_TPS_TESTLIB,
            CheckerType.STD_TESTLIB,
        ]:
            assert isinstance(chal.problem_context, UserProgramMixin)
            assert chal.problem_context.checker_compiler
            lang = langs[chal.problem_context.checker_compiler]
            if chal.problem_context.userprog_compiler != Compiler.java:
                exec, args = lang.get_execute_command("checker", args=["in", "out", "ans"])
            else:
                exec, args = lang.get_execute_command(
                    "checker", "checker", args=["in", "out", "ans"]
                )
            param = SandboxParams(
                exe_path=exec,
                args=args,
                time_limit=chal.limits.time // 10**6,
                memory_limit=chal.limits.memory // 1024,
                stack_limit=65536,
                proc_limit=lang.allow_thread_count,
                stdout=chal.box.gen_filepath(f"{self.testdata.id}-checker-stdout"),
                stderr=chal.box.gen_filepath(f"{self.testdata.id}-checker-stderr"),
                allow_proc=lang.allow_thread_count > 1,
                allow_mount_proc=lang == Compiler.java,
            )
            assert chal.problem_context.checker_path
            param.add_copy_in_path(chal.problem_context.checker_path, "checker")
            param.add_copy_in_path(self.testdata.inputpath, "in")
            param.add_copy_in_path(self.testdata.outputpath, "out")
            assert self.testdata.useroutput_path
            param.add_copy_in_path(self.testdata.useroutput_path, "ans")
            res = chal.box.run_sandbox([param])[0]

            # TODO: Move this to utils
            stderr_content = ""
            stderr = chal.box.get_file(f"{self.testdata.id}-checker-stderr")
            if stderr:
                with open(stderr) as f:
                    stderr_content = f.read()
                chal.box.delete_file(f"{self.testdata.id}-checker-stderr")

            stdout_content = ""
            stdout = chal.box.get_file(f"{self.testdata.id}-checker-stdout")
            if stdout:
                with open(stdout) as f:
                    stdout_content = f.read()
                chal.box.delete_file(f"{self.testdata.id}-checker-stdout")

            if chal.problem_context.checker_type == CheckerType.CMS_TPS_TESTLIB:
                if res.status != SandboxStatus.Normal:
                    self.set_testdata_result_je(chal, "checker runtime error")
                    return

                checker_message = stderr_content.split("\n")[0]
                if checker_message:
                    testdata_result.message = checker_message
                    testdata_result.message_type = MessageType.TEXT

                try:
                    score = float(stdout_content.split("\n")[0])
                except ValueError:
                    self.set_testdata_result_je(chal, "invalid score")
                    return

                if score >= 1.0:
                    testdata_result.status = Status.Accepted
                elif score <= 0.0:
                    chal.result.testdata_results[
                        self.testdata.id
                    ].status = Status.WrongAnswer
                else:
                    chal.result.testdata_results[
                        self.testdata.id
                    ].status = Status.PartialCorrect
                testdata_result.score = decimal.Decimal(score)

            elif chal.problem_context.checker_type == CheckerType.STD_TESTLIB:
                if res.status not in [
                    SandboxStatus.Normal,
                    SandboxStatus.NonzeroExitStatus,
                ]:
                    self.set_testdata_result_je(chal, "checker runtime error")
                    return

                if res.exit_status == 0:
                    testdata_result.status = Status.Accepted
                elif res.exit_status in [1, 2]:
                    testdata_result.status = Status.WrongAnswer
                elif res.exit_status == 3:
                    self.set_testdata_result_je(chal, "checker internal error")
                elif res.exit_status == 7:
                    testdata_result.status = Status.PartialCorrect
                    line = stderr_content.split("\n")[0]
                    line = line.split(" ")
                    try:
                        if line[0] != "points":
                            self.set_testdata_result_je(chal, "invalid score")
                        testdata_result.score = decimal.Decimal(line[1])
                    except (IndexError, decimal.DecimalException):
                        testdata_result.status = Status.JudgeError
                        testdata_result.score = decimal.Decimal()

                # TODO: testlib message
                checker_message = stdout_content
                if checker_message:
                    testdata_result.message = checker_message
                    testdata_result.message_type = MessageType.TEXT

    def finish(self, chal: Challenge, task: TaskEntry):
        chal.reporter(
            {
                "chal_id": chal.chal_id,
                "task": "scoring",
                "testdata_result": chal.result.testdata_results[self.testdata.id],
            }
        )

        if chal.result.testdata_results[self.testdata.id].status not in [
            Status.Accepted,
            Status.PartialCorrect,
        ]:
            chal.skip_subtasks.update(self.testdata.subtasks)

        assert self.testdata.useroutput_path
        chal.box.delete_file(self.testdata.useroutput_path)