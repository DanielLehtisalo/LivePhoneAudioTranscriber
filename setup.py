import os
import subprocess
import sys
import venv
import shutil
import json


VENV_DIR = "venv"
CERT_DIR = "certs"
MODELS_DIR = "models"
CERT_DURATION = 365

MODELS = ["large-v3-turbo", "large-v3"]

KEYS_DIR = "keys"
PRIVATE_KEY = f"{KEYS_DIR}/private_key.pem"
PUBLIC_KEY = f"{KEYS_DIR}/public_key.pem"

def create_certificate(openssl_path):
    print("OpenSSL found, creating certificate.")
    if not os.path.exists(CERT_DIR):
        print("Creating missing cert directory.")
        os.mkdir(CERT_DIR)
    if not os.path.exists(f"{CERT_DIR}/key.pem"): 
        subprocess.run(
            [openssl_path, "genrsa", "-out", f"{CERT_DIR}/key.pem", "2048"]
        )
        print("Created private key.")
    else:
        print("Skipped creating private key for certificate.")
    if not os.path.exists(f"{CERT_DIR}/signreq.csr"):
        subprocess.run(
                    [openssl_path, "req", "-new", 
                     "-key", f"{CERT_DIR}/key.pem", 
                     "-out", f"{CERT_DIR}/signreq.csr", 
                     "-subj", "/" # Remove "-subj", "/" to fill in the questions.
                    ] 
                )
        print("Created signreq with blank details, if you wish to fill these in edit this script.")
    else:
        print("Skipped creating signreq.")
    if not os.path.exists(f"{CERT_DIR}/certificate.pem"):
        subprocess.run(
                        [openssl_path, "x509", "-req", 
                         "-days", f"{CERT_DURATION}", 
                         "-in", f"{CERT_DIR}/signreq.csr", 
                         "-signkey", f"{CERT_DIR}/key.pem", 
                         "-out", f"{CERT_DIR}/certificate.pem"
                        ]
                )
        print("Created certificate.")
    else:
        print("Skipped creating certificate.")

def create_signing_key(openssl_path):
    if os.path.exists(PRIVATE_KEY):
        print("Skipped creating signing key.")
    else:
        os.makedirs(KEYS_DIR, exist_ok=True)
        print("Creating signing key.")
        subprocess.run([openssl_path, "genpkey", "-algorithm", "ed25519", "-out", PRIVATE_KEY], check=True)

    if not os.path.exists(PUBLIC_KEY):
        print("Creating public key from signing key.")
        subprocess.run([openssl_path, "pkey", "-in", PRIVATE_KEY, "-pubout", "-out", PUBLIC_KEY], check=True)
    else:
        print("Skipped creating public key.")

def download_models(venv_python):
    script = (
        "import sys\n"
        "from faster_whisper import download_model\n"
        "out_dir = sys.argv[1]\n"
        "for name in sys.argv[2:]:\n"
        "    download_model(name, output_dir=f'{out_dir}/{name}')\n"
        "    print(f'Model ready: {name}')\n"
    )
    print("Downloading missing transcription models. This might take a while.")
    subprocess.run([venv_python, "-c", script, MODELS_DIR, *MODELS], check=True)
    print("All models downloaded.")

def main():
    if not os.path.exists(VENV_DIR):
        print(f"Creating virtual environment in '{VENV_DIR}'")
        venv.create(VENV_DIR, with_pip=True)
    else:
        print(f"Virtual environment '{VENV_DIR}' already exists.")

    if os.name == "nt":  # Windows
        venv_python = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:  # macOS and Linux
        venv_python = os.path.join(VENV_DIR, "bin", "python")

    if os.path.exists("min-requirements.txt"):
        print("Installing minimum dependencies from min-requirements.txt...")
        subprocess.run(
            [venv_python, "-m", "pip", "install", "-r", "min-requirements.txt"],
            check=True,
        )
        print("\nMinimum dependencies installed.")
    else:
        print("No min-requirements.txt found. Skipping package installation.")

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        if os.path.exists("requirements.txt"):
            print("Installing dependencies from requirements.txt...")
            subprocess.run(
                [venv_python, "-m", "pip", "install", "-r", "requirements.txt"],
                check=True,
            )
            print("\nDependencies installed.")
        else:
            print("No requirements.txt found. Skipping package installation.")

        openssl_path = shutil.which("openssl")
        if openssl_path:
            create_certificate(openssl_path)
            create_signing_key(openssl_path)
        else:
            print("OpenSSL is not installed, please install it and add it to the system path.")

        download_models(venv_python)
        print("Setup completed.")

if __name__ == "__main__":
    main()
