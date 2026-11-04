# Workflow Git for 5 teammates (beginner-friendly)

## 0. One coordinator creates the private GitHub repository

1. Create an **EMPTY, private** repo on GitHub, e.g. `network-collaboration`.
2. Do **not** choose "Initialize with README" (the ZIP already has a README).
3. Extract the ZIP and open a terminal **inside the `network-collaboration` folder**.
4. Run (replace the URL and user identity with your own):

```bash
git init
git branch -M main
git add .
git commit -m "Initial runnable project scaffold"
git remote add origin https://github.com/OWNER/network-collaboration.git
git push -u origin main
```

If Git complains about author identity, configure *your own* name and email
first: `git config --global user.name "Your Name"` and
`git config --global user.email "you@example.com"`.

**Before committing**, run `git status` and verify `config/local_key.txt`,
`downloads/` and `.venv/` are **not** listed. Do not `git add -f` those files.

Invite four collaborators under GitHub repo **Settings → Collaborators**.

## 1. Each member clones once

```bash
git clone https://github.com/OWNER/network-collaboration.git
cd network-collaboration
python -m venv .venv
```

Activate venv and install dependencies as shown in the README, then obtain
`config/local_key.txt` securely from the coordinator (NOT through the repo).

## 2. Each member creates a distinct branch

| Member | Suggested branch | Primarily edits |
|---|---|---|
| Member 1 | `feature/member1-server` | `app/server/`, `app/run_server.py` |
| Member 2 | `feature/member2-transport` | `app/transport/`, transport tests |
| **Member 3 (you)** | **`feature/member3-chat-file`** | **`app/features/`, `tests/test_features.py`** |
| Member 4 | `feature/member4-ui` | `app/web/`, `app/client.py`, `app/run_client.py` |
| Member 5 | `feature/member5-security-tests` | `app/security/`, security + system tests, docs |

Example for Member 3:

```bash
git switch main
git pull origin main
git switch -c feature/tv3-chat-file
```

**Do not create five independent server implementations.** Shared code and API
are already present; extend them rather than rewriting the whole project.

## 3. Everyday work (Member 3 example)

Edit only your module and its tests, then run:

```bash
python -m unittest discover -s tests -v
python scripts/smoke_test.py
git status
git add app/features tests/test_features.py
git commit -m "Member 3: improve file validation and test cases"
git push -u origin feature/tv3-chat-file
```

After the first `git push -u`, you can use simply `git push` on that branch.
Open GitHub → **Pull requests** → **New pull request** → base: `main`, compare:
`feature/member3-chat-file`. Ask at least one teammate to review and then merge.

**Avoid:** Everyone pushing directly to `main`, copying files through chat and
manually overwriting, or multiple members editing `app/common/protocol.py` at once.

## 4. Get new teammates' changes without overwriting your work

Commit your own changes first, then:

```bash
git switch main
git pull origin main
git switch feature/tv3-chat-file
git merge main
```

If Git says there is a conflict, **don't delete either version blindly**.
Check conflict markers, resolve with the owning teammate, run tests and commit
the resolution. This merge-based method is easier for beginners than rebasing.

## 5. Protocol and shared file rules

`app/common/config.py` / `app/common/protocol.py` and the `app/client.py`
callback interfaces affect several modules. An API change requires:

1. A short description in the team's GitHub issue/chat.
2. Review/approval by Member 1 (and Member 2 for packet changes).
3. Changes to `docs/protocol.md` and affected tests in the same PR.
4. Everybody pulls `main` after that PR is merged.

## 6. Integration checkpoints

- **M0:** Agree on packet/API, LAN ports, encryption key flow, rubric questions.
- **M1:** Two logins + user list + broadcast/private chat from real UI.
- **M2:** Real binary/empty file + SHA-256 receipt + AES-GCM in transit.
- **M3:** Loss/reordering/timeouts + sudden disconnect + 10-20 client test.
- **M4:** Fresh clone, reproduce on another machine, report diagrams and PDF.

The initial repository already provides a sample M1/M2 integration path,
**but that does not replace each teammate's code review and testing.**
