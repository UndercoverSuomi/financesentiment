from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'backend'
FRONTEND_DIR = REPO_ROOT / 'frontend'
VENV_DIR = REPO_ROOT / '.venv'


def is_windows() -> bool:
    return os.name == 'nt'


def backend_python_path() -> Path:
    if is_windows():
        return VENV_DIR / 'Scripts' / 'python.exe'
    return VENV_DIR / 'bin' / 'python'


def npm_command() -> str:
    return 'npm.cmd' if is_windows() else 'npm'


def run_checked(cmd: list[str], cwd: Path | None = None) -> None:
    print(f'> {" ".join(cmd)}')
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def can_connect(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def ensure_backend_ready() -> Path:
    py = backend_python_path()
    if not py.exists():
        run_checked([sys.executable, '-m', 'venv', str(VENV_DIR)], cwd=REPO_ROOT)

    try:
        run_checked([str(py), '-c', 'import fastapi,uvicorn,sqlalchemy,alembic'], cwd=BACKEND_DIR)
    except subprocess.CalledProcessError:
        run_checked([str(py), '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=BACKEND_DIR)

    run_checked([str(py), '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND_DIR)
    return py


def ensure_frontend_ready() -> None:
    node_modules = FRONTEND_DIR / 'node_modules'
    if not node_modules.exists():
        run_checked([npm_command(), 'install'], cwd=FRONTEND_DIR)


def pipe_output(prefix: str, proc: subprocess.Popen[str]) -> threading.Thread:
    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            raw = line.rstrip()
            out_enc = sys.stdout.encoding or 'utf-8'
            safe = raw.encode(out_enc, errors='replace').decode(out_enc, errors='replace')
            print(f'[{prefix}] {safe}')

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return thread


def terminate_proc(proc: subprocess.Popen[str], name: str) -> None:
    if proc.poll() is not None:
        return
    print(f'Stopping {name}...')
    if is_windows():
        try:
            subprocess.run(
                ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
        return
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
        proc.wait(timeout=5)


def start_process(cmd: list[str], cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Start backend + frontend together (one command).',
    )
    parser.add_argument(
        '--skip-setup',
        action='store_true',
        help='Skip venv/dependency/migration checks.',
    )
    parser.add_argument(
        '--duration',
        type=float,
        default=None,
        help='Optional auto-stop after N seconds (useful for quick checks).',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if can_connect('127.0.0.1', 8000) or can_connect('127.0.0.1', 3000):
        print('Port 8000 or 3000 is already in use. Stop existing dev servers first.')
        return 2

    try:
        if not args.skip_setup:
            py = ensure_backend_ready()
            ensure_frontend_ready()
        else:
            py = backend_python_path()
            if not py.exists():
                print('Shared repo venv missing. Run without --skip-setup once.')
                return 2
    except subprocess.CalledProcessError as exc:
        print(f'Setup failed (exit code {exc.returncode}).')
        return exc.returncode or 1

    backend_cmd = [
        str(py),
        '-m',
        'uvicorn',
        'app.main:app',
        '--host',
        '127.0.0.1',
        '--port',
        '8000',
    ]
    frontend_cmd = [
        npm_command(),
        'run',
        'dev',
        '--',
        '--hostname',
        '127.0.0.1',
        '--port',
        '3000',
    ]

    backend_proc: subprocess.Popen[str] | None = None
    frontend_proc: subprocess.Popen[str] | None = None
    deadline = time.time() + args.duration if args.duration and args.duration > 0 else None

    try:
        backend_proc = start_process(backend_cmd, BACKEND_DIR)
        pipe_output('backend', backend_proc)
        time.sleep(1.5)
        if backend_proc.poll() is not None:
            print('Backend exited during startup.')
            return backend_proc.returncode or 1

        frontend_proc = start_process(frontend_cmd, FRONTEND_DIR)
        pipe_output('frontend', frontend_proc)

        print('Dev stack started.')
        print('Backend:  http://127.0.0.1:8000')
        print('Frontend: http://127.0.0.1:3000')
        print('Press Ctrl+C to stop both.')

        while True:
            if backend_proc.poll() is not None:
                print('Backend stopped unexpectedly.')
                return backend_proc.returncode or 1
            if frontend_proc.poll() is not None:
                print('Frontend stopped unexpectedly.')
                return frontend_proc.returncode or 1
            if deadline and time.time() >= deadline:
                print('Duration reached, shutting down.')
                return 0
            time.sleep(0.4)
    except KeyboardInterrupt:
        print('Interrupted by user.')
        return 0
    finally:
        if frontend_proc is not None:
            terminate_proc(frontend_proc, 'frontend')
        if backend_proc is not None:
            terminate_proc(backend_proc, 'backend')


if __name__ == '__main__':
    try:
        if is_windows():
            signal.signal(signal.SIGINT, signal.default_int_handler)
    except Exception:
        pass
    raise SystemExit(main())
