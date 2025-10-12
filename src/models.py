import decimal
from abc import ABC, abstractmethod
from enum import IntEnum
from dataclasses import dataclass, field
from types import FunctionType
from sandbox.sandbox import ChallengeBox, SandboxResult

class SandboxStatus(IntEnum):
    Normal = 1
    TimeLimitExceeded = 2
    MemoryLimitExceeded = 3
    OutputLimitExceeded = 4
    DisallowedSyscall = 5
    Signalled = 6
    NonzeroExitStatus = 7
    RunnerError = 8

class Status(IntEnum):
    Accepted = 1
    PartialCorrect = 2
    WrongAnswer = 3
    RuntimeError = 4  # Re:從零開始的競賽生活
    RuntimeErrorSignalled = 5  # 請不要把OJ當CTF打
    TimeLimitExceeded = 6
    MemoryLimitExceeded = 7
    OutputLimitExceeded = 8
    CompileError = 9  # 再不編譯啊
    CompileLimitExceeded = 10  # 沒事不要炸Judge
    InternalError = 11
    JudgeError = 12
    Skipped = 102


SignalErrorMessage = {
    4: "illegal hardware instruction",
    6: "abort",
    8: "floating point exception",
    11: "segmentation fault",
}

class Compiler(IntEnum):
    gcc_c_11 = 1
    clang_c_11 = 2
    gcc_cpp_17 = 3
    clang_cpp_17 = 4
    rust = 5
    python3 = 6
    java = 7
    asm_with_libc = 8
    asm_with_libstdcpp = 9


class CheckerType(IntEnum):
    DIFF = 1
    DIFF_STRICT = 2
    DIFF_FLOAT4 = 3
    DIFF_FLOAT6 = 4
    DIFF_FLOAT9 = 5
    CMS_TPS_TESTLIB = 6
    STD_TESTLIB = 7
    IOREDIR = 8
    TOJ = 9

    @classmethod
    def need_build_checkers(cls):
        return [cls.CMS_TPS_TESTLIB, cls.STD_TESTLIB, cls.TOJ, cls.IOREDIR]


class TaskType(IntEnum):
    COMPILE = 1
    EXECUTE = 2
    SCORING = 3
    SUMMARY = 4


class CompileTaskType(IntEnum):
    USER = 1
    CHECKER = 2
    SUMMARY = 3


class MessageType(IntEnum):
    NONE = 1
    TEXT = 2
    HTML = 3


class SummaryType(IntEnum):
    GROUPMIN = 1
    OVERWRITE = 2
    CUSTOM = 3


internal_id = 0
task_id = 0


def next_internal_id() -> int:
    global internal_id
    internal_id += 1
    return internal_id


def next_task_id() -> int:
    global task_id
    task_id += 1
    return task_id

def next_challenge_box() -> ChallengeBox:
    return ChallengeBox("/dev/shm/ntoj-judge-sandbox", internal_id)

@dataclass(frozen=True, slots=True)
class Limits:
    time: int
    memory: int
    output: int


@dataclass(slots=True)
class TestData:
    id: int
    inputpath: str
    outputpath: str
    useroutput_path: str | None = None
    subtasks: set[int] = field(default_factory=set)


@dataclass(slots=True)
class TestDataResult:
    id: int
    score: decimal.Decimal = decimal.Decimal()
    time: int = 0
    memory: int = 0
    message: str = ""
    message_type: MessageType = MessageType.NONE
    status: Status | None = None


@dataclass(slots=True)
class SubtaskResult:
    time: int = 0
    memory: int = 0
    score: decimal.Decimal = decimal.Decimal()
    status: Status | None = None


@dataclass(slots=True)
class TotalResult:
    time: int = 0
    memory: int = 0
    score: decimal.Decimal = decimal.Decimal()
    status: Status | None = None
    ce_message: str = ""
    ie_message: str = ""
    message_type: MessageType = MessageType.NONE


@dataclass(slots=True)
class Result:
    chal_id: int
    total_result: TotalResult = field(default_factory=TotalResult)
    subtask_results: dict[int, SubtaskResult] = field(default_factory=dict)
    testdata_results: dict[int, TestDataResult] = field(default_factory=dict)


@dataclass(slots=True)
class Subtask:
    id: int
    score: decimal.Decimal
    testdatas: list[TestData] = field(default_factory=list)
    dependency_subtasks: list[int] = field(default_factory=list)


@dataclass(slots=True)
class Challenge:
    chal_id: int
    pro_id: int
    contest_id: int
    acct_id: int
    priority: int

    code_path: str
    res_path: str
    limits: Limits = None
    result: Result = None

    problem_context: 'ProblemContext' = None

    reporter: FunctionType = lambda: 0
    skip_nonac: bool = False
    skip_subtasks: set[int] = field(default_factory=set)

    internal_id: int = field(default_factory=next_internal_id)
    box: ChallengeBox = field(default_factory=next_challenge_box)

    testdatas: dict[int, TestData] = field(default_factory=dict)
    subtasks: dict[int, Subtask] = field(default_factory=dict)


@dataclass(slots=True)
class Task(ABC):
    @abstractmethod
    def setup(self, chal: Challenge, task: "TaskEntry") -> bool:
        pass

    @abstractmethod
    def run(self, chal: Challenge, task: "TaskEntry"):
        pass

    @abstractmethod
    def finish(self, chal: Challenge, task: "TaskEntry"):
        pass

@dataclass(slots=True)
class TaskEntry:
    task: Task
    internal_id: int
    priority: int
    task_id: int = field(default_factory=next_task_id)
    order: int = 0
    indeg_cnt: int = 0
    edges: list[int] = field(default_factory=list)

    def __lt__(self, other: "TaskEntry"):
        if self.priority != other.priority:
            return self.priority < other.priority

        if self.internal_id != other.internal_id:
            return self.internal_id < other.internal_id

        return self.order < other.order

@dataclass(slots=True)
class CompilationTarget(ABC):
    @abstractmethod
    def can_compile(self, chal: 'Challenge') -> bool:
        pass

    @abstractmethod
    def get_source_files(self, chal: 'Challenge') -> list[tuple[str, str]]:
        pass

    @abstractmethod
    def get_source_list(self, chal: 'Challenge') -> list[str]:
        pass

    @abstractmethod
    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        pass

    @abstractmethod
    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        pass

    @abstractmethod
    def get_output_name(self, chal: 'Challenge') -> str:
        pass

    @abstractmethod
    def on_compile_success(self, chal: 'Challenge', file: str):
        pass

    @abstractmethod
    def on_compile_failure(self, chal: 'Challenge', res: SandboxResult):
        pass

@dataclass(slots=True)
class ProblemContext(ABC):
    problem_type: str

    @classmethod
    @abstractmethod
    def from_json(cls, obj: dict, chal: 'Challenge') -> 'ProblemContext':
        pass

    @abstractmethod
    def build_task_dag(self, chal: 'Challenge') -> list[TaskEntry]:
        pass

    @abstractmethod
    def create_testdata(self, chal: 'Challenge', testdata_obj: dict) -> TestData:
        pass


_CONTEXT_REGISTRY: dict[str, type[ProblemContext]] = {}

def register_context(problem_type: str):
    def decorator(cls: type[ProblemContext]):
        _CONTEXT_REGISTRY[problem_type] = cls
        return cls
    return decorator

def get_context_class(problem_type: str) -> type[ProblemContext]:
    if problem_type not in _CONTEXT_REGISTRY:
        raise ValueError(f"Unknown problem type: {problem_type}")
    return _CONTEXT_REGISTRY[problem_type]