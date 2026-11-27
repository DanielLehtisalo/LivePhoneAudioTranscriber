import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_DIR, "venv")

def venv_python_path():
    if os.name == "nt":  # Windows
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")  # macOS and Linux

def resolve_args(args):
    if args and args[0] == "verify":
        return ["verify"] + [a if a.startswith("-") else os.path.abspath(a) for a in args[1:]]
    return args

if __name__ == "__main__":
    venv_python = venv_python_path()
    if not os.path.exists(venv_python):
        print("venv seems to be missing, run setup.py first.")
        sys.exit(1)

    args = resolve_args(sys.argv[1:])
    if not args:
        print("Starting LPAT")

    try:
        result = subprocess.run(
            [venv_python, os.path.join(PROJECT_DIR, "src", "main.py"), *args],
            cwd=PROJECT_DIR,
        )
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        sys.exit(130)