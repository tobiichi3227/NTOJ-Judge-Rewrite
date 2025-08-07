import decimal
import executor_server
from models import (
    CheckerType,
    MessageType,
    Status,
    SummaryType,
    Task,
    TaskEntry,
    Challenge,
)


class SummaryTask(Task):
    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        # NOTE: CE / CLE / JE need summary set testdata results and subtask results status to Status.Skipped
        if (
            chal.summary_type == SummaryType.CUSTOM
            and chal.result.total_result.status == Status.JudgeError
        ):
            return False
        return True

    def run(self, chal: Challenge, task: TaskEntry):
        assert chal.summary_type != SummaryType.CUSTOM, "TODO: Custom summary"
        result = chal.result

        for subtask_id, subtask_result in result.subtask_results.items():
            subtask_result.score = decimal.Decimal("Infinity")
            for testdata in chal.subtasks[subtask_id].testdatas:
                testdata_result = result.testdata_results[testdata.id]

                if testdata_result.status and testdata_result.status != Status.Skipped:
                    assert testdata_result.status not in [
                        Status.CompileError,
                        Status.CompileLimitExceeded,
                    ]
                    subtask_result.memory += testdata_result.memory
                    subtask_result.time = max(subtask_result.time, testdata_result.time)
                    if subtask_result.status:
                        subtask_result.status = max(
                            subtask_result.status, testdata_result.status
                        )
                    else:
                        subtask_result.status = testdata_result.status

                if subtask_result.status in [
                    Status.Accepted,
                    Status.PartialCorrect,
                ]:
                    if chal.checker_type in [
                        CheckerType.CMS_TPS_TESTLIB,
                        CheckerType.STD_TESTLIB,
                        CheckerType.TOJ,
                    ]:
                        if chal.summary_type == SummaryType.GROUPMIN:
                            subtask_result.score = min(
                                subtask_result.score,
                                chal.subtasks[subtask_id].score * testdata_result.score,
                            )

                        elif chal.summary_type == SummaryType.OVERWRITE:
                            subtask_result.score = min(
                                subtask_result.score, testdata_result.score
                            )
                    else:
                        subtask_result.score = chal.subtasks[subtask_id].score
                else:
                    subtask_result.score = decimal.Decimal("Infinity")

            if subtask_result.score.is_infinite():
                subtask_result.score = decimal.Decimal()

            for dep_subtask in chal.subtasks[subtask_id].dependency_subtasks:
                if result.subtask_results[dep_subtask].status not in [
                    Status.Accepted,
                    Status.PartialCorrect,
                ]:
                    subtask_result.status = Status.Skipped
                    subtask_result.score = decimal.Decimal()
                    subtask_result.memory = 0
                    subtask_result.time = 0

        # NOTE: This only occur CE/CLE/JE (when checker / summary got CE/CLE)
        for testdata_result in result.testdata_results.values():
            if not testdata_result.status:
                assert result.total_result.status in [
                    Status.CompileError,
                    Status.CompileLimitExceeded,
                    Status.JudgeError,
                ]
                testdata_result.status = Status.Skipped

        # NOTE: This only occur CE/CLE/JE (when checker / summary got CE/CLE) or subtask without having any testdata
        for subtask_id, subtask_result in result.subtask_results.items():
            if subtask_result.status is None:
                if len(chal.subtasks[subtask_id].testdatas) == 0:
                    subtask_result.status = Status.JudgeError
                    continue

                assert result.total_result.status in [
                    Status.CompileError,
                    Status.CompileLimitExceeded,
                    Status.JudgeError,
                ]
                subtask_result.status = Status.Skipped

        # NOTE: is no None means already CE/CLE/JE/IE
        if result.total_result.status is None:
            for subtask_result in result.subtask_results.values():
                result.total_result.memory += subtask_result.memory
                result.total_result.time = max(
                    subtask_result.time, result.total_result.time
                )

                assert subtask_result.status
                if subtask_result.status != Status.Skipped:
                    if result.total_result.status:
                        result.total_result.status = max(
                            subtask_result.status, result.total_result.status
                        )
                    else:
                        result.total_result.status = subtask_result.status
                result.total_result.score += subtask_result.score

        # NOTE: If total_result.status still None, it means there are no testdata and subtask
        if result.total_result.status is None:
            result.total_result.status = Status.JudgeError
            result.total_result.ie_message = "Problem do not have any testdata or subtask. Please contact administrator or problem setter."
            result.total_result.message_type = MessageType.TEXT

    def finish(self, chal: Challenge, task: TaskEntry):
        chal.reporter(
            {
                "chal_id": chal.chal_id,
                "task": "summary",
                "result": chal.result,
            }
        )

        if chal.checker_id:
            executor_server.file_delete(chal.checker_id)
        if chal.userprog_id:
            executor_server.file_delete(chal.userprog_id)
        if chal.summary_id:
            executor_server.file_delete(chal.summary_id)
