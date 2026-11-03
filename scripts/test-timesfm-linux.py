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


@unittest.skipUnless(sys.platform=="linux","Linux/WSL not available: NOT_RUN")
class LinuxIsolation(unittest.TestCase):
    def launch(self,kind="",memory=None,timeout=15):
        args=runtime.command(2)
        tag="STRATIDE_TIMESFM_RUN=acceptance"+str(__import__("os").getpid())
        args.insert(1,"--setenv="+tag)
        args[-1]="/app/isolation_probe.py"
        if kind:args.append(kind)
        if memory:
            args=["--property=MemoryMax="+str(memory) if a.startswith("--property=MemoryMax=") else a for a in args]
        def cleanup():
            runtime.stop_owned(tag)
        with runtime.lock(cli.state_root()/"worker.lock"):
            return runtime.communicate_bounded(args,b"",cleanup=cleanup,timeout=timeout)

    def test_01_network_filesystem_environment_and_6gib(self):
        result=self.launch()
        self.assertTrue(all(result[k] for k in ("network_denied","model_readonly","home_hidden","secrets_absent")))
        self.assertEqual(result["isolation"]["memory_max_bytes"],6*1024**3)

    def test_02_oom_kills_cgroup_and_next_start_works(self):
        with self.assertRaises(Rejected):self.launch("memory",128*1024**2)
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
                for _ in range(50):
                    p=subprocess.run(["systemctl","--user","is-active",runtime.UNIT],capture_output=True)
                    env=subprocess.run(["systemctl","--user","show",runtime.UNIT,"--property=Environment","--value"],capture_output=True)
                    if p.stdout.strip()==b"active" and tag in env.stdout.decode().split():break
                    time.sleep(.1)
                else:self.fail("Worker unit did not start")
                child.kill();child.communicate(timeout=15)
                for _ in range(100):
                    p=subprocess.run(["systemctl","--user","is-active",runtime.UNIT],capture_output=True)
                    if p.stdout.strip()!=b"active":break
                    time.sleep(.1)
                self.assertNotEqual(p.stdout.strip(),b"active")
            finally:
                if child.poll() is None:child.kill();child.communicate(timeout=5)
                runtime.stop_owned(tag)


if __name__=="__main__":unittest.main(verbosity=2)
