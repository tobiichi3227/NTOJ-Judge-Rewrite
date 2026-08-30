#!/bin/python3

from dataclasses import dataclass
import aiofiles
import asyncio
import enum
import json
import os

from tornado.websocket import websocket_connect
import tornado.template
import tornado.ioloop
import tornado.web


class Compiler(enum.IntEnum):
    GCC = 1
    CLANG = 2
    GPP = 3
    CLANGPP = 4
    RUST = 5
    PYTHON3 = 6
    JAVA = 7
    ASMC = 8
    ASMCPP = 9


@dataclass(slots=True, frozen=True)
class CompilerInfo:
    compiler: Compiler
    grader_name: str
    version_name: str
    short_name: str
    source_ext: str


COMPILER_INFOS: list[CompilerInfo] = [None] * (max(v for v in Compiler) + 1)
COMPILER_INFOS[Compiler.GCC] = CompilerInfo(
    Compiler.GCC, "c", "GCC 14.2.0 GNU11", "gcc", "c"
)
COMPILER_INFOS[Compiler.CLANG] = CompilerInfo(
    Compiler.CLANG, "c", "Clang 19.1.7 C11", "clang", "c"
)
COMPILER_INFOS[Compiler.GPP] = CompilerInfo(
    Compiler.GPP, "cpp", "G++ 14.2.0 GNU++17", "g++", "cpp"
)
COMPILER_INFOS[Compiler.CLANGPP] = CompilerInfo(
    Compiler.CLANGPP, "cpp", "Clang++ 19.1.7 C++17", "clang++", "cpp"
)
COMPILER_INFOS[Compiler.RUST] = CompilerInfo(
    Compiler.RUST, "rust", "Rustc 1.85", "rust", "rs"
)
COMPILER_INFOS[Compiler.PYTHON3] = CompilerInfo(
    Compiler.PYTHON3, "python", "CPython 3.13.5", "python3", "py"
)
COMPILER_INFOS[Compiler.JAVA] = CompilerInfo(
    Compiler.JAVA, "java", "OpenJDK 21.0.11", "java", "java"
)
COMPILER_INFOS[Compiler.ASMC] = CompilerInfo(
    Compiler.ASMC, "asm", "Gas x86_64 Linux 2.44 w/ libc", "asmc", "s"
)
COMPILER_INFOS[Compiler.ASMCPP] = CompilerInfo(
    Compiler.ASMCPP, "asm", "Gas x86_64 Linux 2.44 w/ libstdc++", "asmcpp", "s"
)


class ChalConst:
    STATE_AC = 1
    STATE_PC = 2
    STATE_WA = 3
    STATE_RE = 4
    STATE_RESIG = 5
    STATE_TLE = 6
    STATE_MLE = 7
    STATE_OLE = 8
    STATE_CE = 9
    STATE_CLE = 10
    STATE_ERR = 11
    STATE_JE = 12
    STATE_JUDGE = 100
    STATE_NOTSTARTED = 101
    STATE_SKIPPED = 102
    STATE_REJECTED = 103
    STATE_EXPIRED = 104

    STATE_STR = {
        STATE_AC: "AC",
        STATE_PC: "PC",
        STATE_WA: "WA",
        STATE_RE: "RE",
        STATE_RESIG: "RE(SIG)",
        STATE_TLE: "TLE",
        STATE_MLE: "MLE",
        STATE_CE: "CE",
        STATE_CLE: "CLE",
        STATE_OLE: "OLE",
        STATE_JE: "JE",
        STATE_ERR: "IE",
        STATE_JUDGE: "Challenging",
        STATE_NOTSTARTED: "Not Started",
        STATE_SKIPPED: "SP",
        STATE_REJECTED: "RJ",
        STATE_EXPIRED: "Expired",
    }

    STATE_LONG_STR = {
        STATE_AC: "Accepted",
        STATE_PC: "Partial Correct",
        STATE_WA: "Wrong Answer",
        STATE_RE: "Runtime Error",
        STATE_RESIG: "Runtime Error (Killed by signal)",
        STATE_TLE: "Time Limit Exceed",
        STATE_MLE: "Memory Limit Exceed",
        STATE_OLE: "Output Limit Exceed",
        STATE_CE: "Compile Error",
        STATE_CLE: "Compilation Limit Exceed",
        STATE_ERR: "Internal Error",
        STATE_JE: "Judge Error",
        STATE_JUDGE: "Challenging",
        STATE_NOTSTARTED: "Not Started",
        STATE_SKIPPED: "Skipped",
        STATE_REJECTED: "Rejected",
        STATE_EXPIRED: "Expired",
    }

    OLD_STR_2_COMPILER = {
        "g++": Compiler.GPP,
        "clang++": Compiler.CLANGPP,
        "gcc": Compiler.GCC,
        "clang": Compiler.CLANG,
        "rustc": Compiler.RUST,
        "python3": Compiler.PYTHON3,
        "java": Compiler.JAVA,
        "asmc": Compiler.ASMC,
        "asmcpp": Compiler.ASMCPP,
    }

    NORMAL_PRI = 0
    CONTEST_PRI = 1
    CONTEST_REJUDGE_PRI = 2
    NORMAL_REJUDGE_PRI = 3


