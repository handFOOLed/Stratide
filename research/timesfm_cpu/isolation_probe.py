"""Fixed Linux acceptance probes. Not selectable through the production Worker."""
import json
import os
from pathlib import Path
import socket
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))

if sys.argv[1:] == ["memory"]:
    data=bytearray(256*1024*1024)
    for i in range(0,len(data),4096):data[i]=1
    print(json.dumps(dict(error_code="MEMORY_LIMIT_NOT_ENFORCED")))
elif sys.argv[1:] == ["hang"]:
    time.sleep(30)
elif sys.argv[1:] == ["crash"]:
    os._exit(42)
else:
    from worker import linux_limits
    limits=linux_limits()
    sock=socket.socket()
    sock.settimeout(.5)
    try:
        sock.connect(("1.1.1.1",443))
        network=False
    except OSError:
        network=True
    finally:
        sock.close()
    try:
        Path("/model/.isolation-write-probe").write_bytes(b"probe")
        readonly=False
    except OSError:
        readonly=True
    print(json.dumps(dict(network_denied=network,model_readonly=readonly,home_hidden=not Path("/home").exists(),
                          secrets_absent=(os.environ.get("HF_HUB_DISABLE_IMPLICIT_TOKEN") == "1" and not any(
                              any(marker in k for marker in ("KEY", "TOKEN", "SECRET"))
                              and k != "HF_HUB_DISABLE_IMPLICIT_TOKEN" for k in os.environ)),isolation=limits)))
