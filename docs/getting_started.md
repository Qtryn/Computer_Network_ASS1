# Getting Started

These commands assume Windows PowerShell and the repository root.

## 1. Install

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/generate_key.py
```

`generate_key.py` writes `config/local_key.txt`. **Never commit it to Git**.
For a LAN demo on separate computers, each client/server must use the same
key, sent privately outside the GitHub repository. Use only a test key.

## 2. Run all checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke_test.py
.\.venv\Scripts\python.exe scripts/load_test.py
```

## 3. Run in three terminals

```powershell
.\.venv\Scripts\python.exe -m app.run_server
```

```powershell
.\.venv\Scripts\python.exe -m app.run_client --name alice --ui-port 8011
```

```powershell
.\.venv\Scripts\python.exe -m app.run_client --name bob --ui-port 8012
```

Alice UI: http://127.0.0.1:8011  
Bob UI: http://127.0.0.1:8012

Send a private message, broadcast to everyone, and send a binary file.
Received file: `downloads/bob/`.

## 4. LAN demo

On the server PC:

```powershell
python -m app.run_server --host 0.0.0.0
```

On each client PC, replace `SERVER_IP` with the actual server LAN IP:

```powershell
python -m app.run_client --name alice --host SERVER_IP --ui-port 8011
```

Use a unique username on each client. Local UI port numbers only need to be
unique for processes running on the **same machine**. Allow private-network
TCP 9100 and UDP 9101 on the server firewall. Every browser connects to its
**own** 127.0.0.1 UI; it is never accessed remotely.

## 5. Common errors

- `ModuleNotFoundError: cryptography`: install `requirements.txt` into the
  Python interpreter used to run the app.
- `Missing AES key`: generate the test key or set the `COLLAB_KEY` environment
  variable to the same 64-character hex string on all peers.
- `Address already in use`: close the old process or choose another UI port.
- `Login rejected`: choose a different username and check server logs.
- `No UDP messages`: check Windows Firewall and matching test keys/IPs/ports.

## 6. Git

Read `docs/git_workflow.md` before any shared edits. Do not edit another
member's folder without discussing the change first.
