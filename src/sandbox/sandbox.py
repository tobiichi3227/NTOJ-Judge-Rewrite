import os
import shutil
import subprocess
from dataclasses import dataclass, field
import select
import json
import uuid

import utils


# From CMS
def wait_without_std(procs):
    """Wait for the conclusion of the processes in the list, avoiding
    starving for input and output.

    procs (list): a list of processes as returned by Popen.

    return (list): a list of return codes.

    """

    def get_to_consume():
        """Amongst stdout and stderr of list of processes, find the
        ones that are alive and not closed (i.e., that may still want
        to write to).

        return (list): a list of open streams.

        """
        to_consume = []
        for process in procs:
            if process.poll() is None:  # If the process is alive.
                if process.stdout and not process.stdout.closed:
                    to_consume.append(process.stdout)
                if process.stderr and not process.stderr.closed:
                    to_consume.append(process.stderr)
        return to_consume

    # Close stdin; just saying stdin=None isn't ok, because the
    # standard input would be obtained from the application stdin,
    # that could interfere with the child process behaviour
    for process in procs:
        if process.stdin:
            process.stdin.close()

    # Read stdout and stderr to the end without having to block
    # because of insufficient buffering (and without allocating too
    # much memory). Unix specific.
    to_consume = get_to_consume()
    while len(to_consume) > 0:
        to_read = select.select(to_consume, [], [], 1.0)[0]
        for file_ in to_read:
            print(file_.read(8 * 1024))
        to_consume = get_to_consume()

    return [process.wait() for process in procs]


@dataclass(slots=True)
class SandboxResult:
    status: int
    exit_status: int
    error: str
    time: int
    run_time: int
    memory: int
    proc_peak: int

    @staticmethod
    def from_dict(d: dict) -> "SandboxResult":
        return SandboxResult(
            status=d.get("status", 0),
            exit_status=d.get("exitStatus", 0),
            error=d.get("error", ""),
            time=d.get("time", 0),
            run_time=d.get("runTime", 0),
            memory=d.get("memory", 0),
            proc_peak=d.get("procPeak", 0),
        )


@dataclass(slots=True)
class SandboxParams:
    exe_path: str = ""
    args: list[str] = field(default_factory=list)
    workdir: str = ""  # 建議由 ChallengeBox 設定
    time_limit: int = 1000 # ms
    memory_limit: int = 262144 # kib
    stack_limit: int = 65536 # kib
    vss_memory_limit: int = 0 # kib
    proc_limit: int = 1 # count
    output_limit: int = 65536 # kib
    open_file_limit: int = 16 # count
    stdin: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    extra_env: list[str] = field(default_factory=list)
    allow_proc: bool = False
    allow_mount_proc: bool = False
    allow_mount_proc_rw: bool = False
    cpuset: str = ""
    bind_paths: list[tuple[str, str, bool]] = field(default_factory=list)  # (src, dst, readonly)
    bind_to_workdir_paths: list[tuple[str, str, bool]] = field(default_factory=list)  # (src, dst, readonly)
    copy_out_cache_files: list[str] = field(default_factory=list)  # list of filenames in workdir to copy out

    def set_exe(self, exe_path: str):
        self.exe_path = exe_path
        return self

    def set_args(self, args: list[str]):
        self.args = args
        return self

    def set_time_limit(self, time_limit: int):
        self.time_limit = time_limit
        return self

    def set_memory_limit(self, memory_limit: int):
        self.memory_limit = memory_limit
        return self

    def set_stack_limit(self, stack_limit: int):
        self.stack_limit = stack_limit
        return self

    def set_vss_memory_limit(self, vss_memory_limit: int):
        self.vss_memory_limit = vss_memory_limit
        return self

    def set_proc_limit(self, proc_limit: int):
        self.proc_limit = proc_limit
        return self

    def set_output_limit(self, output_limit: int):
        self.output_limit = output_limit
        return self

    def set_open_file_limit(self, open_file_limit: int):
        self.open_file_limit = open_file_limit
        return self

    def set_stdin(self, stdin: str):
        self.stdin = stdin
        return self

    def set_stdout(self, stdout: str):
        self.stdout = stdout
        return self

    def set_stderr(self, stderr: str):
        self.stderr = stderr
        return self

    def add_env(self, env: str):
        self.extra_env.append(env)
        return self

    def set_allow_proc(self, allow: bool):
        self.allow_proc = allow
        return self

    def set_allow_mount_proc(self, allow: bool):
        self.allow_mount_proc = allow
        return self

    def set_allow_mount_proc_rw(self, allow: bool):
        self.allow_mount_proc_rw = allow
        return self

    def add_bind_path(self, src: str, dst: str, readonly: bool = True):
        self.bind_paths.append((src, dst, readonly))
        return self

    def add_copy_in_path(self, src: str, dst: str, readonly: bool = True):
        self.bind_to_workdir_paths.append((src, dst, readonly))
        return self

    def set_cpuset(self, cpuset: str):
        self.cpuset = cpuset
        return self

    def set_copy_out_cache_files(self, files: list[str]):
        self.copy_out_cache_files = files
        return self

    def add_copy_out_cache_file(self, file: str):
        self.copy_out_cache_files.append(file)
        return self

    def to_flags(self) -> list[str]:
        flags = [
            "--workpath", self.workdir,
            "--time-limit", str(self.time_limit),
            "--memory-limit", str(self.memory_limit),
            "--stack-limit", str(self.stack_limit),
            "--proc-limit", str(self.proc_limit),
            "--output-limit", str(self.output_limit),
            "--open-file-limit", str(self.open_file_limit),
            "--vss-memory-limit", str(self.vss_memory_limit),
            "--redir-output-to-null",
        ]
        if __debug__:
            flags.append("--show-trace-details")
        if self.stdin:
            flags += ["--stdin", self.stdin]
        if self.stdout:
            flags += ["--stdout", self.stdout]
        if self.stderr:
            flags += ["--stderr", self.stderr]
        if self.allow_proc:
            flags += ["--allow-proc"]
        if self.allow_mount_proc:
            flags += ["--allow-mount-proc"]
        elif self.allow_mount_proc_rw:
            flags += ["--allow-mount-proc-rw"]
        if self.cpuset:
            flags += ["--cpuset", self.cpuset]
        for env in self.extra_env:
            flags += ["--add-env", env]
        for src, dst, readonly in self.bind_paths:
            flags += ["--add-bind-path", f"{src}:{dst}:{'true' if readonly else 'false'}"]
        for src, dst, readonly in self.bind_to_workdir_paths:
            flags += ["--add-bind-path", f"{src}:work/{dst}:{'true' if readonly else 'false'}"]
        flags += [self.exe_path] + self.args
        return flags


