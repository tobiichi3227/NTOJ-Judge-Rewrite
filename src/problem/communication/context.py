import os
from dataclasses import dataclass

from models import (
    Challenge,
    CommunicationIOType,
    ProblemContext,
    TaskEntry,
    TestData,
    register_context,
)
from problem.compilation import ManagerCompilationTarget, UserProgramCompilationTarget
from problem.communication.execute import CommunicationExecuteTask
from problem.mixins import ManagerMixin, SummaryMixin, UserProgramMixin
from tasks.compile import CompileTask
from tasks.summary import SummaryTask
from utils import logger
from utils.challenge_builder import (
    get_exec_order,
    link_task,
    parse_communication_info,
    parse_limits,
    parse_summary_info,
    parse_user_program_info,
)


@register_context("communication")
@dataclass(slots=True)
class CommunicationProblemContext(
    ProblemContext,
    UserProgramMixin,
    ManagerMixin,
    SummaryMixin,
):
    problem_type: str = "communication"
    communication_io_type: CommunicationIOType = CommunicationIOType.FIFO
    num_processes: int = 1

    @classmethod
    def from_json(
        cls, obj: dict, chal: Challenge
    ) -> 'CommunicationProblemContext':
        logger.info(f"Creating communication problem context for chal {chal.chal_id}")
        context = cls(
            problem_type="communication",
            **parse_user_program_info(obj),
            **parse_communication_info(obj),
            **parse_summary_info(obj),
            grader_name="stub",
        )
        chal.limits = parse_limits(obj)
        logger.debug(
            "Communication context created: "
            f"compiler={context.userprog_compiler}, "
            f"manager_compiler={context.manager_compiler}, "
            f"io_type={context.communication_io_type}, "
            f"num_processes={context.num_processes}"
        )
        return context

    def build_task_dag(self, chal: Challenge) -> list[TaskEntry]:
        logger.info(f"Building communication task DAG for chal {chal.chal_id}")
        user_compile_task = TaskEntry(
            CompileTask(UserProgramCompilationTarget(self)),
            chal.internal_id,
            chal.priority,
        )
        manager_compile_task = TaskEntry(
            CompileTask(ManagerCompilationTarget(self)),
            chal.internal_id,
            chal.priority,
        )
        summary_task = TaskEntry(SummaryTask(), chal.internal_id, chal.priority)

        execute_tasks = []
        exec_order = get_exec_order(chal, chal.skip_nonac)
        for idx, testdata in enumerate(chal.testdatas.values()):
            execute_task = TaskEntry(
                CommunicationExecuteTask(testdata),
                chal.internal_id,
                chal.priority,
                order=exec_order[idx],
            )
            link_task(user_compile_task, execute_task)
            link_task(manager_compile_task, execute_task)
            link_task(execute_task, summary_task)
            execute_tasks.append(execute_task)

        link_task(user_compile_task, summary_task)
        link_task(manager_compile_task, summary_task)

        if chal.skip_nonac:
            ordered_indexes = sorted(
                range(len(execute_tasks)),
                key=lambda i: execute_tasks[i].order,
            )
            for prev, cur in zip(ordered_indexes, ordered_indexes[1:]):
                link_task(execute_tasks[prev], execute_tasks[cur])

        tasks = [user_compile_task, manager_compile_task, *execute_tasks, summary_task]
        logger.info(
            f"Communication task DAG built with {len(tasks)} tasks for "
            f"chal {chal.chal_id} ({len(execute_tasks)} testcases)"
        )
        return tasks

    def uses_testdata_scores(self) -> bool:
        return True

    def create_testdata(self, chal: Challenge, testdata_obj: dict) -> TestData:
        output_name = testdata_obj.get('output')
        return TestData(
            id=int(testdata_obj['id']),
            inputpath=os.path.join(chal.res_path, "testdata", testdata_obj['input']),
            outputpath=(
                os.path.join(chal.res_path, "testdata", output_name)
                if output_name
                else ""
            ),
        )
