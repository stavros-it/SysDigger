# GitHub + SignPath Guide for SysDigger

A step-by-step guide for putting SysDigger on GitHub and getting it signed for free — written for someone who's comfortable with computers but new to Git/GitHub.

---

## What we're doing (the big picture)

1. **Put your code on GitHub** — so the world can see it (and SignPath can verify it)
2. **Set up GitHub Actions** — so GitHub's servers build the exe automatically when you tag a release
3. **Connect SignPath** — so the built exe gets signed automatically (after your approval)
4. **Publish a release** — so users can download the signed exe

You never build or sign on your own machine. GitHub builds it, SignPath signs it, users download it. Everything is free.

---

## Part 1: Install Git on your computer

Git is the tool that tracks code changes and uploads to GitHub. It's different from GitHub (the website).

### Step 1.1: Download and install Git

1. Go to https://git-scm.com/download/win
2. Download the **64-bit Git for Windows Setup**
3. Run the installer — accept all defaults (just click Next through every screen)
4. When it's done, open **PowerShell** and verify:
   ```pwsh
   git --version
   # git version 2.4x.x.windows.x
   ```

### Step 1.2: Tell Git who you are

Git needs your name and email (this gets attached to every commit, like a signature on a letter):

```pwsh
git config --global user.name "Stavros Antoniou"
git config --global user.email "your-email@example.com"
```

Use the same email you used to create your GitHub account.

### Step 1.3: Set your default branch name

GitHub uses `main` as the default branch (not `master`). Match it:

```pwsh
git config --global init.defaultBranch main
```

---

## Part 2: Create a GitHub repository

### Step 2.1: Create the repo on GitHub

