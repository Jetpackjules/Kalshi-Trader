import subprocess
import sys
from pathlib import Path

def main():
    # Configuration
    host = "34.56.193.18"
    user = "jetpackjules"
    
    # Paths
    root_dir = Path(__file__).resolve().parent
    key_path = root_dir / "keys" / "gcp_key"
    local_file = root_dir / "server_mirror" / "dashboard.html"
    remote_dest = f"{user}@{host}:~/dashboard.html"

    if not local_file.exists():
        print(f"Error: Local file not found at {local_file}")
        sys.exit(1)
    
    if not key_path.exists():
        print(f"Error: SSH key not found at {key_path}")
        sys.exit(1)

    # SCP Command
    scp_cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-i", str(key_path),
        str(local_file),
        remote_dest
    ]

    print(f"Uploading {local_file.name} to {host}...")
    try:
        subprocess.run(scp_cmd, check=True)
        print("Successfully uploaded dashboard.html!")
    except subprocess.CalledProcessError as e:
        print(f"Upload failed with exit code {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
