import decimal

from models import Limits, CheckerType, SummaryType, TestData, Subtask, Compiler, ProblemContext, Challenge, TaskEntry

def parse_base_challenge_info(obj: dict) -> dict:
    return {
        'chal_id': obj['chal_id'],
        'pro_id': obj['pro_id'],
        'contest_id': obj.get('contest_id', 0),
        'acct_id': obj['acct_id'],
        'priority': obj.get('priority', 0),
        'code_path': obj['code_path'],
        'res_path': obj['res_path'],
        'skip_nonac': obj.get('skip_nonac', False),
        'skip_subtasks': set(obj.get('skip_subtasks', [])),
    }


def parse_limits(obj: dict) -> Limits:
    lim = obj.get('limit', {})
    return Limits(
        time=lim.get('time', 1000 * 10**6),
        memory=lim.get('memory', 262144 * 1024),
        output=lim.get('output', 64 * 1024 * 1024),
    )


def parse_checker_info(obj: dict) -> dict:
    checker_compiler_val = obj.get('checker_compiler')
    return {
        'checker_type': CheckerType(obj['checker_type']),
        'checker_compiler': Compiler(checker_compiler_val) if checker_compiler_val else None,
        'checker_compile_args': obj.get('checker_compile_args', []),
    }


def parse_summary_info(obj: dict) -> dict:
    return {
        'summary_type': SummaryType(obj.get('summary_type', SummaryType.GROUPMIN)),
    }

def parse_user_program_info(obj: dict) -> dict:
    return {
        'userprog_compiler': Compiler(obj['userprog_compiler']),
        'userprog_compile_args': obj.get('userprog_compile_args', []),
        'has_grader': obj.get('has_grader', False),
    }

def parse_testdatas_and_subtasks(obj: dict, chal: 'Challenge', context: ProblemContext) -> tuple[dict[int, TestData], dict[int, Subtask]]:
    testdatas = {}
    subtasks = {}

    for td_obj in obj.get('testdatas', []):
        testdata = context.create_testdata(chal, td_obj)
        testdatas[testdata.id] = testdata

    for st_obj in obj.get('subtasks', []):
        subtask = Subtask(
            id=st_obj['id'],
            score=decimal.Decimal(str(st_obj['score'])),
            testdatas=[testdatas[td_id] for td_id in st_obj.get('testdatas', [])],
            dependency_subtasks=st_obj.get('dependency_subtasks', []),
        )
        subtasks[subtask.id] = subtask

        for testdata in subtask.testdatas:
            testdata.subtasks.add(subtask.id)

    return testdatas, subtasks

def get_exec_order(chal: Challenge, skip_nonac=False) -> list[int]:
    def lower_bound(layers: list[set[int]], pred) -> int:
        left, right = 0, len(layers)
        while left < right:
            mid = (left + right) // 2
            if pred(layers[mid]):
                left = mid + 1
            else:
                right = mid
        return left

    testdata_cnt = len(chal.testdatas)
    order = list(range(testdata_cnt))

    if skip_nonac:
        testdata_layer = [0] * testdata_cnt
        scan_order = sorted(
            range(testdata_cnt),
            key=lambda i: len(chal.testdatas[i].subtasks),
            reverse=True,
        )
        subtask_layers: list[set[int]] = []
        for testdata_idx in scan_order:
            pos = lower_bound(
                subtask_layers,
                lambda layer: all(
                    subtask in layer
                    for subtask in chal.testdatas[testdata_idx].subtasks
                ),
            )

            if pos == len(subtask_layers):
                subtask_layers.append(set())

            subtask_layers[pos].update(chal.testdatas[testdata_idx].subtasks)
            testdata_layer[testdata_idx] = pos

        inverse_order = sorted(range(testdata_cnt), key=lambda i: testdata_layer[i])
        for i, idx in enumerate(inverse_order):
            order[idx] = i

    return order

def link_task(a: TaskEntry, b: TaskEntry):
    """
    Link two TaskEntry objects by adding an edge from 'a' to 'b'.

    Args:
        a (TaskEntry): The source task entry.
        b (TaskEntry): The destination task entry.
    """
    a.edges.append(b.task_id)
    b.indeg_cnt += 1