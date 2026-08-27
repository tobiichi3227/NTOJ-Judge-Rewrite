import decimal
import threading
import uuid

import config
from lang.base import langs
from models import (
    Challenge,
    CommunicationIOType,
    Compiler,
    MessageType,
    SandboxStatus,
    SignalErrorMessage,
    Status,
    Task,
    TaskEntry,
    TestData,
)
from problem.mixins import ManagerMixin, UserProgramMixin
from sandbox.sandbox import SandboxParams, SandboxResult
from utils import logger


execute_id = 0
execute_id_lock = threading.Lock()


def next_execute_id() -> int:
    global execute_id
    with execute_id_lock:
        execute_id += 1
        return execute_id


def next_cpuset() -> str:
    if not config.CPUSET:
        return ""
    return config.CPUSET[next_execute_id() % len(config.CPUSET)]


class CommunicationExecuteTask(Task):
    _USER_FAILURE_PRIORITY = {
        SandboxStatus.NonzeroExitStatus: 1,
        SandboxStatus.Signalled: 2,
        SandboxStatus.DisallowedSyscall: 2,
        SandboxStatus.TimeLimitExceeded: 3,
        SandboxStatus.MemoryLimitExceeded: 4,
        SandboxStatus.OutputLimitExceeded: 5,
        SandboxStatus.RunnerError: 6,
    }

    def __init__(self, testdata: TestData):
        self.testdata = testdata

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        if chal.result.total_result.status is not None:
            logger.debug(
                f"Skipping testdata {self.testdata.id} because total result is set"
            )
            return False

        if chal.skip_nonac and all(
            subtask in chal.skip_subtasks for subtask in self.testdata.subtasks
        ):
            logger.debug(
                f"Skipping communication testdata {self.testdata.id} due to skip_nonac"
            )
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

    @staticmethod
    def _read_box_file(chal: Challenge, name: str) -> str:
        path = chal.box.get_file(name)
        if path is None:
            return ""
        try:
            with open(path) as file:
                return file.read()
        finally:
            chal.box.delete_file(name)

    @staticmethod
    def _sandbox_status_name(result: SandboxResult) -> str:
        try:
            return SandboxStatus(result.status).name
        except ValueError:
            return f"Unknown({result.status})"

    def _set_manager_je(
        self, chal: Challenge, result: SandboxResult, reason: str
    ):
        status_name = self._sandbox_status_name(result)
        logger.error(
            f"Manager failed for chal {chal.chal_id} testdata {self.testdata.id}: "
            f"{status_name}, exit_status={result.exit_status}, error={result.error}"
        )
        testdata_result = chal.result.testdata_results[self.testdata.id]
        testdata_result.status = Status.JudgeError
        testdata_result.message = reason
        testdata_result.message_type = MessageType.TEXT

    def _set_user_failure(
        self, chal: Challenge, process_index: int, result: SandboxResult
    ):
        testdata_result = chal.result.testdata_results[self.testdata.id]
        status = result.status
        if status == SandboxStatus.TimeLimitExceeded:
            testdata_result.status = Status.TimeLimitExceeded
        elif status == SandboxStatus.MemoryLimitExceeded:
            testdata_result.status = Status.MemoryLimitExceeded
        elif status == SandboxStatus.OutputLimitExceeded:
            testdata_result.status = Status.OutputLimitExceeded
        elif status == SandboxStatus.NonzeroExitStatus:
            testdata_result.status = Status.RuntimeError
        elif status in (SandboxStatus.Signalled, SandboxStatus.DisallowedSyscall):
            testdata_result.status = Status.RuntimeErrorSignalled
            if result.exit_status in SignalErrorMessage:
                testdata_result.message = SignalErrorMessage[result.exit_status]
                testdata_result.message_type = MessageType.TEXT
        else:
            testdata_result.status = Status.InternalError

        logger.info(
            f"Communication user process {process_index} failed for chal "
            f"{chal.chal_id} testdata {self.testdata.id}: "
            f"{self._sandbox_status_name(result)}, exit_status={result.exit_status}"
        )

    @staticmethod
    def _manager_result_requires_stop(result: SandboxResult) -> bool:
        return result.status != SandboxStatus.Normal

    @classmethod
    def _select_stop(
        cls, completed_results: dict[int, SandboxResult]
    ) -> int | None:
        """Choose which result in one polling batch triggers cancellation."""
        # A contestant failure takes precedence over a manager failure
        # observed in the same polling batch. This handles the common case
        # where a contestant crash causes the manager's FIFO I/O to fail
        # immediately afterwards.
        user_failures = [
            index
            for index, result in completed_results.items()
            if index > 0
            and result.status
            not in (SandboxStatus.Normal, SandboxStatus.Cancelled)
        ]
        if user_failures:
            # This is an explicit verdict-severity policy, not a claim about
            # chronological order inside the polling interval. Process index
            # is used only as a stable tie-breaker for equal statuses.
            return max(
                user_failures,
                key=lambda index: (
                    cls._USER_FAILURE_PRIORITY.get(
                        completed_results[index].status,
                        cls._USER_FAILURE_PRIORITY[SandboxStatus.RunnerError],
                    ),
                    -index,
                ),
            )

        manager_result = completed_results.get(0)
        if (
            manager_result is not None
            and cls._manager_result_requires_stop(manager_result)
        ):
            return 0
        return None

    def _score_manager_result(
        self,
        chal: Challenge,
        manager_result: SandboxResult,
        stdout_content: str,
        stderr_content: str,
    ):
        testdata_result = chal.result.testdata_results[self.testdata.id]

        if manager_result.status != SandboxStatus.Normal:
            self._set_manager_je(chal, manager_result, "manager runtime error")
            return

        manager_message = stderr_content.split("\n")[0]
        if manager_message:
            testdata_result.message = manager_message
            testdata_result.message_type = MessageType.TEXT

        try:
            score = decimal.Decimal(stdout_content.split("\n")[0])
            if not score.is_finite():
                raise decimal.InvalidOperation
        except (decimal.InvalidOperation, IndexError):
            self._set_manager_je(chal, manager_result, "invalid score")
            return

        if score >= 1:
            testdata_result.score = decimal.Decimal(1)
            testdata_result.status = Status.Accepted
        elif score <= 0:
            testdata_result.score = decimal.Decimal()
            testdata_result.status = Status.WrongAnswer
        else:
            testdata_result.score = score
            testdata_result.status = Status.PartialCorrect

    @staticmethod
    def _user_command(context: UserProgramMixin, process_args: list[str]):
        lang = langs[context.userprog_compiler]
        if context.userprog_compiler == Compiler.java:
            main = "stub" if context.has_grader else "main"
            return lang.get_execute_command("a", main, args=process_args)
        return lang.get_execute_command("a", args=process_args)

    @staticmethod
    def _manager_command(context: ManagerMixin, manager_args: list[str]):
        lang = langs[context.manager_compiler]
        if context.manager_compiler == Compiler.java:
            return lang.get_execute_command("manager", "manager", args=manager_args)
        return lang.get_execute_command("manager", args=manager_args)

    def run(self, chal: Challenge, task: TaskEntry):
        context = chal.problem_context
        assert isinstance(context, UserProgramMixin)
        assert isinstance(context, ManagerMixin)
        assert context.userprog_path
        assert context.manager_path

        logger.info(
            f"Executing communication testdata {self.testdata.id} for chal "
            f"{chal.chal_id} with {context.num_processes} user processes"
        )

        problem_time_limit = chal.limits.time // 10**6
        user_realtime_limit = 2 * problem_time_limit + 1000
        manager_time_limit = context.num_processes * problem_time_limit + 1000
        manager_realtime_limit = 2 * manager_time_limit + 1000
        memory_limit = chal.limits.memory // 1024
        output_limit = chal.limits.output // 1024

        fifo_token = uuid.uuid4().hex
        fifo_paths = []
        fifo_names = []
        for process_index in range(context.num_processes):
            m2u_name = f"{fifo_token}-m2u-{process_index}-fifo"
            u2m_name = f"{fifo_token}-u2m-{process_index}-fifo"
            chal.box.mkfifo(m2u_name)
            chal.box.mkfifo(u2m_name)
            fifo_names.extend((m2u_name, u2m_name))
            fifo_paths.append(
                (chal.box.gen_fifopath(m2u_name), chal.box.gen_fifopath(u2m_name))
            )

        manager_stdout_name = f"{self.testdata.id}-{fifo_token}-manager-stdout"
        manager_stderr_name = f"{self.testdata.id}-{fifo_token}-manager-stderr"

        # The manager reads u2m and writes m2u, so its pair order is the
        # reverse of the contestant process pair order.
        manager_args = []
        for process_index in range(context.num_processes):
            manager_args.extend(
                (f"u2m-{process_index}-fifo", f"m2u-{process_index}-fifo")
            )
        manager_exe, manager_command_args = self._manager_command(
            context, manager_args
        )
        manager_lang = langs[context.manager_compiler]
        manager_param = SandboxParams(
            exe_path=manager_exe,
            args=manager_command_args,
            time_limit=manager_time_limit,
            realtime_limit=manager_realtime_limit,
            memory_limit=memory_limit,
            stack_limit=65536,
            output_limit=output_limit,
            open_file_limit=max(32, 2 * context.num_processes + 8),
            proc_limit=32,
            stdin=self.testdata.inputpath,
            stdout=chal.box.gen_filepath(manager_stdout_name),
            stderr=chal.box.gen_filepath(manager_stderr_name),
            allow_proc=True,
            allow_mount_proc=context.manager_compiler == Compiler.java,
            cpuset=next_cpuset(),
        )
        if context.manager_compiler == Compiler.java:
            manager_param.add_bind_path("/usr/lib/jvm/", "usr/lib/jvm/")
            manager_param.add_bind_path("/etc/java-21-openjdk/", "etc/java-21-openjdk/")
            manager_param.add_env("JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64")

        manager_param.add_copy_in_path(context.manager_path, "manager")
        for process_index, (m2u_path, u2m_path) in enumerate(fifo_paths):
            manager_param.add_copy_in_path(
                m2u_path, f"m2u-{process_index}-fifo", False
            )
            manager_param.add_copy_in_path(
                u2m_path, f"u2m-{process_index}-fifo", False
            )

        params = [manager_param]
        for process_index, (m2u_path, u2m_path) in enumerate(fifo_paths):
            if context.communication_io_type == CommunicationIOType.STDIO:
                process_args = [str(process_index)]
            else:
                process_args = ["m2u-fifo", "u2m-fifo"]
                if context.num_processes > 1:
                    process_args.append(str(process_index))

            user_exe, user_args = self._user_command(context, process_args)
            user_lang = langs[context.userprog_compiler]
            user_param = SandboxParams(
                exe_path=user_exe,
                args=user_args,
                time_limit=problem_time_limit,
                realtime_limit=user_realtime_limit,
                memory_limit=memory_limit,
                stack_limit=65536,
                output_limit=output_limit,
                proc_limit=user_lang.allow_thread_count,
                allow_proc=user_lang.allow_thread_count > 1,
                allow_mount_proc=context.userprog_compiler == Compiler.java,
                cpuset=next_cpuset(),
            )
            if context.userprog_compiler == Compiler.java:
                user_param.add_bind_path("/usr/lib/jvm/", "usr/lib/jvm/")
                user_param.add_bind_path("/etc/java-21-openjdk/", "etc/java-21-openjdk/")
                user_param.add_env("JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64")
            user_param.add_copy_in_path(context.userprog_path, "a")
            if context.communication_io_type == CommunicationIOType.STDIO:
                user_param.stdin = m2u_path
                user_param.stdout = u2m_path
            else:
                user_param.add_copy_in_path(m2u_path, "m2u-fifo", False)
                user_param.add_copy_in_path(u2m_path, "u2m-fifo", False)
            params.append(user_param)

        try:
            execution_result = chal.box.run_sandbox_with_cancellation(
                params, self._select_stop
            )
        finally:
            for fifo_name in fifo_names:
                chal.box.delete_fifo(fifo_name)

        results = execution_result.results
        manager_result = results[0]
        user_results = results[1:]
        testdata_result = chal.result.testdata_results[self.testdata.id]
        testdata_result.time = sum(result.time for result in user_results)
        testdata_result.memory = sum(result.memory for result in user_results)

        stdout_content = self._read_box_file(chal, manager_stdout_name)
        stderr_content = self._read_box_file(chal, manager_stderr_name)

        cancelled_by = execution_result.cancelled_by
        if cancelled_by is not None and cancelled_by > 0:
            self._set_user_failure(
                chal, cancelled_by - 1, results[cancelled_by]
            )
            return
        if cancelled_by == 0:
            self._set_manager_je(chal, manager_result, "manager runtime error")
            return

        self._score_manager_result(
            chal, manager_result, stdout_content, stderr_content
        )

    def finish(self, chal: Challenge, task: TaskEntry):
        testdata_result = chal.result.testdata_results[self.testdata.id]
        logger.debug(
            f"Communication execution finished for testdata {self.testdata.id} "
            f"of chal {chal.chal_id}: {testdata_result.status}"
        )
        chal.reporter(
            {
                "chal_id": chal.chal_id,
                "task": "execute",
                "testdata_result": testdata_result,
            }
        )
        if testdata_result.status not in (Status.Accepted, Status.PartialCorrect):
            chal.skip_subtasks.update(self.testdata.subtasks)