1. Log in to https://github.com
2. Click the **+** icon (top-right) → **New repository**
3. Fill in:
   - **Repository name**: `SysDigger`
   - **Description**: `Windows system information and diagnostics viewer`
   - **Visibility**: Public (SignPath requires this — they only sign open-source projects)
   - **DO NOT** check "Add a README file" (we'll add one from your computer)
   - **DO NOT** add a .gitignore or license yet (we'll add them locally)
4. Click **Create repository**

GitHub shows you a page with instructions. Leave it open — we'll come back to it.

### Step 2.2: LICENSE file (already created — proprietary)

The `LICENSE` file in your SysDigger folder is already created with a
**proprietary** license (Copyright (c) 2026 Stavros Antoniou, All Rights
Reserved). No action needed here.

> **Important:** SignPath free signing requires an OSI-approved
> open-source license (MIT, Apache 2.0, etc.). Since the app is now
> proprietary, **SignPath free signing is NOT available**. Use one of the
> paid alternatives below:
> - **Azure Trusted Signing** (~$10/month) — Microsoft's managed signing
>   service, integrated with `signtool.exe` via the Trusted Signing
>   action
> - **OV (Organization Validation) certificate** (~$200/year from
>   DigiCert/Sectigo) — standard code signing cert; SmartScreen
>   reputation builds over ~100 downloads
> - **EV (Extended Validation) certificate** (~$400/year) — immediate
>   SmartScreen reputation; requires a hardware token
>
> The rest of this guide (GitHub repo setup, push workflow) still applies.
> Skip the SignPath-specific Parts 6 onwards and use the Azure Trusted
> Signing action in your workflow instead.

### Step 2.3: Create a .gitignore file

This tells Git which files NOT to upload (build output, temp files, caches):

Create a file called `.gitignore` (note the dot at the start) in your SysDigger folder with this content:

```
# Build output
build/
dist/
*.spec.bak

# Python cache
__pycache__/
*.pyc
*.pyo

# App runtime files
app.log
app.log.*
config.json
cache/
lib/lhm_standalone/

# IDE
.vscode/
.idea/
*.swp

# OS
Thumbs.db
desktop.ini
.DS_Store
```

> **Why exclude `config.json` and `app.log`?** These are runtime files — your personal settings and logs. They shouldn't be in the repo. Each user generates their own.

### Step 2.4: Create a README.md

If you don't have one, create `README.md` in your SysDigger folder. This is the front page of your GitHub repo. Keep it simple:

```markdown
# SysDigger

Windows system information and diagnostics viewer.

## Features

- Hardware info (CPU, GPU, memory, motherboard, disks, battery)
- Live sensors (temperatures, fan speeds, voltages) via LibreHardwareMonitor
- Network info, external IP, speed test
- Software, services, startup programs, Windows updates
- Processes (list + tree view)
- Devices (USB, Bluetooth, printers, audio)
- Diagnostics (event logs, BSOD history, DirectX, restore points)
- 27 maintenance tools (disk cleanup, SFC/DISM, hosts editor, etc.)

## Requirements

- Windows 10/11 (64-bit)
- Administrator privileges (for sensor access)
- .NET Framework 4.x (pre-installed on Windows 10/11)

## Download

Download the latest release from the [Releases page](../../releases).

## Build

See [BUILD_GUIDE.md](BUILD_GUIDE.md) for build and signing instructions.

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

- **Committers and reviewers**: [Contributors](../../graphs/contributors)
- **Approvers**: [Owner](https://github.com/StavrosAntoniou)

### Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

## License

Proprietary — Copyright (c) 2026 Stavros Antoniou. All rights reserved.
See [LICENSE](LICENSE) for details.
```

Replace `StavrosAntoniou` with your actual GitHub username.

---

## Part 3: Upload your code to GitHub

This is the core "Git workflow." You'll do this sequence every time you want to update your code.

### Step 3.1: Open PowerShell in your SysDigger folder

```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysDigger"
```

### Step 3.2: Initialize the Git repository

This creates a hidden `.git` folder that tracks changes:

```pwsh
git init
```

### Step 3.3: Stage all files

This tells Git "I want to include all these files in the next upload":

```pwsh
git add .
```

### Step 3.4: Check what will be uploaded

Before committing, always review what's staged:

```pwsh
git status
```

You should see green text listing your files. **Check that `config.json`, `app.log`, `cache/`, `lib/lhm_standalone/`, `build/`, and `dist/` are NOT listed** — if they are, your `.gitignore` isn't working.

If something is wrong, unstage everything and fix `.gitignore`:
```pwsh
git reset
# Edit .gitignore, then:
git add .
git status
```

### Step 3.5: Commit (save a snapshot)

This creates a permanent snapshot of your code with a message:

```pwsh
git commit -m "Initial commit — SysDigger v4.11"
```

### Step 3.6: Connect to your GitHub repo

Tell Git where to upload (replace `YOUR_USERNAME` with your GitHub username):

```pwsh
git remote add origin https://github.com/YOUR_USERNAME/SysDigger.git
```

If you get an error "remote origin already exists":
```pwsh
git remote set-url origin https://github.com/YOUR_USERNAME/SysDigger.git
```

### Step 3.7: Upload to GitHub

```pwsh
git push -u origin main
```

- `-u` tells Git to remember this connection (so next time you just type `git push`)
- `origin` is the nickname for your GitHub repo
- `main` is the branch name

You'll be asked to authenticate. GitHub no longer accepts passwords for Git — you need a **Personal Access Token**:

### Step 3.8: Create a Personal Access Token (PAT)

If `git push` asked for a password and failed:

1. Go to https://github.com/settings/tokens
2. Click **Generate new token** → **Generate new token (classic)**
3. Fill in:
   - **Note**: `SysDigger push access`
   - **Expiration**: 90 days (or whatever you prefer)
   - **Scopes**: check `repo` (full repository access)
4. Click **Generate token**
5. **Copy the token immediately** — you won't see it again
6. Go back to PowerShell and push again:
   ```pwsh
   git push -u origin main
   ```
   - Username: your GitHub username
   - Password: **paste the token** (not your GitHub password)

Windows Credential Manager will remember the token, so you only do this once.

### Step 3.9: Verify it worked

Go to https://github.com/YOUR_USERNAME/SysDigger — you should see all your files, the README displayed on the front page, and the LICENSE file.

---

## Part 4: The Git workflow (every time you update code)

You'll repeat this sequence whenever you change code and want to update GitHub. Memorize these 4 commands:

```pwsh
# 1. See what changed
git status

# 2. Stage all changes
git add .

# 3. Commit with a message describing what you did
git commit -m "Fixed sensor display bug"

# 4. Upload to GitHub
git push
```

That's it. Stage → Commit → Push. This is the entire Git workflow for a solo developer.

### If you change code on your computer and want to update GitHub

```pwsh
git add .
git commit -m "Description of what changed"
git push
```

### If you changed code on GitHub (e.g., edited a file in the browser)

```pwsh
git pull
```

This downloads changes from GitHub to your computer.

### If you want to undo changes you haven't committed yet

```pwsh
git checkout -- .    # discard all uncommitted changes
# OR
git checkout -- gui.py    # discard changes to one file
```

---

## Part 5: Apply for SignPath Foundation

SignPath provides free code signing for open-source projects. This is the "free cert" route.

### Step 5.1: Apply

1. Go to https://signpath.org/apply
2. Fill in:
   - **Project name**: SysDigger
   - **Repository URL**: `https://github.com/YOUR_USERNAME/SysDigger`
   - **License**: MIT
   - **Description**: Windows system information and diagnostics viewer with 27 maintenance tools. Built with Python/PySide6. Uses LibreHardwareMonitorLib for sensor data.
   - **Your role**: Maintainer
3. Submit and wait 1-2 weeks for review

### Step 5.2: While you wait — enable 2FA

SignPath requires all team members to use multi-factor authentication:

**On GitHub:**
1. Go to https://github.com/settings/security
2. Click **Enable two-factor authentication**
3. Choose either:
   - **Authenticator app** (recommended) — install Microsoft Authenticator or Google Authenticator on your phone, scan the QR code
   - **SMS** — enter your phone number

**Make sure you save your recovery codes** somewhere safe.

### Step 5.3: Wait for approval

SignPath reviews each application manually. You'll get an email when approved (or if they need more info). Don't build anything yet — wait for the approval email.

---

## Part 6: Set up SignPath (after approval)

### Step 6.1: Accept the SignPath invitation

You'll get an email from SignPath with a link to create your account. Log in at https://app.signpath.io/

### Step 6.2: Connect your GitHub repository

1. In SignPath, go to **Organizations** → select your organization
2. Go to **Projects** → **Add Project**
3. Fill in:
   - **Project name**: SysDigger
   - **Source control system**: GitHub
   - **Repository**: `YOUR_USERNAME/SysDigger`
4. Authorize the SignPath GitHub App (a popup will ask you to grant access)
5. Click **Create project**

### Step 6.3: Configure artifact settings

Tell SignPath which files to sign:

1. Go to your project → **Artifact Configurations** → **Add**
2. Name it `release-config`
3. Under **Files to sign**, add:
   - `SysDigger.exe`
   - `_internal\*.exe`
   - `_internal\*.dll`
4. Under **Metadata restrictions** (SignPath requires these):
   - Product name: `SysDigger` (enforced — all signed files must report this product name)
   - Product version: leave as "from file" (uses the version from `version.txt`)
5. Save

### Step 6.4: Configure signing policy

1. Go to **Signing Policies** → **Add**
2. Name it `release-signing`
3. **Signing method**: SignPath Foundation certificate
4. **Approver**: Your account (you'll approve each release manually)
5. **Artifact configuration**: `release-config`
6. Save

### Step 6.5: Get your API credentials

You'll need these for the GitHub Action:

1. Go to **Organizations** → your org → **API Tokens**
2. Click **Create API token**
3. Name it `GitHub Actions`
4. Copy the token value (you won't see it again)
5. Also note your **Organization ID** (shown on the organization page)

---

## Part 7: Set up GitHub Actions (automatic build + sign)

GitHub Actions is a CI/CD service that runs scripts on GitHub's servers. We'll create a workflow that builds SysDigger and asks SignPath to sign it, every time you publish a release.

### Step 7.1: Add secrets to your GitHub repo

1. Go to https://github.com/YOUR_USERNAME/SysDigger/settings/secrets/actions
2. Click **New repository secret**
3. Add two secrets:

   **Secret 1:**
   - Name: `SIGNPATH_API_TOKEN`
   - Value: (paste the API token from Step 6.5)

   **Secret 2:**
   - Name: `SIGNPATH_ORG_ID`
   - Value: (paste your Organization ID from Step 6.5)

### Step 7.2: Create the workflow file

In your SysDigger folder, create this directory structure:
```
SysDigger/
└── .github/
    └── workflows/
        └── build-and-sign.yml
```

Create the file `.github/workflows/build-and-sign.yml` with this content:

```yaml
name: Build and Sign

on:
  release:
    types: [published]

permissions:
  contents: write

jobs:
  build-and-sign:
    runs-on: windows-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Compile check
        run: python -m py_compile app.py gui.py collectors.py sysdigger.pyw tools.py sensors.py helpers.py config.py lhm_process.py updater.py app_logger.py paths.py

      - name: Build with PyInstaller
        run: pyinstaller sysdigger.spec --noconfirm --clean

      - name: Zip the build
        run: |
          cd dist
          Compress-Archive -Path SysDigger\* -DestinationPath ..\SysDigger-${{ github.event.release.tag_name }}.zip
          cd ..

      - name: Submit to SignPath for signing
        id: signpath
        uses: signpath/github-action-submit-signing-request@v1
        with:
          api-token: ${{ secrets.SIGNPATH_API_TOKEN }}
          organization-id: ${{ secrets.SIGNPATH_ORG_ID }}
          project-slug: SysDigger
          signing-policy-slug: release-signing
          artifact-configuration-slug: release-config
          github-artifact-id: ${{ github.event.release.tag_name }}
          wait-for-completion: true
          output-artifact-directory: signed

      - name: Upload signed zip to release
        uses: softprops/action-gh-release@v2
        with:
          files: signed/SysDigger-${{ github.event.release.tag_name }}.zip

      - name: Upload unsigned zip (fallback)
        if: failure()
        uses: softprops/action-gh-release@v2
        with:
          files: SysDigger-${{ github.event.release.tag_name }}.zip
```

### Step 7.3: Upload the workflow to GitHub

```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysDigger"
git add .
git commit -m "Add GitHub Actions build-and-sign workflow"
git push
```

### Step 7.4: Verify the workflow appears on GitHub

Go to https://github.com/YOUR_USERNAME/SysDigger/actions — you should see "Build and Sign" listed as a workflow. It won't run yet (it only runs when you publish a release).

---

## Part 8: Publish a release

This triggers the build + sign pipeline.

### Step 8.1: Tag your code with a version number

In PowerShell:
```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysDigger"
git tag v4.11
git push origin v4.11
```

### Step 8.2: Create the release on GitHub

1. Go to https://github.com/YOUR_USERNAME/SysDigger/releases
2. Click **Draft a new release**
3. **Choose a tag**: select `v4.11` (or type it if it doesn't appear)
4. **Release title**: `SysDigger v4.11`
5. **Description**: Copy the version history from `roadmap.md`:
   ```
   ## What's New in v4.11

   - Motherboard sensors via portable LHM.exe bridge (fan RPM, voltages, VRM temps)
   - Storage cleanup tools (disk analyzer, Appx manager, dev cache cleaner, hibernate manager)
   - Unified GPU tab with live metrics for any GPU vendor
   - Sparkline graph rendering fix
   - 22 code audit fixes (thread safety, resource leaks, portability)
   - PyInstaller packaging support with code signing
   ```
6. Click **Publish release**

### Step 8.3: Watch the build

1. Go to https://github.com/YOUR_USERNAME/SysDigger/actions
2. You'll see a new run titled "Build and Sign"
3. Click it to watch the progress:
   - Checkout code ✓
   - Set up Python ✓
   - Install dependencies ✓ (takes 1-2 minutes)
   - Compile check ✓
   - Build with PyInstaller ✓ (takes 2-5 minutes)
   - Zip the build ✓
   - Submit to SignPath for signing ⏳ (pauses here waiting for SignPath)

The build takes 5-10 minutes total.

### Step 8.4: Approve the signing request

When the workflow reaches "Submit to SignPath," you'll get an email from SignPath:

1. Click the link in the email
2. Log in to https://app.signpath.io/
3. Review the signing request:
   - Check the project name: SysDigger
   - Check the files to be signed
   - Check the source commit hash (verifies it matches your GitHub repo)
4. Click **Approve**

The signing takes 1-2 minutes. SignPath signs on their HSM and uploads the signed zip back to your GitHub release.

### Step 8.5: Download the signed release

1. Go to https://github.com/YOUR_USERNAME/SysDigger/releases
2. You'll see `SysDigger-v4.11.zip` attached to the release
3. Download it, extract, and run `SysDigger.exe`
4. Windows should show "Verified publisher: SignPath Foundation" (no SmartScreen warning after reputation builds up)

### Step 8.6: Verify the signature

```pwsh
signtool verify /pa /v SysDigger.exe
```

Should output:
```
Signing Certificate Chain:
    CN=SignPath Foundation
    ...
Successfully verified: SysDigger.exe
```

---

## Part 9: Updating your app (the routine)

Every time you fix a bug or add a feature and want to publish a new signed release:

### Step 9.1: Update code on your computer

Edit files as usual.

### Step 9.2: Bump the version

1. In `gui.py`, find the version label and bump it:
   ```python
   ver = QLabel("Version 4.12")  # was 4.11
   ```
2. In `version.txt`, update the version numbers:
   ```
   filevers=(4, 12, 0, 0),
   prodvers=(4, 12, 0, 0),
   ```

### Step 9.3: Commit and push

```pwsh
git add .
git commit -m "v4.12 — description of changes"
git push
```

### Step 9.4: Tag and release

```pwsh
git tag v4.12
git push origin v4.12
```

Then on GitHub:
1. Go to Releases → Draft a new release
2. Select tag `v4.12`
3. Title: `SysDigger v4.12`
4. Describe changes
5. Publish release

The build + sign pipeline runs automatically. Approve on SignPath when the email arrives. Done.

---

## Troubleshooting

### `git push` says "Authentication failed"

Your Personal Access Token expired or was lost. Create a new one:
1. Go to https://github.com/settings/tokens
2. Generate new token (classic) with `repo` scope
3. Push again — when asked for password, paste the new token

To update the saved credential on Windows:
```pwsh
# Clear the old credential
cmdkey /delete:git:https://github.com
# Push again — it will ask for username + token
git push
```

### GitHub Actions build fails at "Install dependencies"

Check the build log — click the failed step to see the error. Common causes:
- Missing package in `requirements.txt`
- Package version incompatible with the GitHub Actions runner

### GitHub Actions build fails at "Build with PyInstaller"

Check if `sysdigger.spec` is valid. Common issues:
- Path to `app.ico` not found (the icon must be in the repo)
- `lib/` directory not committed (but it should be — the DLLs need to be in the repo for the build to work)

> **Important:** The `lib/` directory with the LHM DLLs MUST be committed to your repo (don't add it to `.gitignore`). Without these DLLs, the build will fail. They're about 3 MB total.

If you excluded `lib/` in `.gitignore`, remove that line and push:
```pwsh
# Edit .gitignore — remove the line "lib/lhm_standalone/"
# Keep "lib/lhm_standalone/" excluded (that's the downloaded LHM.exe, not the DLLs)
git add .gitignore lib/
git commit -m "Add LHM DLLs to repo for builds"
git push
```

### SignPath signing request fails

Check the SignPath dashboard for the error. Common causes:
- Artifact configuration doesn't match (file paths wrong)
- Metadata restriction failed (product name in exe doesn't match "SysDigger")
- You tried to sign a binary that wasn't built from the verified source code

### The signed exe still shows SmartScreen warning

This is expected for the first ~100 downloads. SignPath uses an OV certificate (not EV), so SmartScreen reputation builds gradually. Users click "More info" → "Run anyway". After enough downloads, the warning stops.

There's no way to speed this up for free. An EV cert ($200-300/year) gives immediate SmartScreen trust.

### The build succeeds but the zip isn't attached to the release

Check the "Upload signed zip to release" step in the Actions log. Common issue: the `softprops/action-gh-release` action needs `permissions: contents: write` (already included in the workflow above).

---

## Quick reference: The 5-minute update workflow

After your initial setup is done, here's the routine for every new release:

```pwsh
# 1. Make your code changes
# 2. Bump version in gui.py and version.txt
# 3. Commit and push
git add .
git commit -m "v4.12 — fixed X, added Y"
git push

# 4. Tag the release
git tag v4.12
git push origin v4.12

# 5. Go to GitHub → Releases → Draft new release → select tag v4.12 → Publish
# 6. Wait for the email from SignPath → Approve on app.signpath.io
# 7. Download the signed zip from the GitHub release page
```

Total active time: ~5 minutes. Build + sign wait: ~10 minutes.