class CheckerType(enum.IntEnum):
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
        return [cls.CMS_TPS_TESTLIB, cls.STD_TESTLIB, cls.IOREDIR, cls.TOJ]


class SummaryType(enum.IntEnum):
    GROUPMIN = 1
    OVERWRITE = 2
    CUSTOM = 3


@dataclass(slots=True)
class ChallengeResult:
    state: int = ChalConst.STATE_NOTSTARTED
    time: int = 0
    memory: int = 0
    message: str = ""


class Counter:
    def __init__(self, start: int = 0):
        self.count = start
        self.lock = asyncio.Lock()

    async def next(self):
        async with self.lock:
            ret = self.count
            self.count += 1
            return ret

    async def get(self):
        async with self.lock:
            return self.count


class ChallengeService:
    res_buffer_size = 128

    def __init__(self, judge_url: str, tmp_dir: str):
        self.tmp_dir = tmp_dir
        self.judge_url = judge_url
        self.chal_res_buffer = [None] * ChallengeService.res_buffer_size
        self.chal_id_gen = Counter()
        ChallengeService.inst = self

    async def start(self):
        await self.connect_judge()

    async def emit_chal(
        self, compiler: Compiler, code: str, input: str, output: str
    ) -> int:
        chal_id = await self.chal_id_gen.next()

        buffer_idx = chal_id & (ChallengeService.res_buffer_size - 1)
        self.chal_res_buffer[buffer_idx] = ChallengeResult(state=ChalConst.STATE_JUDGE)

        if chal_id >= ChallengeService.res_buffer_size:
            os.rmdir(
                os.path.join(
                    self.tmp_dir, str(chal_id - ChallengeService.res_buffer_size)
                )
            )

        chal_dir = os.path.join(self.tmp_dir, str(chal_id))
        os.makedirs(chal_dir, exist_ok=True)
        os.makedirs(os.path.join(chal_dir, "testdata"), exist_ok=True)

        code_path = os.path.join(
            chal_dir, f"code.{COMPILER_INFOS[compiler].source_ext}"
        )
        input_path = os.path.join(chal_dir, "testdata", "0.in")
        output_path = os.path.join(chal_dir, "testdata", "0.out")
        async with aiofiles.open(code_path, "w") as f:
            await f.write(code)
        async with aiofiles.open(input_path, "w") as f:
            await f.write(input)
        async with aiofiles.open(output_path, "w") as f:
            await f.write(output)

        data = {
            "acct_id": 1110,
            "pro_id": 1110,
            "contest_id": 0,
            "chal_id": chal_id,
            "res_path": chal_dir,
            "code_path": code_path,
            "userprog_compiler": compiler,
            "userprog_compiler_args": "",
            "checker_type": CheckerType.DIFF.value,
            "checker_compiler": None,
            "checker_compiler_args": None,
            "has_grader": False,
            "subtasks": [{"id": 0, "score": 100, "testdatas": [0]}],
            "limit": {
                "time": 1000 * 10**6,
                "memory": 256 * 1024 * 1024,
                "output": 1024 * 1024,  # 1 MiB
            },
            "testdatas": [{"id": 0, "input": "0.in", "output": "0.out"}],
            "priority": ChalConst.NORMAL_PRI,
            "skip_nonac": False,
        }
        await self.ws.write_message(json.dumps(data))

        return chal_id

    async def get_chal_res(self, chal_id: int) -> ChallengeResult | None:
        if chal_id < 0 or chal_id >= await self.chal_id_gen.get():
            return None

        buffer_idx = chal_id & (ChallengeService.res_buffer_size - 1)
        ret = self.chal_res_buffer[buffer_idx]

        if chal_id < await self.chal_id_gen.get() - ChallengeService.res_buffer_size:
            return None

        return ret

    async def connect_judge(self):
        self.ws = await websocket_connect(self.judge_url)

        while True:
            ret = await self.ws.read_message()
            if ret is None:
                break

            res = json.loads(ret)
            if res["task"] != "summary":
                continue
            total_result = res["result"]["total_result"]

            chal_id = res["chal_id"]
            buffer_idx = chal_id & (ChallengeService.res_buffer_size - 1)
            chal_res = self.chal_res_buffer[buffer_idx]

            if total_result["status"] in (ChalConst.STATE_CE, ChalConst.STATE_CLE):
                message = total_result["ce_message"]
                chal_res.message = message
            elif total_result["status"] in (ChalConst.STATE_ERR, ChalConst.STATE_JE):
                chal_res.message = total_result["ie_message"]

            chal_res.time = total_result["time"] // 10**6
            chal_res.memory = total_result["memory"] // 1024

            # This must be done after the above assignments, because the
            # front-end stops polling when the state is not
            # ChalConst.STATE_JUDGE.
            chal_res.state = total_result["status"]


