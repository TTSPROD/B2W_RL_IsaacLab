"""HTTP origin protection, recipe bounds and actual supervisor stop/failure paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "scripts"))
import jobs
import server
from run_support import read_json, write_json, utc_now
urlopen = build_opener(ProxyHandler({})).open


class DashboardTests(unittest.TestCase):
    def test_submission_succeeds_when_monitor_launch_fails(self):
        import process_client
        with patch.object(process_client,'start_job',return_value={'id':'independent'}) as start, \
             patch.object(process_client.subprocess,'Popen',side_effect=OSError('monitor unavailable')):
            result=process_client.submit({'kind':'tests'})
        start.assert_called_once_with({'kind':'tests'})
        self.assertEqual(result['id'],'independent')

    def test_headless_submission_does_not_launch_or_contact_monitor(self):
        import process_client
        with patch.object(process_client,'start_job',return_value={'id':'independent'}), \
             patch.object(process_client.subprocess,'Popen') as launch:
            process_client.submit({'kind':'tests'},open_monitor=False)
        launch.assert_not_called()

    def test_missing_metrics_dependency_preserves_run_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); run = root / "fixture"; run.mkdir()
            write_json(run / "continuation_manifest.json", {"parent_iteration": 24650,
                "additional_updates": 1500, "created_utc": utc_now()})
            write_json(run / "progress.json", {"status": "running", "completed_updates": 7,
                "target_updates": 1500, "updated_utc": utc_now()})
            with patch.object(server, "LOGS", root), patch.object(server, "CACHE", {}), \
                 patch.object(server, "runs", return_value=[{"id": "fixture"}]), \
                 patch.object(server, "event_accumulator", side_effect=ModuleNotFoundError("tensorboard")):
                data = server.run_data("fixture")
            self.assertEqual(data["progress"]["completed_updates"], 7)
            self.assertEqual(data["series"], {})
            self.assertIn("tensorboard", data["metrics_warning"])

    @unittest.skipUnless((Path(os.environ.get("B2W_ISAAC_SIM_ENV", "D:/isaacsim51")) / "Lib/site-packages/tensorboard").is_dir(),
                         "Existing local simulator packages required")
    def test_metrics_import_without_inherited_pythonpath(self):
        env = dict(os.environ, PYTHONPATH="")
        code = "import sys;sys.path.insert(0,'dashboard');from server import event_accumulator;print(event_accumulator().__name__)"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EventAccumulator", result.stdout)

    def test_atomic_state_survives_windows_reader_sharing_conflict(self):
        import run_support
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            write_json(path, {"status": "running"})
            replace = os.replace
            calls = []
            def shared_reader(source, destination):
                calls.append(1)
                if len(calls) <= 2:
                    self.assertEqual(read_json(path), {"status": "running"})
                    raise PermissionError("Windows reader has not released its handle")
                return replace(source, destination)
            with patch.object(run_support.os, "replace", side_effect=shared_reader):
                write_json(path, {"status": "completed"})
            self.assertEqual(read_json(path), {"status": "completed"})
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_recipes_reject_remote_arbitrary_shell_and_bad_budgets(self):
        for payload in ({"kind": "server"}, {"entrypoint": "cmd.exe"},
                        {"kind": "train", "updates": 0}, {"kind": "train", "updates": True},
                        {"kind": "evaluate", "policy": "../../vendor"}):
            with self.assertRaises(ValueError):
                jobs.recipe(payload)
        self.assertEqual(jobs.recipe({"kind": "compare"})[0], "scripts/run_locomotion.py")

    def test_dashboard_rejects_all_mutations(self):
        http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{http.server_port}"
        try:
            for headers in ({}, {"X-B2W-Token": server.TOKEN, "Origin": "https://foreign.example"},
                            {"X-B2W-Token": server.TOKEN, "Host": "foreign.example"}):
                request = Request(url + "/api/jobs", b'{"kind":"tests"}', headers=headers)
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=3)
                self.assertEqual(caught.exception.code, 405)
            with urlopen(url + "/api/health", timeout=3) as response:
                self.assertEqual(json.load(response)["service"], "b2w-dashboard-v2")
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    @unittest.skipUnless(sys.platform == "win32", "Windows Job Object test")
    def test_supervisor_reports_failure_and_cancellation_and_reaps_children(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                state = {"id": "fixture", "kind": "fixture", "entrypoint": "fixture", "arguments": [],
                         "status": "queued", "created": utc_now(), "updated": utc_now(), "returncode": None}
                write_json(directory / "request.json", state)
                training=directory/'logs/rsl_rl/completed_run/progress.json'
                write_json(training,{'status':'completed','completed_updates':1350,'target_updates':1350})
                training_bytes=training.read_bytes()
                write_json(directory/'training_run.json',{'path':'logs/rsl_rl/completed_run'})
                payload = ("import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
                           "print(p.pid,flush=True);time.sleep(120)") if cancel else "raise SystemExit(7)"
                bootstrap = (f"import sys,pathlib;sys.path.insert(0,{str(ROOT / 'dashboard')!r});import worker;"
                    f"worker.job_path=lambda _:pathlib.Path({folder!r});"
                    f"worker.ROOT=pathlib.Path({folder!r});"
                    f"worker.local_command=lambda *args:[sys.executable,'-c',{payload!r}];"
                    "sys.argv=['worker','fixture'];worker.main()")
                process = subprocess.Popen([sys.executable, "-c", bootstrap], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                child_pid = None
                try:
                    if cancel:
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            output = directory / "stdout.log"
                            if output.exists() and output.read_text().strip():
                                child_pid = int(output.read_text().strip())
                                break
                            if process.poll() is not None:
                                break
                            time.sleep(.1)
                        self.assertIsNotNone(child_pid)
                        (directory / "cancel").touch()
                    stdout, stderr = process.communicate(timeout=20)
                    self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
                    final = read_json(directory / "state.json")
                    self.assertEqual(training.read_bytes(),training_bytes)
                    self.assertEqual(final["status"], "cancelled" if cancel else "failed")
                    if not cancel:
                        self.assertEqual(final["returncode"], 7)
                    if child_pid:
                        self.assertFalse(jobs.process_running(child_pid))
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
