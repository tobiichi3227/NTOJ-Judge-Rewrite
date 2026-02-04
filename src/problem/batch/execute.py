import os
import shutil

from models import (
    MessageType,
    SandboxStatus,
    Task,
    TaskEntry,
    TestData,
    Challenge,
    Status,
    Compiler,
    SignalErrorMessage,
)

from lang.base import langs

import config
from problem.mixins import UserProgramMixin
from sandbox.sandbox import SandboxParams


class BatchExecuteTask(Task):
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
        assert isinstance(chal.problem_context, UserProgramMixin)
        lang = langs[chal.problem_context.userprog_compiler]
        if chal.problem_context.userprog_compiler != Compiler.java:
            exec, args = lang.get_execute_command("a")
        else:
            if chal.problem_context.has_grader:
                exec, args = lang.get_execute_command("a", "grader")
            else:
                exec, args = lang.get_execute_command("a", "main")

        stdin_path = f"{self.testdata.id}-input"
        assert chal.box.get_file(stdin_path) is None
        shutil.copyfile(self.testdata.inputpath, stdin_path)
        param = SandboxParams(
            exe_path=exec,
            args=args,
            time_limit=chal.limits.time // 10**6, # TODO: use ms instead of ns
            memory_limit=chal.limits.memory // 1024, # TODO: use kib instead of byte
            stack_limit=65536,
            output_limit=chal.limits.output // 1024,
            proc_limit=lang.allow_thread_count,
            # TODO: cpu rate
            stdin=stdin_path,
            stdout=chal.box.gen_filepath(f"{self.testdata.id}-stdout"),
            allow_proc=lang.allow_thread_count > 1,
            allow_mount_proc=lang == Compiler.java,
        )
        assert chal.problem_context.userprog_path
        param.add_copy_in_path(chal.problem_context.userprog_path, "a")
        res = chal.box.run_sandbox([param])[0]
        try:
            os.remove(stdin_path)
        except FileNotFoundError:
            pass

        testdata_result = chal.result.testdata_results[self.testdata.id]
        testdata_result.memory = res.memory
        testdata_result.time = max(res.run_time, res.time)
        if chal.box.get_file(f"{self.testdata.id}-stdout"):
            self.testdata.useroutput_path = chal.box.get_file(f"{self.testdata.id}-stdout")

        if res.status == SandboxStatus.Normal:
            testdata_result.status = Status.Accepted
        elif res.status == SandboxStatus.TimeLimitExceeded:
            testdata_result.status = Status.TimeLimitExceeded
        elif res.status == SandboxStatus.MemoryLimitExceeded:
            testdata_result.status = Status.MemoryLimitExceeded
        elif res.status == SandboxStatus.OutputLimitExceeded:
            testdata_result.status = Status.OutputLimitExceeded
        elif res.status == SandboxStatus.NonzeroExitStatus:
            testdata_result.status = Status.RuntimeError
        elif res.status == SandboxStatus.Signalled:
            testdata_result.status = Status.RuntimeErrorSignalled
            if res.exit_status in SignalErrorMessage:
                testdata_result.message = SignalErrorMessage[res.exit_status]
                testdata_result.message_type = MessageType.TEXT
        elif res.status == SandboxStatus.RunnerError:
            testdata_result.status = Status.InternalError

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
            if self.testdata.useroutput_path:
                chal.box.delete_file(self.testdata.useroutput_path)