class MainHandler(tornado.web.RequestHandler):
    def __init__(self, *args, **kwargs):
        self.tpldr = tornado.template.Loader("static/templ")

        super().__init__(*args, **kwargs)

    async def get(self):
        data = self.tpldr.load("index.html").generate()
        self.finish(data)

    async def post(self):
        code = self.get_argument("code")
        input = self.get_argument("input")
        answer = self.get_argument("answer")
        compiler = Compiler(int(self.get_argument("compiler")))
        chal_id = await ChallengeService.inst.emit_chal(compiler, code, input, answer)
        data = {"chal_id": chal_id}
        self.finish(json.dumps(data))


class ResultHandler(tornado.web.RequestHandler):
    async def get(self, chal_id):
        try:
            chal_id = int(chal_id)
        except (ValueError, TypeError):
            data = {
                "state": ChalConst.STATE_NOTSTARTED,
                "state_str": ChalConst.STATE_LONG_STR[ChalConst.STATE_NOTSTARTED],
                "time": "--",
                "memory": "--",
                "message": "",
            }
            self.finish(json.dumps(data))
            return

        chal_res = await ChallengeService.inst.get_chal_res(chal_id)
        if chal_res is None:
            data = {
                "state": ChalConst.STATE_EXPIRED,
                "state_str": ChalConst.STATE_LONG_STR[ChalConst.STATE_EXPIRED],
                "time": "--",
                "memory": "--",
                "message": "",
            }
            self.finish(json.dumps(data))
            return

        data = {
            "state": chal_res.state,
            "state_str": ChalConst.STATE_LONG_STR[chal_res.state],
            "time": chal_res.time,
            "memory": chal_res.memory,
            "message": chal_res.message,
        }
        self.finish(json.dumps(data))


if __name__ == "__main__":
    ChallengeService("ws://judge:2502/judge", "/tmp_dir")

    http_server = tornado.httpserver.HTTPServer(
        tornado.web.Application(
            [
                (r"/", MainHandler),
                (r"/result/(\d+)", ResultHandler),
            ]
        )
    )
    http_server.listen(8080)
    tornado.ioloop.IOLoop.current().run_sync(ChallengeService.inst.start)
    tornado.ioloop.IOLoop.current().start()
