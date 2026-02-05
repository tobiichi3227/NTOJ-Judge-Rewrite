import os
import shutil
import zipfile
import threading

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
from utils import logger

import config
from problem.mixins import UserProgramMixin
from sandbox.sandbox import SandboxParams

execute_id = 0
def next_execute_id() -> int:
    global execute_id
    execute_id += 1
    return execute_id

zip_lock = threading.Lock()

class BatchExecuteTask(Task):
    def __init__(self, testdata: TestData):
        self.testdata = testdata

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        # NOTE: Check CE / CLE / JE
        if chal.result.total_result.status is not None:
            logger.debug(f"Skipping testdata {self.testdata.id} due to total result status already set")
            return False

        if chal.skip_nonac:
            flag = True
            for subtask in self.testdata.subtasks:
                if subtask not in chal.skip_subtasks:
                    flag = False
                    break

            if flag:
                logger.debug(f"Skipping testdata {self.testdata.id} due to skip_nonac")
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
        logger.info(f"Executing testdata {self.testdata.id} for chal {chal.chal_id} with {lang.name}")
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
        cpuset = ""
        if config.CPUSET:
            cpuset = config.CPUSET[next_execute_id() % len(config.CPUSET)]
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
            cpuset=cpuset,
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
            if self.testdata.useroutput_path:
                try:
                    logger.info(f"Writing user output to zip for chal {chal.chal_id}, testdata {self.testdata.id}, filename: {self.testdata.id + 1}.ans")
                    code_folder_path = os.path.dirname(chal.code_path)

                    with zip_lock:
                        with zipfile.ZipFile(os.path.join(code_folder_path, "output.zip"), "a", compression=zipfile.ZIP_LZMA) as zf:
                            logger.debug(f"{zf.namelist()} already in zip for chal {chal.chal_id}")
                            zf.write(self.testdata.useroutput_path, f"{self.testdata.id + 1}.ans")
                    logger.info(f"Successfully wrote user output to zip for chal {chal.chal_id}, testdata {self.testdata.id}, filename: {self.testdata.id + 1}.ans")
                except Exception as e:
                    logger.error(f"Failed to write user output to zip for chal {chal.chal_id}, testdata {self.testdata.id}, filename: {self.testdata.id + 1}.ans: {e}")

        if res.status == SandboxStatus.Normal:
            testdata_result.status = Status.Accepted
            logger.info(f"Testdata {self.testdata.id} executed normally for chal {chal.chal_id}, time: {res.time}ms, memory: {res.memory}KB")
        elif res.status == SandboxStatus.TimeLimitExceeded:
            testdata_result.status = Status.TimeLimitExceeded
            logger.info(f"Testdata {self.testdata.id} TLE for chal {chal.chal_id}")
        elif res.status == SandboxStatus.MemoryLimitExceeded:
            testdata_result.status = Status.MemoryLimitExceeded
            logger.info(f"Testdata {self.testdata.id} MLE for chal {chal.chal_id}")
        elif res.status == SandboxStatus.OutputLimitExceeded:
            testdata_result.status = Status.OutputLimitExceeded
            logger.info(f"Testdata {self.testdata.id} OLE for chal {chal.chal_id}")
        elif res.status == SandboxStatus.NonzeroExitStatus:
            testdata_result.status = Status.RuntimeError
            logger.info(f"Testdata {self.testdata.id} runtime error for chal {chal.chal_id}, exit code: {res.exit_status}")
        elif res.status == SandboxStatus.Signalled:
            testdata_result.status = Status.RuntimeErrorSignalled
            logger.info(f"Testdata {self.testdata.id} signalled for chal {chal.chal_id}, signal: {res.exit_status}")
            if res.exit_status in SignalErrorMessage:
                testdata_result.message = SignalErrorMessage[res.exit_status]
                testdata_result.message_type = MessageType.TEXT
        elif res.status == SandboxStatus.RunnerError:
            testdata_result.status = Status.InternalError
            logger.error(f"Testdata {self.testdata.id} runner error for chal {chal.chal_id}")

    def finish(self, chal: Challenge, task: TaskEntry):
        logger.debug(f"Execution finished for testdata {self.testdata.id} of chal {chal.chal_id}")
        chal.reporter(
            {
                "chal_id": chal.chal_id,
                "task": "execute",
                "testdata_result": chal.result.testdata_results[self.testdata.id],
            }
        )

        if chal.result.testdata_results[self.testdata.id].status != Status.Accepted:
            logger.debug(f"Testdata {self.testdata.id} not accepted, marking subtasks as skip")
            chal.skip_subtasks.update(self.testdata.subtasks)
            if self.testdata.useroutput_path:
                chal.box.delete_file(self.testdata.useroutput_path)
