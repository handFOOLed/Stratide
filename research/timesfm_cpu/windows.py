"""Development diagnostics only: Windows Job memory/tree limits, no network sandbox."""
import ctypes as c
from ctypes import wintypes as w
from model import MEMORY_MAX, require


class Basic(c.Structure):
    _fields_ = [("process_time",c.c_int64),("job_time",c.c_int64),("flags",w.DWORD),
                ("min_working_set",c.c_size_t),("max_working_set",c.c_size_t),("active",w.DWORD),
                ("affinity",c.c_size_t),("priority",w.DWORD),("scheduling",w.DWORD)]


class Io(c.Structure):
    _fields_ = [(k,c.c_uint64) for k in ("read_ops","write_ops","other_ops","read_bytes","write_bytes","other_bytes")]


class Limits(c.Structure):
    _fields_ = [("basic",Basic),("io",Io),("process_memory",c.c_size_t),("job_memory",c.c_size_t),
                ("peak_process",c.c_size_t),("peak_job",c.c_size_t)]


class Job:
    def __init__(self, process, memory_max=MEMORY_MAX):
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE,c.c_int,c.c_void_p,w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE,w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.QueryInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None,None)
        limits = Limits()
        limits.basic.flags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
        require(0 < memory_max <= MEMORY_MAX,"WINDOWS_MEMORY_BUDGET")
        limits.job_memory = memory_max
        ok = self.handle and self.kernel.SetInformationJobObject(self.handle,9,c.byref(limits),c.sizeof(limits))
        ok = ok and self.kernel.AssignProcessToJobObject(self.handle,w.HANDLE(int(process._handle)))
        if not ok:
            self.close()
        require(ok,"WINDOWS_JOB_LIMIT_UNAVAILABLE")
        self.memory_max=memory_max

    def snapshot(self):
        limits=Limits()
        class Accounting(c.Structure):
            _fields_=[(k,c.c_int64) for k in ("user","kernel","period_user","period_kernel")]+[(k,w.DWORD) for k in ("faults","total_processes","active_processes","terminated_processes")]
        accounting=Accounting()
        require(self.kernel.QueryInformationJobObject(self.handle,9,c.byref(limits),c.sizeof(limits),None)
                and self.kernel.QueryInformationJobObject(self.handle,1,c.byref(accounting),c.sizeof(accounting),None),"WINDOWS_JOB_METRICS_UNAVAILABLE")
        return dict(job_memory_peak_bytes=limits.peak_job,job_cpu_seconds=(accounting.user+accounting.kernel)/10000000,
                    job_total_processes=accounting.total_processes,job_memory_max_bytes=self.memory_max,resource_scope="WHOLE_WINDOWS_JOB")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def peak_rss():
    class Counters(c.Structure):
        _fields_ = [("cb",w.DWORD),("faults",w.DWORD)] + [(k,c.c_size_t) for k in
                   ("peak_working","working","peak_pagepool","pagepool","peak_nonpaged","nonpaged","pagefile","peak_pagefile")]
    counters = Counters()
    counters.cb = c.sizeof(counters)
    kernel = c.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = w.HANDLE
    psapi = c.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE,c.c_void_p,w.DWORD]
    require(psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),c.byref(counters),c.sizeof(counters)),"RSS_UNAVAILABLE")
    return counters.peak_working
