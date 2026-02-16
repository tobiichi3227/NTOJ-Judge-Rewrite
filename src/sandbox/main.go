package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"time"

	"github.com/tobiichi3227/go-sandbox/pkg/cgroup"
	"github.com/tobiichi3227/go-sandbox/pkg/seccomp"
	// "github.com/tobiichi3227/go-sandbox/pkg/memfd"
	"github.com/tobiichi3227/go-sandbox/pkg/mount"
	"github.com/tobiichi3227/go-sandbox/pkg/rlimit"
	"github.com/tobiichi3227/go-sandbox/pkg/seccomp/libseccomp"
	"github.com/tobiichi3227/go-sandbox/runner"
	"github.com/tobiichi3227/go-sandbox/runner/unshare"
)

// default allowed safe syscalls
var (
	defaultSyscallAllows = []string{
		// file access through fd
		"read",
		"write",
		"readv",
		"writev",
		"close",
		"fstat",
		"lseek",
		"dup",
		"dup3",
		"ioctl",
		"fcntl",
		"fadvise64",
		"pread64",
		"pwrite64",

		// memory action
		"mmap",
		"mprotect",
		"munmap",
		"brk",
		"mremap",
		"msync",
		"mincore",
		"madvise",

		// signal action
		"rt_sigaction",
		"rt_sigprocmask",
		"rt_sigreturn",
		"rt_sigpending",
		"sigaltstack",

		// get current work dir
		"getcwd",

		// process exit
		"exit",
		"exit_group",

		// others
		"gettimeofday",
		"getrlimit",
		"getrusage",
		"times",
		"clock_gettime",

		"restart_syscall",

		// execute file
		"execve",
		"execveat",

		// file open
		"openat",

		// file delete
		"unlinkat",

		// soft link
		"readlinkat",

		// permission check
		"faccessat",

		// arch syscall allow
		"dup2",
		"time",
		"arch_prctl",

		// arch syscall trace
		"open",
		"unlink",
		"readlink",
		"lstat",
		"stat",
		"access",
		"newfstatat",

		"set_tid_address",
		"set_robust_list",
		"rseq",
	}

	// process related syscall if allowProc enabled
	defaultProcSyscalls = []string{"clone", "fork", "vfork", "nanosleep", "execve"}

	// MaskPaths defines paths to be masked to avoid reading information from
	// outside of the container
	defaultMaskPaths = []string{
		"/sys/firmware",
		"/sys/devices/virtual/powercap",
		"/proc/acpi",
		"/proc/asound",
		"/proc/kcore",
		"/proc/keys",
		"/proc/latency_stats",
		"/proc/timer_list",
		"/proc/timer_stats",
		"/proc/sched_debug",
		"/proc/scsi",
		"/usr/lib/wsl/drivers",
		"/usr/lib/wsl/lib",
	}

	defaultEnv = []string{"PATH=/usr/local/bin:/usr/bin:/bin"}
)

var (
	addBindPath, addMaskPath, addAllowSyscall, addKillSyscall, addEnv                                                 arrayFlags
	stdinFile, stdoutFile, stderrFile, workPath, cpuSet                                                               string
	timeLimit, realTimeLimit, memoryLimit, vssMemoryLimit, outputLimit, openFileLimit, stackLimit, procLimit, cpuRate uint64

	allowMountProc, allowMountProcRW, allowProc, redirOutputToNull, enableSeccomp, showDetails bool
	args                                                                     []string
	// stdinFd, stdoutFd, stderrFd                                                                                       uint64
)

func printUsage() {
	fmt.Fprintf(flag.CommandLine.Output(), "Usage: %s [options] <args>\n", os.Args[0])
	flag.PrintDefaults()
	os.Exit(2)
}

