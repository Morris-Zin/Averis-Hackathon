"""Private document process limits implementation."""

from __future__ import annotations

import os
import signal
import sys
from importlib import import_module
from typing import Protocol, cast


class _ResourceModule(Protocol):
    RLIMIT_AS: int
    RLIMIT_CPU: int

    def setrlimit(self, resource: int, limits: tuple[int, int]) -> None: ...


class _ChildProcess(Protocol):
    @property
    def pid(self) -> int | None: ...

    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...


def acquire_child_process_tree() -> int | None:
    """Put this worker and descendants in one OS-owned termination unit."""

    if sys.platform != "win32":
        os.setsid()
        return None

    import ctypes
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimitInformation(ctypes.Structure):
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

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_job = kernel32.CreateJobObjectW
    create_job.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    create_job.restype = wintypes.HANDLE
    set_information = kernel32.SetInformationJobObject
    set_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    set_information.restype = wintypes.BOOL
    assign_process = kernel32.AssignProcessToJobObject
    assign_process.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    assign_process.restype = wintypes.BOOL
    current_process = kernel32.GetCurrentProcess
    current_process.argtypes = []
    current_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    job = create_job(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    information = _ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = 0x00002000
    if not set_information(
        job, 9, ctypes.byref(information), ctypes.sizeof(information)
    ):
        error = ctypes.WinError(ctypes.get_last_error())
        close_handle(job)
        raise error
    if not assign_process(job, current_process()):
        error = ctypes.WinError(ctypes.get_last_error())
        close_handle(job)
        raise error
    return int(job)


def stop_process_tree(process: _ChildProcess) -> None:
    """Stop the worker and every subprocess that belongs to its ownership unit."""

    if sys.platform != "win32" and process.pid is not None:
        group_was_created = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            group_was_created = False
            # A timeout can win the race before the worker calls setsid().
            if process.is_alive():
                process.terminate()
        process.join(timeout=2)

        if group_was_created:
            # Descendants may ignore SIGTERM after the group leader has exited.
            # Always send SIGKILL to the group instead of gating it on the leader.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.is_alive():
            process.kill()
        process.join(timeout=2)
        return

    if process.is_alive():
        # The worker owns a kill-on-close Windows Job Object. Terminating it closes
        # that handle, and Windows terminates every process assigned to the job.
        process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)


def apply_child_resource_limits(cpu_seconds: int) -> None:
    """Add OS-enforced child limits on POSIX; Windows retains parent wall limits."""

    if sys.platform == "win32":
        return
    resources = cast(_ResourceModule, import_module("resource"))
    # ONNX maps model/workspace memory beyond its resident set. The multilingual
    # reader is measured separately inside a 1 GiB container; retain a finite
    # address-space ceiling rather than rejecting valid model allocations.
    memory_bytes = 1536 * 1024 * 1024
    resources.setrlimit(resources.RLIMIT_AS, (memory_bytes, memory_bytes))
    resources.setrlimit(resources.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
