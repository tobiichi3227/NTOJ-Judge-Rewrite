from dataclasses import dataclass, field

from models import Compiler, CheckerType, SummaryType

@dataclass
class UserProgramMixin:
    userprog_compiler: 'Compiler' = None
    userprog_compile_args: list[str] = field(default_factory=list)
    userprog_path: str | None = None
    has_grader: bool = False

    def get_user_program_compile_target(self):
        from problem.compilation import UserProgramCompilationTarget
        return UserProgramCompilationTarget(self)

@dataclass
class CheckerMixin:
    checker_type: 'CheckerType' = None
    checker_compiler: 'Compiler | None' = None
    checker_compile_args: list[str] = field(default_factory=list)
    checker_path: str | None = None

    def has_custom_checker(self) -> bool:
        from models import CheckerType
        return self.checker_type in CheckerType.need_build_checkers()

    def get_checker_compile_target(self):
        from problem.compilation import CheckerCompilationTarget
        return CheckerCompilationTarget(self)


@dataclass
class SummaryMixin:
    summary_type: SummaryType = None
    summary_compiler: Compiler | None = None
    summary_compile_args: list[str] = field(default_factory=list)
    summary_id: str | None = None


# @dataclass
# class ManagerMixin:
#     manager_compiler: 'Compiler'
#     manager_compile_args: list[str] = field(default_factory=list)
#     manager_id: str | None = None

#     def get_manager_compile_target(self):
#         from tasks.targets.common import ManagerCompilationTarget
#         return ManagerCompilationTarget(self)