from models import (
    MessageType,
    Task,
    TaskEntry,
    TestData,
    Challenge,
    GoJudgeStatus,
    Status,
    Compiler,
    SignalErrorMessage,
)

from lang.base import langs

import executor_server


class ExecuteTask(Task):
    def __init__(self, testdata: TestData):
        self.testdata = testdata

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        # NOTE: Check CE / CLE / JE
        if chal.result.total_result.status is not None:
            return False

        if chal.skip_nonac:
            flag = True
            for subtask in self.testdata.subtasks:
                if subtask not in chal.skip_subtasks:
                    flag = False
                    break

            if flag:
                chal.result.testdata_results[self.testdata.id].status = Status.Skipped
                chal.reporter(
                    {
                        "chal_id": chal.chal_id,
                        "task": "execute",
                        "testdata_result": chal.result.testdata_results[
                            self.testdata.id
                        ],
                    }
                )
                return False

        return True

    def run(self, chal: Challenge, task: TaskEntry):
        lang = langs[chal.userprog_compiler]
        if chal.userprog_compiler != Compiler.java:
            args = lang.get_execute_command("a")
        else:
            if chal.has_grader:
                args = lang.get_execute_command("a", "grader")
            else:
                args = lang.get_execute_command("a", "main")
        res = executor_server.exec(
            {
                "cmd": [
                    {
                        "args": args,
                        "env": ["PATH=/usr/bin:/bin"],
                        "files": [
                            {"src": self.testdata.inputpath},
                            {"name": "stdout", "max": chal.limits.output},
                            {"name": "stderr", "max": chal.limits.output},
                        ],
                        "cpuLimit": chal.limits.time,
                        "memoryLimit": chal.limits.memory,
                        "procLimit": lang.allow_thread_count,
                        "copyIn": {"a": {"fileId": chal.userprog_id}},
                        "copyOutCached": ["stdout"],
                        "copyOutMax": chal.limits.output,
                    }
                ]
            }
        )
        res = res["results"][0]

        testdata_result = chal.result.testdata_results[self.testdata.id]
        testdata_result.memory = res["memory"]
        testdata_result.time = max(res["runTime"], res["time"])

        if res["status"] == GoJudgeStatus.Accepted:
            testdata_result.status = Status.Accepted
            self.testdata.useroutput_id = res["fileIds"]["stdout"]

        elif res["status"] == GoJudgeStatus.TimeLimitExceeded:
            testdata_result.status = Status.TimeLimitExceeded

        elif res["status"] == GoJudgeStatus.MemoryLimitExceeded:
            testdata_result.status = Status.MemoryLimitExceeded

        elif res["status"] == GoJudgeStatus.OutputLimitExceeded:
            testdata_result.status = Status.OutputLimitExceeded

        elif res["status"] == GoJudgeStatus.NonzeroExitStatus:
            testdata_result.status = Status.RuntimeError

        elif res["status"] == GoJudgeStatus.Signalled:
            testdata_result.status = Status.RuntimeErrorSignalled
            if res["exitStatus"] in SignalErrorMessage:
                testdata_result.message = SignalErrorMessage[res["exitStatus"]]
                testdata_result.message_type = MessageType.TEXT

    def finish(self, chal: Challenge, task: TaskEntry):
        chal.reporter(
            {
                "chal_id": chal.chal_id,
                "task": "execute",
                "testdata_result": chal.result.testdata_results[self.testdata.id],
            }
        )

        if chal.result.testdata_results[self.testdata.id].status != Status.Accepted:
            chal.skip_subtasks.update(self.testdata.subtasks)
