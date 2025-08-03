import time
import dataclasses
import decimal
import enum
import functools
import json
import multiprocessing.pool
import os
import signal
import shlex
import threading
from multiprocessing.dummy import Pool as ThreadingPool
from queue import PriorityQueue, Queue

import tornado.ioloop
import tornado.web
import tornado.websocket

import config
import executor_server
import utils
from models import *
from tasks.compile import CompileTask
from tasks.execute import ExecuteTask
from tasks.scoring import ScoringTask
from tasks.summary import SummaryTask
from lang.base import init_langs

server_running = True
ioloop = tornado.ioloop.IOLoop.current()
challenge_list: dict[int, Challenge] = {}
task_list: dict[int, TaskEntry] = {}
task_queue: PriorityQueue[TaskEntry] = PriorityQueue()
finish_queue = Queue()
task_event = threading.Event()
task_running_cnt = 0
threading_pool: multiprocessing.pool.Pool = ThreadingPool()


def link_task(a: TaskEntry, b: TaskEntry):
    a.edges.append(b.task_id)
    b.indeg_cnt += 1


def remove_task(task: TaskEntry):
    for next in task.edges:
        next_task = task_list[next]
        next_task.indeg_cnt -= 1

        if next_task.indeg_cnt == 0:
            task_queue.put(next_task)
    task_list.pop(task.task_id)


def add_task(task: TaskEntry):
    task_list[task.task_id] = task
    if task.indeg_cnt == 0:
        task_queue.put(task)


def run_task(chal: Challenge, task: TaskEntry, finish_queue: Queue[TaskEntry]):
    global task_running_cnt
    try:
        if task.task.setup(chal, task):
            task.task.run(chal, task)
            task.task.finish(chal, task)
        finish_queue.put(task)
    except Exception as e:
        import traceback

        traceback.print_exception(e)
        chal.result.total_result.status = Status.InternalError
        chal.result.total_result.memory = 0
        chal.result.total_result.time = 0
        chal.result.total_result.score = decimal.Decimal()
        for subtask_result in chal.result.subtask_results.values():
            subtask_result.memory = subtask_result.time = 0
            subtask_result.score = decimal.Decimal()
            subtask_result.status = Status.InternalError

        for testdata_result in chal.result.testdata_results.values():
            testdata_result.memory = testdata_result.time = 0
            testdata_result.score = decimal.Decimal()
            testdata_result.status = Status.InternalError
        if __debug__:
            chal.result.total_result.ie_message = "\n".join(
                traceback.format_exception(e)
            )
            chal.result.total_result.message_type = MessageType.TEXT

        task_running_cnt -= 1
        chal.reporter(
            {"chal_id": chal.chal_id, "task": "summary", "result": chal.result}
        )


def task_loop():
    global task_running_cnt
    while task_event.wait() and server_running:
        while task_running_cnt < config.JUDGE_TASK_MAXCONCURRENT:
            task = task_queue.get()
            threading_pool.apply_async(
                run_task,
                (challenge_list[task.internal_id], task, finish_queue),
            )
            task_running_cnt += 1

        task_event.clear()


def finish_task_loop():
    global task_running_cnt
    while server_running:
        finish_task = finish_queue.get()
        remove_task(finish_task)
        task_running_cnt -= 1
        task_event.set()


"""
obj = {
    "acct_id": 9787,
    "pro_id": 756,
    "contest_id": 0,
    "chal_id": 1110,
    "res_path": "/home/tobiichi3227/NTOJ-Judge-Rewrite/dev/res",
    "code_path": "/home/tobiichi3227/NTOJ-Judge-Rewrite/dev/test.cpp",
    "userprog_compiler": "g++",
    "userprog_compile_args": "",
    "checker_type": CheckerType.DIFF.value,
    "checker_compiler": None,
    "checker_compile_args": "",
    "summary_type": SummaryType.GROUPMIN.value,
    "summary_compiler": None,
    "summary_compile_args": "",
    "has_grader": False,
    "subtasks": [
        {"id": 0, "score": 20, "testdatas": [0], "dependency_subtasks": []},
        {"id": 1, "score": 30, "testdatas": [1], "dependency_subtasks": []},
        {"id": 2, "score": 50, "testdatas": [2], "dependency_subtasks": []},
    ],
    "limit": {
        "time": 1110 * 10**6,
        "memory": 262144 * 1024,
        "output": 1110,
    },
    "testdatas": [
        {"id": 0, "input": "1.in", "output": "1.out"},
        {"id": 1, "input": "2.in", "output": "2.out"},
        {"id": 2, "input": "3.in", "output": "3.out"},
    ],
    "priority": 1,
    "skip_nonac": False,
}
"""