func main() {
	flag.Usage = printUsage
	flag.Var(&addBindPath, "add-bind-path", "add bind-mount path")
	flag.Var(&addMaskPath, "add-mask-path", "mask mounted paths with empty / null mount")
	flag.Var(&addAllowSyscall, "add-allow-syscall", "add allow syscall")
	flag.Var(&addKillSyscall, "add-kill-syscall", "add kill syscall (it will overwrite allow syscall)")
	flag.Var(&addEnv, "add-env", "add environment variable")
	flag.StringVar(&stdinFile, "stdin", "", "Set stdin file name")
	flag.StringVar(&stdoutFile, "stdout", "", "Set stdout file name")
	flag.StringVar(&stderrFile, "stderr", "", "Set stderr file name")
	// flag.StringVar(&stdinFd, "stdin-fd", "", "Set stdin file descriptor")
	// flag.StringVar(&stdoutFd, "stdout-fd", "", "Set stdout file descriptor")
	// flag.StringVar(&stderrFd, "stderr-fd", "", "Set stderr file descriptor")
	flag.StringVar(&cpuSet, "cpuset", "", "Set cpu set")
	flag.StringVar(&workPath, "workpath", "", "Set the work path of the program")
	flag.BoolVar(&allowProc, "allow-proc", false, "Allow fork, exec... etc.")
	flag.BoolVar(&allowMountProc, "allow-mount-proc", false, "Allow mount readonly /proc, this is for java")
	flag.BoolVar(&allowMountProcRW, "allow-mount-proc-rw", false, "Allow mount /proc with read/write")
	flag.BoolVar(&redirOutputToNull, "redir-output-to-null", false, "Redir empty stdout and stderr to /dev/null")
	flag.BoolVar(&enableSeccomp, "seccomp", false, "Enable seccomp")
	flag.BoolVar(&showDetails, "show-trace-details", false, "Show trace details")
	flag.Uint64Var(&timeLimit, "time-limit", 1000, "Set time limit (in millisecond)")
	flag.Uint64Var(&realTimeLimit, "realtime-limit", 0, "Set real time limit (in millisecond)")
	flag.Uint64Var(&memoryLimit, "memory-limit", 262144, "Set memory limit (in kib)")
	flag.Uint64Var(&outputLimit, "output-limit", 262144, "Set output limit (in kib)")
	flag.Uint64Var(&openFileLimit, "open-file-limit", 256, "Set open file times limit")
	flag.Uint64Var(&vssMemoryLimit, "vss-memory-limit", 0, "Set vss memory limit (in kib)")
	flag.Uint64Var(&stackLimit, "stack-limit", 16384, "Set stack limit (in kib)")
	flag.Uint64Var(&procLimit, "proc-limit", 1, "Set proc count limit")
	flag.Uint64Var(&cpuRate, "cpu-rate", 1000, "Set cpu rate") // TODO: maybe cfs quota
	flag.Parse()
	args = flag.Args()
	if len(args) == 0 {
		printUsage()
	}

	if workPath == "" {
		panic("workPath must be set")
	}
	if realTimeLimit < timeLimit {
		// realTimeLimit = timeLimit + 2000
		realTimeLimit = timeLimit
	}
	if stackLimit > memoryLimit {
		stackLimit = memoryLimit
	}
	if redirOutputToNull {
		if stderrFile == "" {
			stderrFile = "/dev/null"
		}

		if stdoutFile == "" {
			stdoutFile = "/dev/null"
		}
	}

	rt, err := start()
	if rt == nil {
		rt = &runner.Result{
			Status: runner.StatusRunnerError,
			Error: err.Error(),
		}
	}

	b, err := json.Marshal(struct {
		Status     int    `json:"status"`
		ExitStatus int    `json:"exitStatus"`
		Error      string `json:"error"`
		Time       uint64 `json:"time"`
		RunTime    uint64 `json:"runTime"`
		Memory     uint64 `json:"memory"`
		ProcPeak   uint64 `json:"procPeak"`
	}{
		Status:     int(rt.Status),
		ExitStatus: rt.ExitStatus,
		Error:      rt.Error,
		Time:       uint64(rt.Time),
		RunTime:    uint64(rt.RunningTime),
		Memory:     rt.Memory.Byte(),
		ProcPeak:   rt.ProcPeak,
	})
	if err != nil {
		fmt.Fprintf(os.Stdout, "failed to output result: %v", err)
	}
	fmt.Fprintf(os.Stdout, "%v", string(b))
}

type ss string

func (s *ss) Scan(state fmt.ScanState, verb rune) error {
	tok, err := state.Token(true, func(r rune) bool {
        return r != ':'
    })
    if err != nil {
        return err
    }
    *s = ss(tok)
    return nil
}

