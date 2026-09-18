"""Project-scoped SSH transport for the explicitly assigned Windows laptop."""
import base64
from pathlib import Path
import subprocess

from b2w_runtime import PROJECT_ROOT as ROOT

HOST = '192.168.1.129'
USER = r'severstal\ra.suragin'
REMOTE_ROOT = 'D:/Work/GitProjects/B2W_RL_IsaacLab'
KEY = Path.home() / '.ssh/id_ed25519'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def remote_command(script):
    prefix = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
    prefix += "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);"
    prefix += f"Set-Location -LiteralPath '{REMOTE_ROOT}';"
    # The desktop app PATH contains a corporate reparse point on this laptop.
    # Restrict only our SSH process; do not modify system/user environment.
    prefix += "$env:PATH='C:\\Windows\\System32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0;C:\\Program Files\\Git\\cmd';"
    prefix += "$env:PYTHONDONTWRITEBYTECODE='1';$env:OMNI_KIT_ACCEPT_EULA='YES';"
    encoded = base64.b64encode((prefix + script).encode('utf-16le')).decode('ascii')
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=10',
            '-i', str(KEY), '-l', USER, HOST, 'powershell.exe', '-NoProfile', '-EncodedCommand', encoded]


def execute(script, timeout=60):
    return subprocess.run(remote_command(script), cwd=ROOT, check=True,
                          capture_output=True, text=True, encoding='utf-8',
                          timeout=timeout, creationflags=FLAGS).stdout


def project_path(relative):
    value = str(relative).replace('\\', '/')
    if value.startswith('/') or ':' in value or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Expected a project-relative path')
    return f'{HOST}:{REMOTE_ROOT}/{value}'


def copy(relative, local, download=False, timeout=600):
    remote = project_path(relative)
    endpoints = [remote, str(local)] if download else [str(local), remote]
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                    '-i', str(KEY), '-o', 'User=' + USER, *endpoints], cwd=ROOT,
                   check=True, timeout=timeout, creationflags=FLAGS)
