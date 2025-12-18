# AI Agent Connection Guide: Google Cloud VM

**Objective:** Connect to the user's Google Cloud VM `alpaca-trader` via SSH.

## 1. Credentials & Config
- **IP Address:** `34.56.193.18`
- **Username:** `jetpackjules`
- **Private Key Path:** `./gcp_key` (Located in the root of this workspace: `kalshi_weather_data`)
- **Public Key:** Already configured on the VM.

## 2. Action: Connect via SSH
You do **not** need `gcloud` CLI access. Use the standard `ssh` tool with the provided key file.

**Run this exact command in the terminal:**
```powershell
ssh -i ./gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18
```

## 3. Troubleshooting
- If you see "Permissions denied", ensure you are using `-i ./gcp_key`.
- If asked for a passphrase, there is none (press Enter if prompted, though it shouldn't be).
- The key file `gcp_key` must exist in your current working directory.
