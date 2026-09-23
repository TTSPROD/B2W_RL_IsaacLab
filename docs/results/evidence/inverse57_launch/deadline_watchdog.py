import json, subprocess, time
from pathlib import Path
r=Path(__file__).resolve().parent
budget=json.loads((r/'budget.json').read_text())
deadline=budget['start_epoch']+15*3600
container='63d6172d21155ea01570557a8ea349d52642fb04afc722d935a2c7b23758e392'
while time.time()<deadline-60:
 time.sleep(min(60,max(0,deadline-60-time.time())))
state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}',container],text=True))
if state['Running']:
 p=subprocess.run(['docker','stop','--time','30',container],capture_output=True,text=True)
 (r/'watchdog_stop.json').write_text(json.dumps({'deadline':deadline,'stopped_at':time.time(),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}))
