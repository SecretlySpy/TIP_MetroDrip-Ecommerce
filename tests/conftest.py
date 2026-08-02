import os
import subprocess
import time
import socket
import pytest

uvicorn_proc = None

def wait_for_port(port, host='127.0.0.1', timeout=5.0):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False

@pytest.fixture(scope="session", autouse=True)
def start_fastapi(django_db_setup, django_db_blocker):
    global uvicorn_proc
    env = os.environ.copy()
    env["MYSQL_DATABASE_INVENTORY"] = "test_metrodrip"
    env["SKIP_CREATE_ALL"] = "1"
    
    import sys
    uvicorn_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", 
            "services.inventory.main:app", 
            "--port", "8000"
        ],
        env=env
    )
    if not wait_for_port(8000):
        print("WARNING: Uvicorn did not start on port 8000 in time")
    
    yield
    
    if uvicorn_proc:
        uvicorn_proc.terminate()
        uvicorn_proc.wait()
