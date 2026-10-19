"""
OFFICIALUM1 — Automated VPS Deployer via Paramiko
Connects to 142.93.19.40, uploads project files, and triggers deploy_vps.sh
"""
import os
import sys
import time

try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("[ERROR] paramiko or scp not installed yet.")
    sys.exit(1)

VPS_IP = "142.93.19.40"
VPS_USER = "root"
VPS_PASS = "!52BRnnsnuZtzYM"
REMOTE_DIR = "/opt/firwallum1"
LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def progress(filename, size, sent):
    sys.stdout.write(f"\r  Uploading {os.path.basename(filename.decode('utf-8', 'ignore') if isinstance(filename, bytes) else filename)}: {sent}/{size} bytes")
    sys.stdout.flush()

def main():
    print("=" * 65)
    print(f"[*] Connecting to {VPS_USER}@{VPS_IP} via SSH...")
    print("=" * 65)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(VPS_IP, port=22, username=VPS_USER, password=VPS_PASS, timeout=30)
        print("[+] SSH Authentication Succeeded!")
    except Exception as e:
        print(f"[-] SSH Connection failed: {e}")
        sys.exit(1)

    # 1. Ensure remote directory exists
    print(f"[*] Preparing remote directory: {REMOTE_DIR}")
    ssh.exec_command(f"mkdir -p {REMOTE_DIR}")

    # 2. Upload codebase
    print("[*] Uploading core files to VPS...")
    items_to_upload = [
        "core", "data", "web", "scripts",
        "Dockerfile", "requirements.txt", "server.py", "deploy_vps.sh"
    ]

    with SCPClient(ssh.get_transport(), progress=progress) as scp:
        for item in items_to_upload:
            local_path = os.path.join(LOCAL_DIR, item)
            if os.path.exists(local_path):
                print(f"\n[*] Transferring {item}...")
                scp.put(local_path, remote_path=REMOTE_DIR, recursive=True)

    print("\n[+] All project files uploaded successfully!")

    # 3. Fix line endings and execute deploy_vps.sh
    print("\n" + "=" * 65)
    print("[*] Executing deploy_vps.sh on VPS (setting up Swap, DNS & Service)...")
    print("=" * 65)

    setup_cmd = f"cd {REMOTE_DIR} && sed -i 's/\\r$//' deploy_vps.sh && chmod +x deploy_vps.sh && bash deploy_vps.sh"
    stdin, stdout, stderr = ssh.exec_command(setup_cmd, get_pty=True)

    for line in iter(stdout.readline, ""):
        print(line, end="")

    exit_status = stdout.channel.recv_exit_status()
    print(f"\n[*] Setup finished with exit status: {exit_status}")

    # 4. Check systemctl status
    print("\n[*] Checking service status...")
    out_text = status_out.read().decode("utf-8", "ignore")
    print(out_text.encode("ascii", "replace").decode("ascii"))

    ssh.close()
    print("\n" + "=" * 65)
    print("[+] AUTOMATED DEPLOYMENT FINISHED!")
    print("=" * 65)

if __name__ == "__main__":
    main()