func start() (*runner.Result, error) {
	defaultEnv = append(defaultEnv, addEnv...)
	mb := mount.NewDefaultBuilder().
		WithBind("/etc/alternatives", "etc/alternatives", true).
		WithBind("/dev/null", "dev/null", false).
		WithBind(workPath, "work", false).
		WithTmpfs("tmp", "size=8m,nr_inodes=4k").
		FilterNotExist()

	if allowMountProc {
		mb.WithProc()
	} else if allowMountProcRW {
		mb.WithProcRW(true)
	}

	for _, path := range addBindPath {
		var src, dst, readonly string
		fmt.Sscanf(path, "%s:%s:%s", (*ss)(&src), (*ss)(&dst), (*ss)(&readonly))
		mb.WithBind(src, dst, readonly != "false")
	}

	mt, err := mb.FilterNotExist().Build()
	if err != nil {
		return nil, err
	}

	defaultMaskPaths = append(defaultMaskPaths, addMaskPath...)

	root, err := os.MkdirTemp("", "ns")
	if err != nil {
		return nil, fmt.Errorf("cannot make temp root for new namespace")
	}
	defer os.RemoveAll(root)

	t := cgroup.DetectType()
	if t == cgroup.TypeV2 {
		cgroup.EnableV2Nesting()
	}
	ct, err := cgroup.GetAvailableController()
	if err != nil {
		log.Fatalln(err)
	}
	b, err := cgroup.New("ntoj-judge-sandbox", ct)
	if err != nil {
		return nil, err
	}
	cg, err := b.Random("ntoj-judge-sandbox")
	if err != nil {
		return nil, err
	}
	defer cg.Destroy()
	cgDir, err := cg.Open()
	if err != nil {
		return nil, err
	}
	defer cgDir.Close()
	cgroupFd := cgDir.Fd()

	syncFunc := func(pid int) error {
		if err := cg.AddProc(pid); err != nil {
			return err
		}
		return nil
	}

	var filter seccomp.Filter
	if enableSeccomp {
		syscallType := make(map[string]int, len(defaultSyscallAllows)+len(addAllowSyscall)+len(addKillSyscall))
		if allowProc {
			defaultSyscallAllows = append(defaultSyscallAllows, defaultProcSyscalls...)
		}
		for _, syscall := range defaultSyscallAllows {
			syscallType[syscall] = int(libseccomp.ActionAllow)
		}
		for _, syscall := range addAllowSyscall {
			syscallType[syscall] = int(libseccomp.ActionAllow)
		}
		for _, syscall := range addKillSyscall {
			syscallType[syscall] = int(libseccomp.ActionKill)
		}

		allowSys := make([]string, 0, len(syscallType))
		killSys := make([]string, 0, len(addKillSyscall))
		for s, t := range syscallType {
			if t == int(libseccomp.ActionAllow) {
				allowSys = append(allowSys, s)
			} else if t == int(libseccomp.ActionKill) {
				killSys = append(killSys, s)
			}
		}
		if len(killSys) == 0 {
			killSys = nil
		}

		secb := libseccomp.Builder{
			Allow:   allowSys,
			Kill:    killSys,
			Default: libseccomp.ActionKill,
		}
		filter, err = secb.Build()
		if err != nil {
			return nil, fmt.Errorf("failed to create seccomp filter: %w", err)
		}
	} else {
		secb := libseccomp.Builder{
			Allow:   []string{},
			Kill:    []string{},
			Default: libseccomp.ActionAllow,
		}
		filter, err = secb.Build()
		if err != nil {
			return nil, fmt.Errorf("failed to create seccomp filter: %w", err)
		}
	}

	// open input / output / err files
	files, err := prepareFiles(stdinFile, stdoutFile, stderrFile)
	if err != nil {
		return nil, fmt.Errorf("failed to prepare files: %w", err)
	}
	defer closeFiles(files)
	// if not defined, then use the original value
	fds := make([]uintptr, len(files))
	for i, f := range files {
		if f != nil {
			fds[i] = f.Fd()
		} else {
			fds[i] = uintptr(i)
		}
	}

	// var execFile uintptr
	// {
	// 	fin, err := os.Open(args[0])
	// 	fmt.Println(args[0])
	// 	if err != nil {
	// 		return nil, fmt.Errorf("failed to open args[0]: %w", err)
	// 	}
	// 	execf, err := memfd.DupToMemfd("run_program", fin)
	// 	if err != nil {
	// 		return nil, fmt.Errorf("dup to memfd failed: %w", err)
	// 	}
	// 	fin.Close()
	// 	defer execf.Close()
	// 	execFile = execf.Fd()
	// }

	if err = cg.SetMemoryLimit(memoryLimit << 10); err != nil {
		return nil, err
	}
	if err = cg.SetProcLimit(procLimit); err != nil {
		return nil, err
	}
	if cpuSet != "" {
		if err = cg.SetCPUSet([]byte(cpuSet)); err != nil {
			return nil, err
		}
	}
	// TODO: Set cpurate
	rlims := rlimit.RLimits{
		CPU:         uint64(time.Duration(timeLimit*uint64(time.Millisecond)).Truncate(time.Second)/time.Second) + 1,
		CPUHard:     realTimeLimit / 1000,
		FileSize:    outputLimit << 10,
		Stack:       stackLimit << 10,
		Data:        memoryLimit << 10,
		OpenFile:    openFileLimit,
		DisableCore: true,
	}
	if vssMemoryLimit > 0 {
		rlims.AddressSpace = vssMemoryLimit << 10
	}
	limit := runner.Limit{
		TimeLimit:   time.Duration(timeLimit) * time.Millisecond,
		MemoryLimit: runner.Size(memoryLimit << 10),
	}

	r := &unshare.Runner{
		Args: args,
		Env:  defaultEnv,
		// ExecFile:    execFile,
		WorkDir:     "/work",
		Files:       fds,
		RLimits:     rlims.PrepareRLimit(),
		Limit:       limit,
		Seccomp:     filter,
		Root:        root,
		Mounts:      mt,
		ShowDetails: showDetails,
		MaskPaths:   defaultMaskPaths,
		SyncFunc:    syncFunc,
		CgroupFD:    cgroupFd,
		HostName:    "ntoj-judge-sandbox",
		DomainName:  "ntoj-judge-sandbox",
	}

	var rt runner.Result
	// gracefully shutdown
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)

	// Run tracer
	sTime := time.Now()
	c, cancel := context.WithTimeout(context.Background(), time.Duration(int64(realTimeLimit)*int64(time.Millisecond)))
	defer cancel()

	s := make(chan runner.Result, 1)
	go func() {
		s <- r.Run(c)
	}()
	rTime := time.Now()

	select {
	case <-sig:
		cancel()
		rt = <-s
		rt.Status = runner.StatusRunnerError

	case rt = <-s:
	}
	eTime := time.Now()

	if rt.SetUpTime == 0 {
		rt.SetUpTime = rTime.Sub(sTime)
		rt.RunningTime = eTime.Sub(rTime)
	}

	cpu, err := cg.CPUUsage()
	if err != nil {
		return nil, fmt.Errorf("cgroup cpu: %v", err)
	} else {
		rt.Time = time.Duration(cpu)
	}
	// max memory usage may not exist in cgroup v2
	memory, err := cg.MemoryMaxUsage()
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, fmt.Errorf("cgroup memory: %v", err)
	} else if err == nil {
		rt.Memory = runner.Size(memory)
	}
	procPeak, err := cg.ProcessPeak()
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, fmt.Errorf("cgroup pid: %v", err)
	} else if err == nil {
		rt.ProcPeak = procPeak
	}
	if rt.Status == runner.StatusTimeLimitExceeded || rt.Status == runner.StatusNormal {
		if rt.Time >= limit.TimeLimit {
			rt.Status = runner.StatusTimeLimitExceeded
		} else {
			rt.Status = runner.StatusNormal
		}
	}
	if rt.Status == runner.StatusMemoryLimitExceeded || rt.Status == runner.StatusNormal {
		if rt.Memory >= limit.MemoryLimit {
			rt.Status = runner.StatusMemoryLimitExceeded
		} else {
			rt.Status = runner.StatusNormal
		}
	}

	if rt.Status == runner.StatusNormal && rt.ExitStatus != 0 && rt.RunningTime > time.Duration(realTimeLimit) {
		rt.Status = runner.StatusTimeLimitExceeded
	}

	// Fix TLE due to context cancel, from go-judge
	if rt.Status == runner.StatusNormal && rt.ExitStatus != 0 &&
		rt.Time < time.Duration(timeLimit) && rt.RunningTime < time.Duration(realTimeLimit) {
		rt.Status = runner.StatusSignalled
	}
	return &rt, nil
}