def build_challenge(obj: dict):
    limits = Limits(
        obj["limit"]["time"], obj["limit"]["memory"], obj["limit"]["output"]
    )
    testdatas: dict[int, TestData] = {}
    res_path = obj["res_path"]

    result = Result(chal_id=obj["chal_id"])
    for t in obj["testdatas"]:
        testdata = TestData(
            int(t["id"]),
            os.path.join(res_path, "testdata", t["input"]),
            os.path.join(res_path, "testdata", t["output"]),
        )
        testdatas[t["id"]] = testdata
        result.testdata_results[t["id"]] = TestDataResult(t["id"])

    subtasks = {}
    for g in obj["subtasks"]:
        subtask = Subtask(
            id=int(g["id"]),
            score=decimal.Decimal(g["score"]),
            dependency_subtasks=g["dependency_subtasks"],
        )
        for t in g["testdatas"]:
            testdatas[t].subtasks.add(subtask.id)
            subtask.testdatas.append(testdatas[t])

        result.subtask_results[subtask.id] = SubtaskResult()
        subtasks[subtask.id] = subtask

    checker_type = CheckerType(obj["checker_type"])
    checker_compiler = None
    if obj["checker_compiler"] and checker_type in [
        CheckerType.CMS_TPS_TESTLIB,
        CheckerType.STD_TESTLIB,
        CheckerType.IOREDIR,
        CheckerType.TOJ,
    ]:
        checker_compiler = Compiler(obj["checker_compiler"])

    summary_type = SummaryType(obj["summary_type"])
    summary_compiler = None
    if obj["summary_compiler"] and summary_type == SummaryType.CUSTOM:
        checker_compiler = Compiler(obj["summary_compiler"])

    chal = Challenge(
        acct_id=obj["acct_id"],
        pro_id=obj["pro_id"],
        contest_id=obj["contest_id"],
        chal_id=obj["chal_id"],
        priority=obj["priority"],
        skip_nonac=obj["skip_nonac"],
        limits=limits,
        res_path=res_path,
        code_path=obj["code_path"],
        userprog_compiler=Compiler(obj["userprog_compiler"]),
        userprog_compile_args=shlex.split(obj["userprog_compile_args"]),
        checker_type=checker_type,
        checker_compiler=checker_compiler,
        checker_compile_args=shlex.split(obj["checker_compile_args"]),
        summary_type=summary_type,
        summary_compiler=summary_compiler,
        summary_compile_args=shlex.split(obj["summary_compile_args"]),
        testdatas=testdatas,
        subtasks=subtasks,
        has_grader=obj["has_grader"],
        result=result,
    )

    return chal


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


