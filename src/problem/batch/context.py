import os
from dataclasses import dataclass

from models import Challenge, ProblemContext, CheckerType, register_context, TaskEntry, TestData
from problem.mixins import CheckerMixin, SummaryMixin, UserProgramMixin
from problem.compilation import CheckerCompilationTarget, UserProgramCompilationTarget
from problem.batch.execute import BatchExecuteTask
from utils.challenge_builder import parse_checker_info, parse_limits, parse_summary_info, parse_user_program_info, get_exec_order, link_task
from utils import logger
from tasks.compile import CompileTask
from tasks.scoring import ScoringTask
from tasks.summary import SummaryTask

@register_context("batch")
@dataclass(slots=True)
class BatchProblemContext(ProblemContext, UserProgramMixin, CheckerMixin, SummaryMixin):
    problem_type: str = "batch"

    @classmethod
    def from_json(cls, obj: dict, chal: 'Challenge') -> 'BatchProblemContext':
        logger.info(f"Creating batch problem context for chal {chal.chal_id}")
        context = cls(
            problem_type="batch",
            **parse_user_program_info(obj),
            **parse_checker_info(obj),
            **parse_summary_info(obj),
        )
        chal.limits = parse_limits(obj)
        logger.debug(f"Batch context created: compiler={context.userprog_compiler}, checker_type={context.checker_type}")
        return context

    def build_task_dag(self, chal: 'Challenge') -> list[TaskEntry]:
        logger.info(f"Building task DAG for chal {chal.chal_id}")
        tasks = []
        def add_task(task: TaskEntry):
            tasks.append(task)

        compile_task = TaskEntry(
            CompileTask(UserProgramCompilationTarget(self)),
            chal.internal_id,
            chal.priority,
        )

        summary_task = TaskEntry(
            SummaryTask(),
            chal.internal_id,
            chal.priority,
        )

        exec_tasks = []
        scoring_tasks = []
        exec_order = get_exec_order(chal, chal.skip_nonac)
        for idx, testdata in enumerate(chal.testdatas.values()):
            exec_task = TaskEntry(
                BatchExecuteTask(testdata),
                chal.internal_id,
                chal.priority,
                order=exec_order[idx],
            )
            scoring_task = TaskEntry(
                ScoringTask(testdata),
                chal.internal_id,
                chal.priority,
                order=exec_order[idx],
            )
            link_task(exec_task, scoring_task)
            link_task(scoring_task, summary_task)
            exec_tasks.append(exec_task)
            scoring_tasks.append(scoring_task)

        for exec_task in exec_tasks:
            link_task(compile_task, exec_task)

        assert isinstance(chal.problem_context, CheckerMixin)
        if chal.problem_context.checker_type in [
            CheckerType.CMS_TPS_TESTLIB,
            CheckerType.STD_TESTLIB,
            CheckerType.TOJ,
        ]:
            checker_compile_task = TaskEntry(
                CompileTask(CheckerCompilationTarget(self)),
                chal.internal_id,
                chal.priority,
            )
            for scoring_task in scoring_tasks:
                link_task(checker_compile_task, scoring_task)
            add_task(checker_compile_task)

        add_task(compile_task)
        for t in exec_tasks:
            add_task(t)
        for t in scoring_tasks:
            add_task(t)
        add_task(summary_task)

        code_folder_path = os.path.dirname(chal.code_path)
        output_zip_path = os.path.join(code_folder_path, "output.zip")
        if os.path.exists(output_zip_path):
            try:
                os.remove(output_zip_path)
            except Exception as e:
                logger.error(f"Failed to remove existing output.zip for chal {chal.chal_id}: {e}")

        logger.info(f"Task DAG built with {len(tasks)} tasks for chal {chal.chal_id} ({len(exec_tasks)} testcases)")
        return tasks

    def create_testdata(self, chal: 'Challenge', testdata_obj: dict) -> TestData:
        return TestData(
            id=int(testdata_obj['id']),
            inputpath=os.path.join(chal.res_path, "testdata", testdata_obj['input']),
            outputpath=os.path.join(chal.res_path, "testdata", testdata_obj['output']),
        )
