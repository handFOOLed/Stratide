"""One load, bounded batches, one strict JSON response; no runtime provisioning."""
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import Engine, MAX_INPUT, MAX_OUTPUT, MEMORY_MAX, Rejected, digest, loads, require, validate_request


def linux_limits():
    require(sys.platform == "linux", "LINUX_ISOLATION_REQUIRED")
    entry = next(x for x in Path("/proc/self/cgroup").read_text().splitlines() if x.startswith("0::"))
    cg = Path("/sys/fs/cgroup") / entry[3:].lstrip("/")
    cap = (cg / "memory.max").read_text().strip()
    swap = (cg / "memory.swap.max").read_text().strip()
    oom_group = (cg / "memory.oom.group").read_text().strip()
    require(cap.isdigit() and int(cap) <= MEMORY_MAX and swap == "0" and oom_group == "1", "MEMORY_CGROUP_REQUIRED")
    interfaces = {line.split(":")[0].strip() for line in Path("/proc/net/dev").read_text().splitlines() if ":" in line}
    require(interfaces <= {"lo"}, "PRIVATE_NETWORK_REQUIRED")
    return dict(mechanism="systemd-cgroup-v2+bubblewrap", memory_max_bytes=int(cap), memory_swap_max_bytes=0, memory_oom_group=True)


def cgroup_metrics():
    entry=next(x for x in Path("/proc/self/cgroup").read_text().splitlines() if x.startswith("0::"))
    cg=Path("/sys/fs/cgroup")/entry[3:].lstrip("/")
    cpu=dict(line.split() for line in (cg/"cpu.stat").read_text().splitlines())
    return dict(cgroup_memory_peak_bytes=int((cg/"memory.peak").read_text()),
                cgroup_cpu_seconds=int(cpu["usage_usec"])/1e6,resource_scope="WHOLE_WORKER_CGROUP")


def execute(v, directory, engine_factory=Engine):
    validate_request(v)
    wall, cpu = time.perf_counter(), time.process_time()
    # Discard library diagnostics; never forward exception text/paths/data.
    with open(os.devnull,"w") as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        model = engine_factory(directory, v)
        cold, timings = model.predict(v)
        first = digest(cold)
        for _ in range(v["repeats"] - 1):
            warm, batch_times = model.predict(v)
            require(digest(warm) == first, "NONDETERMINISTIC_FORECAST")
            timings.extend(batch_times)
    return dict(schema_version=1, request_sha256=digest(v), model_revision=model.manifest["revision"],
                weight_sha256=model.manifest["files"]["model.safetensors"],
                forecasts=cold, clamp_count=0, clamp_policy="REJECT_NEGATIVE_NO_CLAMP",
                metrics=dict(load_seconds=model.load_seconds, wall_seconds=time.perf_counter() - wall,
                             cpu_seconds=time.process_time() - cpu, batch_timings=timings, failures=0))



def read_request_line(fd):
    # Use raw FD reads: a daemon must never hold Python's buffered-stdin lock
    # during interpreter shutdown. Preserve any already-read heartbeat bytes.
    data=bytearray()
    while True:
        newline=data.find(b"\n")
        if newline >= 0:
            return bytes(data[:newline]),bytes(data[newline+1:])
        require(len(data) <= MAX_INPUT,"WORKER_INPUT_LIMIT")
        block=os.read(fd,min(65536,MAX_INPUT+1-len(data)))
        if not block:return bytes(data),b""
        data.extend(block)


def main():
    try:
        diagnostic = sys.argv[1:] == ["--development-cpu-diagnostic"]
        require(not sys.argv[1:] or diagnostic, "WORKER_ARGUMENTS")
        limits = dict(mechanism="UNISOLATED_DEVELOPMENT_DIAGNOSTIC", memory_max_bytes=None) if diagnostic else linux_limits()
        input_fd=sys.stdin.fileno()
        raw,pending=read_request_line(input_fd)
        require(len(raw) <= MAX_INPUT, "WORKER_INPUT_LIMIT")
        if not diagnostic:
            last = [time.monotonic()]
            def heartbeat():
                buffered=pending
                while True:
                    while b"\n" in buffered:
                        line,buffered=buffered.split(b"\n",1)
                        if line != b".":os._exit(3)
                        last[0] = time.monotonic()
                    if len(buffered)>1:os._exit(3)
                    block=os.read(input_fd,4096)
                    if not block:os._exit(3)
                    buffered+=block
            def watchdog():
                while time.monotonic() - last[0] < 5:
                    time.sleep(.5)
                os._exit(3)
            threading.Thread(target=heartbeat, daemon=True).start()
            threading.Thread(target=watchdog, daemon=True).start()
        if raw == b"probe":
            value = dict(isolation=limits)
        else:
            value = execute(loads(raw), os.environ.get("STRATIDE_TIMESFM_MODEL", "/model"))
            value["request_sha256"] = hashlib.sha256(raw).hexdigest()
            value["isolation"] = limits
        if sys.platform == "linux":
            import resource
            value.setdefault("metrics", {})["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            if not diagnostic:
                value["metrics"].update(cgroup_metrics())
        elif sys.platform == "win32":
            from windows import peak_rss
            value.setdefault("metrics", {})["peak_rss_bytes"] = peak_rss()
        encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        require(len(encoded) <= MAX_OUTPUT, "WORKER_OUTPUT_LIMIT")
        sys.stdout.buffer.write(encoded + b"\n")
        return 0
    except BaseException as e:
        code = str(e) if isinstance(e, Rejected) else ("WORKER_OOM" if isinstance(e,MemoryError) else "MODEL_RUNTIME_FAILED")
        sys.stdout.write(json.dumps(dict(error_code=code)) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
