"""Run on provisioned Linux, cgroup v2 + systemd user manager + bubblewrap.

Windows skips are NOT a Linux isolation PASS. Requires no market data.
"""
import sys
from pathlib import Path
import unittest
import subprocess
import json
import time
import secrets
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research/timesfm_cpu"))
import runtime
import cli
from model import Rejected

FACTS=[]


@unittest.skipUnless(sys.platform=="linux","Linux/WSL not available: NOT_RUN")
class LinuxIsolation(unittest.TestCase):
    def launch(self,kind="",memory=None,timeout=15):
        args=runtime.command(2)
        tag="STRATIDE_TIMESFM_RUN=acceptance"+str(__import__("os").getpid())
        args.insert(1,"--setenv="+tag)
        args.insert(1,"--setenv=STRATIDE_TEST_SECRET=SYNTHETIC_NOT_A_SECRET")
        args[-1]="/app/isolation_probe.py"
        if kind:args.append(kind)
        if kind == "memory":args.remove("--collect")  # Retain OOM metadata until the host assertion.
        if memory:
            args=["--property=MemoryMax="+str(memory) if a.startswith("--property=MemoryMax=") else a for a in args]
        def cleanup():
            try:
                if kind == "memory":
                    status=subprocess.run(["systemctl","--user","show",runtime.UNIT,
                        "--property=Result,ExecMainCode,ExecMainStatus,MemoryPeak,MemoryMax,MemorySwapMax,OOMPolicy"],capture_output=True,text=True)
                    self.last_unit=dict(line.split("=",1) for line in status.stdout.splitlines() if "=" in line)
                    FACTS.append(dict(test="oom",host_unit=self.last_unit))
            finally:
                runtime.stop_owned(tag)
                if kind == "memory":
                    current=subprocess.run(["systemctl","--user","show",runtime.UNIT,"--property=Environment","--value"],capture_output=True,text=True)
                    if tag in current.stdout.split():
                        subprocess.run(["systemctl","--user","reset-failed",runtime.UNIT],capture_output=True)
        with runtime.lock(cli.state_root()/"worker.lock"):
            return runtime.communicate_bounded(args,b"",cleanup=cleanup,timeout=timeout)

    def test_01_network_filesystem_environment_and_6gib(self):
        result=self.launch()
        self.assertTrue(all(result[k] for k in ("network_denied","model_readonly","home_hidden","secrets_absent")))
        self.assertEqual(result["isolation"]["memory_max_bytes"],6*1024**3)
        self.assertTrue(result["isolation"]["memory_oom_group"])
        FACTS.append(dict(test="network_filesystem_environment",result=result))
        with runtime.lock(cli.state_root()/"worker.lock"):
            normal=runtime.run(b"probe")
            self.assertEqual(runtime.stop()["state"],"STOPPED")
        self.assertTrue(normal["isolation"]["memory_oom_group"])
        FACTS.append(dict(test="production_probe_normal_exit",result=normal))

    def test_02_oom_kills_cgroup_and_next_start_works(self):
        with self.assertRaises(Rejected):self.launch("memory",128*1024**2)
        self.assertEqual(self.last_unit["Result"],"oom-kill")
        self.assertEqual(self.last_unit["ExecMainStatus"],"9")
        self.assertEqual(self.last_unit["MemoryMax"],str(128*1024**2))
        self.assertEqual(self.last_unit["MemorySwapMax"],"0")
        self.assertEqual(self.last_unit["OOMPolicy"],"kill")
        self.assertTrue(self.launch()["network_denied"])

    def test_03_timeout_crash_and_recovery(self):
        with self.assertRaisesRegex(Rejected,"WORKER_TIMEOUT"):self.launch("hang",timeout=.5)
        with self.assertRaises(Rejected):self.launch("crash")
        self.assertTrue(self.launch()["model_readonly"])

    def test_04_controller_death_reclaims_real_worker(self):
        request=dict(schema_version=1,input_mode="synthetic_test",horizon=20,max_context=512,batch_size=1,threads=2,repeats=5,
                     series=[dict(instrument=f"synthetic-{n}",values=[.01]*512) for n in range(100)])
        token=secrets.token_hex(16)
        tag="STRATIDE_TIMESFM_RUN="+token
        code="import sys;sys.path.insert(0,sys.argv[1]);import runtime;runtime.secrets.token_hex=lambda _:sys.argv[2];runtime.run(sys.stdin.buffer.read())"
        with runtime.lock(cli.state_root()/"worker.lock"):
            child=subprocess.Popen([sys.executable,"-c",code,str(runtime.ROOT/"research/timesfm_cpu"),token],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            child.stdin.write(json.dumps(request).encode());child.stdin.close();child.stdin=None
            try:
                resident=None
                for _ in range(300):
                    p=subprocess.run(["systemctl","--user","is-active",runtime.UNIT],capture_output=True)
                    env=subprocess.run(["systemctl","--user","show",runtime.UNIT,"--property=Environment","--value"],capture_output=True)
                    if p.stdout.strip()==b"active" and tag in env.stdout.decode().split():
                        group=subprocess.run(["systemctl","--user","show",runtime.UNIT,"--property=ControlGroup","--value"],capture_output=True,text=True).stdout.strip()
                        cg=Path("/sys/fs/cgroup")/group.lstrip("/")
                        try:
                            for pid in (cg/"cgroup.procs").read_text().split():
                                proc=Path("/proc")/pid
                                if b"/app/worker.py" not in (proc/"cmdline").read_bytes():continue
                                rss=int(next(line.split()[1] for line in (proc/"status").read_text().splitlines() if line.startswith("VmRSS:")))*1024
                                if rss >= 1024**3:
                                    resident=dict(worker_pid=int(pid),worker_rss_bytes=rss,
                                        cgroup={k:(cg/k).read_text().strip() for k in ("memory.max","memory.swap.max","memory.oom.group","memory.current","memory.peak")})
                                    break
                        except (OSError,StopIteration):pass
                        if resident:break
                    time.sleep(.1)
                else:self.fail("Real Worker did not become resident before controller death")
                self.assertIsNone(child.poll())
                FACTS.append(dict(test="controller_death_before_kill",host=resident))
                killed_at=time.monotonic()
                child.kill();child.communicate(timeout=15)
                for _ in range(100):
                    p=subprocess.run(["systemctl","--user","is-active",runtime.UNIT],capture_output=True)
                    if p.stdout.strip()!=b"active":break
                    time.sleep(.1)
                self.assertNotEqual(p.stdout.strip(),b"active")
                for _ in range(50):
                    if not Path("/proc",str(resident["worker_pid"])).exists():break
                    time.sleep(.1)
                self.assertFalse(Path("/proc",str(resident["worker_pid"])).exists())
                FACTS.append(dict(test="controller_death_after_kill",unit_active=False,worker_pid_exists=False,
                                  cleanup_seconds=time.monotonic()-killed_at))
            finally:
                if child.poll() is None:child.kill();child.communicate(timeout=5)
                runtime.stop_owned(tag)


if __name__=="__main__":
    result=unittest.main(verbosity=2,exit=False).result
    import os
    evidence=os.environ.get("STRATIDE_TIMESFM_TEST_EVIDENCE")
    if evidence:Path(evidence).write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),facts=FACTS),indent=2)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
