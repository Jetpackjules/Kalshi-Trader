# How to Deploy and Start the Dashboard

These are the exact commands to upload the latest dashboard code and start the server on Port 80.

### 1. Upload Files
Run this from your local `kalshi_weather_data` directory:

```powershell
scp -i .\keys\gcp_key -o StrictHostKeyChecking=no server_mirror\server_app.py server_mirror\dashboard.html jetpackjules@34.56.193.18:~
```

### 2. Start the Server (Port 80)
This command uses `sudo` (required for Port 80) and `nohup` (to keep it running after you disconnect).

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "sudo nohup /home/jetpackjules/venv/bin/python server_app.py > server_app.log 2>&1 &"
```

### 3. Verify
You can check if it's running with:

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "ps -ef | grep server_app"
```

Access the dashboard at: http://34.56.193.18/dashboard.html
