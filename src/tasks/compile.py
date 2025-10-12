from dataclasses import dataclass
from models import (
    SandboxStatus,
    Task,
    TaskEntry,
    Challenge,
    CompilationTarget,
)

from lang.base import langs

@dataclass(slots=True)
class CompileTask(Task):
    target: CompilationTarget

    def setup(self, chal: Challenge, task: TaskEntry) -> bool:
        # NOTE: Check CE / CLE / JE
        return self.target.can_compile(chal) and chal.result.total_result.status is None

    def run(self, chal: Challenge, task: TaskEntry):
        lang = langs[self.target.get_compiler(chal)]

        res = lang.compile(
            box=chal.box,
            copyin=self.target.get_source_files(chal),
            sources=self.target.get_source_list(chal),
            addition_args=self.target.get_compile_args(chal),
            executable_name=self.target.get_output_name(chal)
        )

        if res.status == SandboxStatus.Normal:
            output_name = self.target.get_output_name(chal)
            self.target.on_compile_success(chal, output_name)
        else:
            self.target.on_compile_failure(chal, res)

    def finish(self, chal: Challenge, task: TaskEntry):
        pass
