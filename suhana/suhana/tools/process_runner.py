import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


WORKER_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
WORKER_CPU_LIMIT_SECONDS = 25
_POLL_INTERVAL_SECONDS = 0.25


class ProcessLimitError(RuntimeError):
    pass


class ProcessTimeoutError(RuntimeError):
    pass


class ProcessCancelledError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int
    pid: int


def _apply_posix_limits():
    import resource

    resource.setrlimit(
        resource.RLIMIT_CPU,
        (WORKER_CPU_LIMIT_SECONDS, WORKER_CPU_LIMIT_SECONDS),
    )
    resource.setrlimit(
        resource.RLIMIT_AS,
        (WORKER_MEMORY_LIMIT_BYTES, WORKER_MEMORY_LIMIT_BYTES),
    )


def _run_posix(command, cwd, timeout_seconds, cancel_check):
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        text=True,
        preexec_fn=_apply_posix_limits,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise ProcessTimeoutError
            try:
                stdout, stderr = process.communicate(
                    timeout=min(_POLL_INTERVAL_SECONDS, remaining)
                )
                return ProcessResult(stdout, stderr, process.returncode, process.pid)
            except subprocess.TimeoutExpired:
                if cancel_check is not None and cancel_check():
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                    raise ProcessCancelledError
    except Exception:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise


def _run_windows(command, cwd, timeout_seconds, cancel_check):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class StartupInfo(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class ProcessInformation(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    kernel.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(StartupInfo),
        ctypes.POINTER(ProcessInformation),
    ]

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ProcessLimitError("Windows could not create a processing resource-limit job.")

    info = ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = (
        0x00000002  # JOB_OBJECT_LIMIT_PROCESS_TIME
        | 0x00000008  # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | 0x00000200  # JOB_OBJECT_LIMIT_JOB_MEMORY
        | 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    info.BasicLimitInformation.PerProcessUserTimeLimit = WORKER_CPU_LIMIT_SECONDS * 10_000_000
    info.BasicLimitInformation.ActiveProcessLimit = 1
    info.ProcessMemoryLimit = WORKER_MEMORY_LIMIT_BYTES
    info.JobMemoryLimit = WORKER_MEMORY_LIMIT_BYTES
    if not kernel.SetInformationJobObject(
        job,
        9,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        kernel.CloseHandle(job)
        raise ProcessLimitError("Windows could not set processing resource limits.")

    with tempfile.TemporaryDirectory(prefix="suhana-process-") as directory:
        stdout_path = Path(directory) / "stdout"
        stderr_path = Path(directory) / "stderr"
        with (
            open(os.devnull, "rb") as stdin_file,
            open(stdout_path, "wb") as stdout_file,
            open(stderr_path, "wb") as stderr_file,
        ):
            handles = [
                msvcrt.get_osfhandle(stdin_file.fileno()),
                msvcrt.get_osfhandle(stdout_file.fileno()),
                msvcrt.get_osfhandle(stderr_file.fileno()),
            ]
            for handle in handles:
                if not kernel.SetHandleInformation(handle, 1, 1):
                    kernel.CloseHandle(job)
                    raise ProcessLimitError("Windows could not configure isolated worker streams.")

            startup = StartupInfo()
            startup.cb = ctypes.sizeof(StartupInfo)
            startup.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            process_info = ProcessInformation()
            command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
            created = kernel.CreateProcessW(
                command[0],
                command_line,
                None,
                None,
                True,
                0x00000004 | 0x08000000,  # CREATE_SUSPENDED | CREATE_NO_WINDOW
                None,
                str(cwd),
                ctypes.byref(startup),
                ctypes.byref(process_info),
            )
            for handle in handles:
                kernel.SetHandleInformation(handle, 1, 0)
            if not created:
                kernel.CloseHandle(job)
                raise ProcessLimitError("Windows could not start the isolated processing worker.")

            process_handle = process_info.hProcess
            thread_handle = process_info.hThread
            pid = process_info.dwProcessId
            try:
                if not kernel.AssignProcessToJobObject(job, process_handle):
                    kernel.TerminateProcess(process_handle, 1)
                    raise ProcessLimitError("Windows could not apply worker resource limits.")
                if kernel.ResumeThread(thread_handle) == 0xFFFFFFFF:
                    kernel.TerminateJobObject(job, 1)
                    raise ProcessLimitError("Windows could not resume the isolated worker.")

                deadline = time.monotonic() + timeout_seconds
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        kernel.TerminateJobObject(job, 1)
                        kernel.WaitForSingleObject(process_handle, 5_000)
                        raise ProcessTimeoutError
                    wait_ms = min(_POLL_INTERVAL_SECONDS, remaining) * 1000
                    wait_result = kernel.WaitForSingleObject(
                        process_handle,
                        max(1, int(wait_ms)),
                    )
                    if wait_result == 0:
                        break
                    if wait_result != 258:
                        kernel.TerminateJobObject(job, 1)
                        raise ProcessLimitError("Windows failed while waiting for the processing worker.")
                    if cancel_check is not None and cancel_check():
                        kernel.TerminateJobObject(job, 1)
                        kernel.WaitForSingleObject(process_handle, 5_000)
                        raise ProcessCancelledError

                exit_code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
                    raise ProcessLimitError("Windows could not read the processing worker exit code.")
                stdout_file.flush()
                stderr_file.flush()
            finally:
                kernel.CloseHandle(thread_handle)
                kernel.CloseHandle(process_handle)
                kernel.CloseHandle(job)

        stdout = stdout_path.read_bytes().decode("utf-8", errors="replace")
        stderr = stderr_path.read_bytes().decode("utf-8", errors="replace")
        return ProcessResult(stdout, stderr, int(exit_code.value), pid)


def run_limited_process(command, cwd, timeout_seconds, cancel_check=None):
    if os.name == "nt":
        return _run_windows(command, cwd, timeout_seconds, cancel_check)
    if os.name == "posix":
        return _run_posix(command, cwd, timeout_seconds, cancel_check)
    raise ProcessLimitError("OS-enforced worker resource limits are unsupported on this platform.")
