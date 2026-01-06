# How to Restart the Dashboard Server Only

Use these commands if you just need to restart the dashboard (e.g., if it's stuck) without re-uploading files.

### 1. Stop the Server
This kills any running `server_app.py` process.

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "sudo pkill -f server_app.py"
```

### 2. Start the Server
Starts the server in the background on Port 80.

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "sudo nohup /home/jetpackjules/venv/bin/python server_app.py > server_app.log 2>&1 &"
```

### 3. Verify
Check if it's running:

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "ps -ef | grep server_app"
```
