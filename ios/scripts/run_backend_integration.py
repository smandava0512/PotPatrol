"""Run Swift client tests against a pinned, separately checked-out backend fixture."""
from pathlib import Path
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

backend = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="potpatrol-contract-") as temporary:
    folder = Path(temporary)
    with socket.socket() as socket_handle:
        socket_handle.bind(("127.0.0.1", 0))
        port = socket_handle.getsockname()[1]
    env = os.environ.copy()
    env.update(POTPATROL_DEVICE_TOKEN=secrets.token_urlsafe(32),
               POTPATROL_DATABASE_URL=f"sqlite:///{folder / 'drives.sqlite'}",
               POTPATROL_STORAGE_DIR=str(folder / "storage"),
               POTPATROL_ANALYZER="potpatrol.fixture_worker:analyze")
    base = f"http://127.0.0.1:{port}"
    processes = []
    with (folder / "backend.log").open("w+") as log:
        try:
            processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "potpatrol.api:app", "--host", "127.0.0.1", "--port", str(port)], cwd=backend, env=env, stdout=log, stderr=log))
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + "/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Contract backend did not start")
            processes.append(subprocess.Popen([sys.executable, "-m", "potpatrol.worker", "--loop"], cwd=backend, env=env, stdout=log, stderr=log))
            test_env = os.environ.copy()
            test_env.update(POTPATROL_TEST_BASE_URL=base, POTPATROL_TEST_TOKEN=env["POTPATROL_DEVICE_TOKEN"])
            subprocess.run(["swift", "test", "--filter", "BackendIntegrationTests"], env=test_env, check=True)
        except Exception:
            log.flush()
            log.seek(0)
            # The token is never logged by this script or included in command arguments.
            print(log.read())
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
