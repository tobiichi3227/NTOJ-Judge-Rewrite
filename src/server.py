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

from utils.challenge_builder import parse_base_challenge_info, parse_testdatas_and_subtasks

import importlib
import pkgutil
import problem
for _, modname, ispkg in pkgutil.iter_modules(problem.__path__, problem.__name__ + "."):
    importlib.import_module(modname)

import tornado.ioloop
import tornado.web
import tornado.websocket

import config
import executor_server
import utils
from models import *
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

        if chal.problem_context.userprog_id:
            executor_server.file_delete(chal.problem_context.userprog_id)
        if chal.problem_context.checker_id:
            executor_server.file_delete(chal.problem_context.checker_id)
        if chal.problem_context.summary_id:
            executor_server.file_delete(chal.problem_context.summary_id)
        for t in chal.testdatas.values():
            if t.useroutput_id:
                executor_server.file_delete(t.useroutput_id)

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
    problem_type = obj.get("problem_type", "batch")
    base_info = parse_base_challenge_info(obj)
    chal = Challenge(**base_info)
    context_class = get_context_class(problem_type)
    context = context_class.from_json(obj, chal)
    chal.problem_context = context
    chal.testdatas, chal.subtasks = parse_testdatas_and_subtasks(obj, chal, context)

    chal.result = Result(chal_id=chal.chal_id)
    for testdata_id in chal.testdatas:
        chal.result.testdata_results[testdata_id] = TestDataResult(id=testdata_id)
    for subtask_id in chal.subtasks:
        chal.result.subtask_results[subtask_id] = SubtaskResult()

    tasks = context.build_task_dag(chal)

    return chal, tasks

def push_tasks(tasks: list[TaskEntry]):
    for task in tasks:
        add_task(task)

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
            chal, tasks = build_challenge(obj)
        except Exception as e:
            import traceback

            # TODO: 有可能連 chal_id 都不知道，這個只有 backend 知道而已
            chal_id = 1110
            result = Result(chal_id)
            result.total_result.status = Status.InternalError
            result.total_result.memory = 0
            result.total_result.time = 0
            result.total_result.score = decimal.Decimal()
            print(traceback.format_exception(e))
            if __debug__:
                result.total_result.ie_message = "\n".join(
                    traceback.format_exception(e)
                )
                result.total_result.message_type = MessageType.TEXT

            self.reporter({"chal_id": chal_id, "task": "summary", "result": result})
            return

        chal.reporter = self.reporter
        challenge_list[chal.internal_id] = chal
        push_tasks(tasks)

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
    app.listen(2502)
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
    init_params = {"cinitPath": "./cinit", "cgroupPrefix": "ntoj-judge-rewrite"}
    if config.CPUSET:
        init_params["cpuset"] = config.CPUSET

    if config.CPU_RATE:
        init_params["enableCpuRate"] = True
    err = executor_server.init_container(init_params)
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
