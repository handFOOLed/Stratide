import sys,json,pathlib
from unittest.mock import patch
root=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'research/timesfm_cpu'))
import model,worker
request=model.loads(sys.stdin.buffer.read())
with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')) as tcp,patch('requests.sessions.Session.request',side_effect=AssertionError('NETWORK_FORBIDDEN')) as http:
 result=worker.execute(request,root/'models/timesfm-2.5')
 assert tcp.call_count==0 and http.call_count==0
print(json.dumps(dict(backend='REAL_TIMESFM_2_5_CPU',forecasts_sha256=model.digest(result['forecasts']),socket_connect_calls=tcp.call_count,http_calls=http.call_count,offline_load_and_forecast=True)))
