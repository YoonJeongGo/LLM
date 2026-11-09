"""Small Windows child lifetime primitive; no model or speech imports."""
from __future__ import annotations
import os

class OwnedWindowsJob:
    """Terminate an owned child tree if its Python owner disappears.

    The non-inheritable job handle belongs to this worker; Windows closes it on
    abrupt process death too. The child waits for an ownership-ready file before
    entering model/COM work, so assignment failure cannot start unowned work.
    """
    def __init__(self, process):
        import ctypes
        from ctypes import wintypes
        if os.name != "nt" or not hasattr(process, "_handle"):
            raise RuntimeError("Windows owned process handle is required")
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = Extended()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def attach_handshaken_child(self, launcher, pid, created_at):
        """Capture a Windows venv redirector's real child before permitting work.

        A process created before its launcher joined this job is not inherited
        retroactively. Verify ancestry and creation time, open a stable handle,
        recheck the handle creation time, then assign that exact process.
        """
        import ctypes
        from ctypes import wintypes
        import psutil
        if launcher.poll() is not None:
            raise RuntimeError("Owned launcher exited before handshake")
        process = psutil.Process(int(pid))
        if abs(process.create_time()-float(created_at)) > .01:
            raise RuntimeError("Handshake process birth mismatch")
        if process.pid != launcher.pid and launcher.pid not in [p.pid for p in process.parents()]:
            raise RuntimeError("Handshake process is not an owned launcher descendant")
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        self.kernel.IsProcessInJob.restype = wintypes.BOOL
        handle = self.kernel.OpenProcess(0x1000 | 0x0100 | 0x0001, False, int(pid))
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.GetProcessTimes(handle, *[ctypes.byref(value) for value in times]):
                raise ctypes.WinError(ctypes.get_last_error())
            birth = ((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime) / 10_000_000 - 11644473600
            if abs(birth-float(created_at)) > .01 or launcher.poll() is not None:
                raise RuntimeError("Opened process handle does not match the live handshake owner")
            member = wintypes.BOOL()
            if not self.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(member)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not member.value and not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
            return {"pid": int(pid), "create_time": birth, "ancestry_verified": True, "job_assigned": True}
        finally:
            self.kernel.CloseHandle(handle)


