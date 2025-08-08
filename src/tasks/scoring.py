import decimal
import os

import executor_server
from models import (
    Challenge,
    CheckerType,
    GoJudgeStatus,
    MessageType,
    Status,
    Task,
    TaskEntry,
    TestData,
    Compiler,
)


from lang.base import langs

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

    def set_testdata_result_je(self, chal: Challenge):
        testdata_result = chal.result.testdata_results[self.testdata.id]
        testdata_result.status = Status.JudgeError
        testdata_result.memory = 0
        testdata_result.time = 0

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        # NOTE: Check CE / CLE / JE
        if chal.result.total_result.status in [
            Status.CompileError,
            Status.CompileLimitExceeded,
            Status.JudgeError,
        ]:
            return False

        # NOTE: TOJ Format Checker allow all status
        if chal.checker_type != CheckerType.TOJ:
            return (
                chal.result.testdata_results[self.testdata.id].status == Status.Accepted
            )
        return True

    def run(self, chal: Challenge, task: TaskEntry):
        assert chal.checker_type not in [CheckerType.TOJ, CheckerType.IOREDIR], (
            "TODO: CheckerType TOJ and IOREDIR"
        )
        testdata_result = chal.result.testdata_results[self.testdata.id]
        if chal.checker_type in [
            CheckerType.DIFF,
            CheckerType.DIFF_STRICT,
            CheckerType.DIFF_FLOAT4,
            CheckerType.DIFF_FLOAT6,
            CheckerType.DIFF_FLOAT9,
        ]:
            # TODO: random "in", "out", "ans" string for security
            res = executor_server.exec(
                {
                    "cmd": [
                        {
                            "args": langs[Compiler.clang_cpp_17].get_execute_command(
                                "checker", args=["in", "out", "ans"]
                            ),
                            "env": ["PATH=/usr/bin:/bin"],
                            "files": [
                                {"content": ""},
                                {"content": ""},
                                {"content": ""},
                            ],
                            "cpuLimit": 2000 * 10**6,
                            "memoryLimit": 262144 * 1024,
                            "stackLimit": 65536 * 1024,
                            "procLimit": 1,
                            "strictMemoryLimit": False,
                            "copyIn": {
                                "checker": {
                                    "src": os.path.join(
                                        DEFAULT_CHECKER_PATH,
                                        DEFAULT_CHECKER[chal.checker_type],
                                    )
                                },
                                "in": {"src": self.testdata.inputpath},
                                "out": {"src": self.testdata.outputpath},
                                "ans": {"fileId": self.testdata.useroutput_id},
                            },
                        }
                    ]
                }
            )
            res = res["results"][0]
            if res["status"] == GoJudgeStatus.Accepted:
                testdata_result.status = Status.Accepted
            else:
                chal.result.testdata_results[
                    self.testdata.id
                ].status = Status.WrongAnswer

        elif chal.checker_type in [
            CheckerType.CMS_TPS_TESTLIB,
            CheckerType.STD_TESTLIB,
        ]:
            assert chal.checker_compiler
            lang = langs[chal.checker_compiler]
            if chal.userprog_compiler != Compiler.java:
                args = lang.get_execute_command("checker", args=["in", "out", "ans"])
            else:
                args = lang.get_execute_command(
                    "checker", "checker", args=["in", "out", "ans"]
                )
            res = executor_server.exec(
                {
                    "cmd": [
                        {
                            "args": args,
                            "env": ["PATH=/usr/bin:/bin"],
                            "files": [
                                {"content": ""},
                                {"name": "stdout", "max": 65536},
                                {"name": "stderr", "max": 65536},
                            ],
                            "cpuLimit": 2000 * 10**6,
                            "memoryLimit": 262144 * 1024,
                            "stackLimit": 65536 * 1024,
                            "procLimit": lang.allow_thread_count,
                            "strictMemoryLimit": False,
                            "copyIn": {
                                "checker": {"fileId": chal.checker_id},
                                "in": {"src": self.testdata.inputpath},
                                "out": {"src": self.testdata.outputpath},
                                "ans": {"fileId": self.testdata.useroutput_id},
                            },
                            "copyOut": ["stdout", "stderr"],
                        }
                    ]
                }
            )
            res = res["results"][0]

            if chal.checker_type == CheckerType.CMS_TPS_TESTLIB:
                if res["status"] != GoJudgeStatus.Accepted:
                    self.set_testdata_result_je(chal)
                    return

                checker_message = res["files"]["stderr"].split("\n")[0]
                if checker_message:
                    testdata_result.message = checker_message
                    testdata_result.message_type = MessageType.TEXT

                try:
                    score = float(res["files"]["stdout"].split("\n")[0])
                except ValueError:
                    self.set_testdata_result_je(chal)
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

            elif chal.checker_type == CheckerType.STD_TESTLIB:
                if res["status"] not in [
                    GoJudgeStatus.Accepted,
                    GoJudgeStatus.NonzeroExitStatus,
                ]:
                    self.set_testdata_result_je(chal)
                    return

                if res["exitStatus"] == 0:
                    testdata_result.status = Status.Accepted
                elif res["exitStatus"] in [1, 2]:
                    testdata_result.status = Status.WrongAnswer
                elif res["exitStatus"] == 3:
                    self.set_testdata_result_je(chal)
                elif res["exitStatus"] == 7:
                    testdata_result.status = Status.PartialCorrect
                    line = res["files"]["stderr"].split("\n")[0]
                    line = line.split(" ")
                    try:
                        if line[0] != "points":
                            self.set_testdata_result_je(chal)
                        testdata_result.score = decimal.Decimal(line[1])
                    except (IndexError, decimal.DecimalException):
                        testdata_result.status = Status.JudgeError
                        testdata_result.score = decimal.Decimal()

                # TODO: testlib message
                checker_message = res["files"]["stdout"]
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

        assert self.testdata.useroutput_id
        executor_server.file_delete(self.testdata.useroutput_id)
