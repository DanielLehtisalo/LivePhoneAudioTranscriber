

import os
import subprocess

VENV_DIR = "venv"

if __name__ == "__main__":
    if os.name == "nt":  # Windows
        venv_python = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:  # macOS and Linux
        venv_python = os.path.join(VENV_DIR, "bin", "python")
    
    if os.path.exists(venv_python):
        print("Starting LPAT")
        project_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(
            [venv_python, f"{os.path.join("src/main.py")}"],
            cwd=project_dir,
            check=True
        )
    else:
        print("venv seems to be missing, run setup.py first.")