class ChallengeBox:
    def __init__(self, base_tmp_path: str, id: int):
        self.root = os.path.join(base_tmp_path, str(id))
        self.fifo_folder = os.path.join(self.root, "fifo")
        self.file_folder = os.path.join(self.root, "file")
        os.mkdir(self.root)
        os.mkdir(self.file_folder)
        os.mkdir(self.fifo_folder)

    def mkdir(self, path: str):
        os.mkdir(os.path.join(self.root, path))

    def mkfifo(self, name: str):
        os.mkfifo(os.path.join(self.fifo_folder, name))

    def gen_filepath(self, name: str) -> str:
        return os.path.join(self.file_folder, name)

    def gen_fifopath(self, name: str) -> str:
        return os.path.join(self.fifo_folder, name)

    def get_file(self, name: str) -> str | None:
        path = self.gen_filepath(name)
        if not os.path.exists(path):
            return None
        return path

    def get_fifo(self, name: str) -> str | None:
        path = self.gen_fifopath(name)
        if not os.path.exists(path):
            return None
        return path

    def delete_file(self, name: str):
        path = self.gen_filepath(name)
        if os.path.exists(path):
            os.remove(path)

    def delete_fifo(self, name: str):
        path = self.gen_fifopath(name)
        if os.path.exists(path):
            os.remove(path)

    def cleanup(self):
        for fifo in os.listdir(self.fifo_folder):
            os.remove(os.path.join(self.fifo_folder, fifo))
        shutil.rmtree(self.root)

    def __alloc_workdir(self, tag: str) -> str:
        assert tag, "Must provide a tag to alloc workdir"
        workdir = os.path.join(self.root, f"sandbox_{tag}")
        assert not os.path.exists(workdir), "Workdir already exists"
        os.makedirs(workdir)
        return workdir

    def run_sandbox(self, params_list: list[SandboxParams]) -> list[SandboxResult]:
        # TODO: copy out
        # TODO: wait multiple processes
        procs: list[tuple[subprocess.Popen, SandboxParams]] = []
        for params in params_list:
            params.workdir = self.__alloc_workdir(tag=str(uuid.uuid4()))
            proc = subprocess.Popen(
                ["./sandbox/sandbox"] + params.to_flags(),
                stdout=subprocess.PIPE,
            )
            if proc.stdin:
                proc.stdin.close()
            procs.append((proc, params))

        for proc in procs:
            proc[0].wait()

        results = []
        for proc, params in procs:
            stdout_data = proc.stdout.read().decode("utf-8").strip()
            try:
                result_dict = json.loads(stdout_data)
                result = SandboxResult.from_dict(result_dict)
            except Exception:
                utils.logger.error(f"Sandbox parse error: {stdout_data}")
                result = SandboxResult(8, 0, "parse error", 0, 0, 0, 0)
            results.append(result)
            for fname in params.copy_out_cache_files:
                src_path = os.path.join(params.workdir, fname)
                dst_path = os.path.join(self.file_folder, fname)
                if os.path.isfile(src_path):
                    os.rename(src_path, dst_path)
            shutil.rmtree(params.workdir, ignore_errors=True)
        return results
