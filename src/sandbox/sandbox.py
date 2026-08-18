import os
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from collections.abc import Callable
import select
import json
import threading
import time
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


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    results: list[SandboxResult]
    cancelled_by: int | None = None
    cancel_requested_indices: frozenset[int] = frozenset()


@dataclass(slots=True)
class SandboxParams:
    exe_path: str = ""
    args: list[str] = field(default_factory=list)
    workdir: str = ""  # 建議由 ChallengeBox 設定
    time_limit: int = 1000 # ms
    realtime_limit: int = 0 # ms
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

    def set_realtime_limit(self, realtime_limit: int):
        self.realtime_limit = realtime_limit
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
            "--realtime-limit", str(self.realtime_limit),
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
        self._cleanup_lock = threading.Lock()
        self._cleaned = False
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
        with self._cleanup_lock:
            if self._cleaned:
                return
            self._cleaned = True

        if os.path.isdir(self.fifo_folder):
            for fifo in os.listdir(self.fifo_folder):
                os.remove(os.path.join(self.fifo_folder, fifo))
        shutil.rmtree(self.root, ignore_errors=True)

    def __alloc_workdir(self, tag: str) -> str:
        assert tag, "Must provide a tag to alloc workdir"
        workdir = os.path.join(self.root, f"sandbox_{tag}")
        assert not os.path.exists(workdir), "Workdir already exists"
        os.makedirs(workdir)
        return workdir

    @staticmethod
    def __read_result(proc: subprocess.Popen) -> SandboxResult:
        assert proc.stdout
        stdout_data = proc.stdout.read().decode("utf-8").strip()
        proc.stdout.close()
        try:
            result_dict = json.loads(stdout_data)
            return SandboxResult.from_dict(result_dict)
        except Exception:
            utils.logger.error(f"Sandbox parse error: {stdout_data}")
            return SandboxResult(8, 0, "parse error", 0, 0, 0, 0)

    @staticmethod
    def __interrupt(proc: subprocess.Popen) -> bool:
        if proc.poll() is not None:
            return False
        try:
            # The Go runner handles SIGINT by cancelling the sandboxed process
            # and cleaning up its namespace and cgroup.
            proc.send_signal(signal.SIGINT)
            return True
        except ProcessLookupError:
            return False

    def __run_sandbox(
        self,
        params_list: list[SandboxParams],
        select_stop: Callable[[dict[int, SandboxResult]], int | None] | None,
    ) -> SandboxExecutionResult:
        if self._cleaned:
            raise RuntimeError("ChallengeBox already cleaned up")

        # TODO: copy out
        procs: list[tuple[subprocess.Popen, SandboxParams]] = []
        results: list[SandboxResult | None] = [None] * len(params_list)
        cancelled_by = None
        cancel_requested_indices: set[int] = set()
        try:
            # Popen is intentionally performed in list order. Communication
            # tasks put the manager first, followed by contestant processes.
            for params in params_list:
                params.workdir = self.__alloc_workdir(tag=str(uuid.uuid4()))
                proc = subprocess.Popen(
                    ["./sandbox/sandbox"] + params.to_flags(),
                    stdout=subprocess.PIPE,
                )
                if proc.stdin:
                    proc.stdin.close()
                procs.append((proc, params))

            remaining = set(range(len(procs)))
            while remaining:
                completed = []
                for index in remaining:
                    proc, _ = procs[index]
                    if proc.poll() is not None:
                        completed.append(index)

                if not completed:
                    time.sleep(0.01)
                    continue

                completed_results = {}
                for index in sorted(completed):
                    proc, _ = procs[index]
                    result = self.__read_result(proc)
                    results[index] = result
                    completed_results[index] = result
                    remaining.remove(index)

                # Select only after collecting the whole polling batch. This
                # lets callers define a deterministic priority without the
                # iteration order deciding which failure wins.
                if cancelled_by is None and select_stop is not None:
                    selected_index = select_stop(completed_results)
                    if selected_index is not None:
                        if selected_index not in completed_results:
                            raise ValueError(
                                "select_stop returned an index outside the "
                                "completed batch"
                            )
                        cancelled_by = selected_index
                        for other_index in remaining:
                            if self.__interrupt(procs[other_index][0]):
                                cancel_requested_indices.add(other_index)

            for index, (_, params) in enumerate(procs):
                assert results[index] is not None
                for fname in params.copy_out_cache_files:
                    src_path = os.path.join(params.workdir, fname)
                    dst_path = os.path.join(self.file_folder, fname)
                    if os.path.isfile(src_path):
                        os.rename(src_path, dst_path)
        except BaseException:
            for proc, _ in procs:
                self.__interrupt(proc)
            for proc, _ in procs:
                proc.wait()
            raise
        finally:
            for params in params_list:
                if params.workdir:
                    shutil.rmtree(params.workdir, ignore_errors=True)

        # Every slot is filled before returning, so preserving the original
        # indices is part of the API contract.
        complete_results = []
        for result in results:
            assert result is not None
            complete_results.append(result)
        return SandboxExecutionResult(
            results=complete_results,
            cancelled_by=cancelled_by,
            cancel_requested_indices=frozenset(cancel_requested_indices),
        )

    def run_sandbox(self, params_list: list[SandboxParams]) -> list[SandboxResult]:
        return self.__run_sandbox(params_list, None).results

    def run_sandbox_with_cancellation(
        self,
        params_list: list[SandboxParams],
        select_stop: Callable[[dict[int, SandboxResult]], int | None],
    ) -> SandboxExecutionResult:
        """Run sandboxes concurrently and interrupt peers when requested.

        ``select_stop`` receives all results found in one polling batch and
        returns the index that should trigger peer cancellation, or ``None``.
        Results retain the same indices as ``params_list``.
        """
        return self.__run_sandbox(params_list, select_stop)
