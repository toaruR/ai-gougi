"""孫プロセス(長時間sleep)を起動し、その PID を stdout に出力してハングする stub。"""
import subprocess
import sys
import time

gc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
print(gc.pid, flush=True)
time.sleep(600)
