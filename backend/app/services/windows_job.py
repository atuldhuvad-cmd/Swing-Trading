"""Windows Job Object for the isolated PDF parser worker.

Each parser worker runs in its own Job Object with:
  JOB_OBJECT_LIMIT_ACTIVE_PROCESS       one process only (ActiveProcessLimit = 1)
  JOB_OBJECT_LIMIT_PROCESS_MEMORY       allocations beyond the limit fail (MemoryError)
  JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE    closing the job kills every process in it,
                                        including a venv launcher's child interpreter
  JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION  no error dialog can keep a worker alive
TerminateJobObject kills the whole worker process tree on timeout.

Only ctypes is used, so this module imports on any platform; it is used only on
Windows. ``kernel32`` can be injected for tests. Real Windows execution still
needs verification on Windows.
"""
from __future__ import annotations

import ctypes

JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_LIMIT_FLAGS = (JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_PROCESS_MEMORY
                   | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION)
ACTIVE_PROCESS_LIMIT = 1  # the worker only; it can never start another process
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
TERMINATED_EXIT_CODE = 1


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),   # LARGE_INTEGER
        ("PerJobUserTimeLimit", ctypes.c_int64),       # LARGE_INTEGER
        ("LimitFlags", ctypes.c_uint32),               # DWORD
        ("MinimumWorkingSetSize", ctypes.c_size_t),    # SIZE_T
        ("MaximumWorkingSetSize", ctypes.c_size_t),    # SIZE_T
        ("ActiveProcessLimit", ctypes.c_uint32),       # DWORD
        ("Affinity", ctypes.c_size_t),                 # ULONG_PTR
        ("PriorityClass", ctypes.c_uint32),            # DWORD
        ("SchedulingClass", ctypes.c_uint32),          # DWORD
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _load_kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    handle, bool_ = ctypes.c_void_p, ctypes.c_int
    k.CreateJobObjectW.argtypes, k.CreateJobObjectW.restype = [ctypes.c_void_p, ctypes.c_wchar_p], handle
    k.SetInformationJobObject.argtypes = [handle, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    k.SetInformationJobObject.restype = bool_
    k.QueryInformationJobObject.argtypes = [handle, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    k.QueryInformationJobObject.restype = bool_
    k.AssignProcessToJobObject.argtypes, k.AssignProcessToJobObject.restype = [handle, handle], bool_
    k.TerminateJobObject.argtypes, k.TerminateJobObject.restype = [handle, ctypes.c_uint32], bool_
    k.CloseHandle.argtypes, k.CloseHandle.restype = [handle], bool_
    return k


class WorkerJob:
    """One Job Object per parser worker. Always ``close()`` it (idempotent)."""

    def __init__(self, memory_limit_bytes: int, kernel32=None):
        self.handle = None
        self._k = kernel32 if kernel32 is not None else _load_kernel32()
        self.memory_limit = int(memory_limit_bytes)
        self.handle = self._k.CreateJobObjectW(None, None)
        if not self.handle:
            self.handle = None
            raise OSError("CreateJobObjectW failed")
        try:
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_LIMIT_FLAGS
            info.BasicLimitInformation.ActiveProcessLimit = ACTIVE_PROCESS_LIMIT
            info.ProcessMemoryLimit = self.memory_limit
            if not self._k.SetInformationJobObject(self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                                                   ctypes.byref(info), ctypes.sizeof(info)):
                raise OSError("SetInformationJobObject failed")
        except BaseException:
            self.close()  # never leak a partially configured job
            raise

    def assign(self, process_handle) -> None:
        if not self._k.AssignProcessToJobObject(self.handle, process_handle):
            raise OSError("AssignProcessToJobObject failed")

    def terminate(self) -> None:
        """Kill every process in the job (the whole worker tree)."""
        if self.handle:
            self._k.TerminateJobObject(self.handle, TERMINATED_EXIT_CODE)

    def peak_process_memory(self) -> int | None:
        if not self.handle:
            return None
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        if not self._k.QueryInformationJobObject(self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                                                 ctypes.byref(info), ctypes.sizeof(info), None):
            return None
        return int(info.PeakProcessMemoryUsed)

    def close(self) -> None:
        """Close the job; KILL_ON_JOB_CLOSE ends anything still running in it."""
        handle, self.handle = self.handle, None
        if handle:
            self._k.CloseHandle(handle)