def push_challenge(chal: Challenge):
    challenge_list[chal.internal_id] = chal
    compile_task = TaskEntry(
        internal_id=chal.internal_id,
        task=CompileTask(CompileTaskType.USER),
        priority=1,
    )

    summary_task = TaskEntry(
        internal_id=chal.internal_id,
        task=SummaryTask(),
        priority=chal.priority,
    )

    exec_tasks = []
    scoring_tasks = []
    exec_order = get_exec_order(chal, chal.skip_nonac)
    for idx, testdata in enumerate(chal.testdatas.values()):
        exec_task = TaskEntry(
            internal_id=chal.internal_id,
            task=ExecuteTask(testdata),
            priority=chal.priority,
            order=exec_order[idx],
        )
        scoring_task = TaskEntry(
            internal_id=chal.internal_id,
            task=ScoringTask(testdata),
            priority=chal.priority,
            order=exec_order[idx],
        )
        link_task(exec_task, scoring_task)
        link_task(scoring_task, summary_task)
        exec_tasks.append(exec_task)
        scoring_tasks.append(scoring_task)

    for exec_task in exec_tasks:
        link_task(compile_task, exec_task)

    if chal.checker_type in [
        CheckerType.CMS_TPS_TESTLIB,
        CheckerType.STD_TESTLIB,
        CheckerType.TOJ,
    ]:
        checker_compile_task = TaskEntry(
            internal_id=chal.internal_id,
            task=CompileTask(CompileTaskType.CHECKER),
            priority=chal.priority,
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

    task_event.set()


class Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)

        elif dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)

        elif isinstance(o, enum.Enum):
            return o.value

        assert o is not None

        return super().default(o)


# TODO: 避免 challenge 已經在 challenge 的 chal
class JudgeWebSocketClient(tornado.websocket.WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings["websocket_ping_interval"] = 5

    async def open(self):
        utils.logger.info("Backend connected")
        pass

    def reporter(self, result):
        ioloop.add_callback(lambda: self.write_message(json.dumps(result, cls=Encoder)))

    async def on_message(self, msg):
        self.ping()
        obj = json.loads(msg)
        try:
            chal = build_challenge(obj)
        except Exception as e:
            import traceback

            # TODO: 有可能連 chal_id 都不知道，這個只有 backend 知道而已
            chal_id = 1110
            result = Result(chal_id)
            result.total_result.status = Status.InternalError
            result.total_result.memory = 0
            result.total_result.time = 0
            result.total_result.score = decimal.Decimal()
            if __debug__:
                result.total_result.ie_message = "\n".join(
                    traceback.format_exception(e)
                )
                result.total_result.message_type = MessageType.TEXT

            self.reporter({"chal_id": chal_id, "task": "summary", "result": result})
            return

        chal.reporter = self.reporter
        push_challenge(chal)

    def on_close(self):
        utils.logger.info(
            f"Backend disconnected close_code: {self.close_code} close_reason: {self.close_reason}"
        )

    def check_origin(self, _: str) -> bool:
        return True


def init_socket_server():
    app = tornado.web.Application(
        [
            (r"/judge", JudgeWebSocketClient),
        ]
    )
    app.listen(2503)
    return app


def sig_handler(sig, _):
    def stop_loop(deadline):
        now = time.time()
        if now < deadline and ioloop.time:
            print("Waiting for next tick")
            ioloop.add_timeout(now + 1, stop_loop, deadline)
        else:
            ioloop.add_callback(ioloop.stop)

            print("Shutdown finally")

    def shutdown():
        global server_running
        server_running = False
        threading_pool.close()
        print("Stopping judge server")
        print(f"Will shutdown in {0} seconds ...")
        stop_loop(time.time() + 0)

    print(f"Caught signal: {sig}")
    ioloop.add_callback_from_signal(shutdown)


def main():
    utils.logger.info("Judge Start")
    executor_server.init()
    err = executor_server.init_container(
        {"cinitPath": "./cinit", "cgroupPrefix": "ntoj-judge-rewrite"}
    )
    if err:
        utils.logger.error("Failed to init container")
        return

    init_langs()
    app = init_socket_server()

    # TODO: handle signal Ctrl+C (SIGINT, SIGTERM, SIGQUIT)
    # signal.signal(signal.SIGINT, functools.partial(sig_handler))
    # signal.signal(signal.SIGTERM, functools.partial(sig_handler))
    # signal.signal(signal.SIGQUIT, functools.partial(sig_handler))

    l1 = threading.Thread(target=task_loop, args=())
    l2 = threading.Thread(target=finish_task_loop)

    l1.start()
    l2.start()
    ioloop.start()


if __name__ == "__main__":
    main()
