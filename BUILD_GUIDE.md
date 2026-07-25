# SysPeek Build & Signing Guide

This guide walks you through building SysPeek as a signed Windows executable suitable for enterprise deployment.

---

## Prerequisites

### 1. Install Python 3.12+

Download from https://www.python.org/downloads/windows/

During installation, check **"Add Python to PATH"**.

Verify:
```pwsh
python --version
# Python 3.12.x
```

### 2. Install dependencies

```pwsh
cd "C:\path\to\SysPeek"
python -m pip install -r requirements.txt
```

This installs: `psutil`, `requests`, `wmi`, `pywin32`, `pythonnet`, `PySide6`, `pyinstaller`.

### 3. Verify the app runs from source

```pwsh
pythonw syspeek.pyw
```

You should see the SysPeek window with all pages populated. If it works, you're ready to build.

---

## Option A: Build WITHOUT signing (quick test)

Use this if you just want to test the exe locally or distribute internally without a certificate.

```pwsh
cd "C:\path\to\SysPeek"
.\build.ps1
```

If PowerShell blocks the script:
```pwsh
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

The build takes 2-5 minutes. Output is in `dist\SysPeek\`:

```
dist/
└── SysPeek/
    ├── SysPeek.exe          ← the main executable (run this)
    ├── _internal/            ← DLLs, Python runtime, PySide6, etc.
    │   ├── lib/              ← LibreHardwareMonitorLib DLLs
    │   ├── icons/            ← nav + category icons
    │   ├── tools source/     ← PowerShell tool library
    │   └── ...
    └── ...
```

**To run:** Double-click `SysPeek.exe` (or `dist\SysPeek\SysPeek.exe`). Windows will show a UAC prompt (admin required for sensors).

**To distribute:** Zip the entire `dist\SysPeek\` folder. Users extract and run `SysPeek.exe`.

> ⚠️ **Without signing, Windows SmartScreen will warn users** the first time they run the exe ("Windows protected your PC"). Users must click "More info" → "Run anyway". This is expected for unsigned exes.

---

## Option B: Build WITH signing (enterprise-ready)

### Step 1: Get a code signing certificate

You need a code signing certificate from a trusted Certificate Authority (CA). Options:

| Provider | Type | Cost | SmartScreen | Best for |
|---|---|---|---|---|
| **SignPath Foundation** | OV (free for OSS) | **FREE** | Builds reputation over time | Open-source projects |
| **Azure Trusted Signing** | Cloud HSM | ~$10/month | Builds reputation over time | Solo devs, small teams |
| **SSL.com** | EV cert (USB token) | ~$200/year | Immediate reputation | Immediate trust needed |
| **DigiCert** | EV cert (USB token) | ~$300/year | Immediate reputation | Enterprise |
| **Sectigo** | OV cert | ~$170/year | Builds reputation over time | Budget option |

> 💡 **See Option C below for the completely free SignPath route** (requires open-sourcing the project on GitHub).

**Recommended: Azure Trusted Signing** — cheapest paid option, no USB token, cloud-based signing.

**Recommended (free): SignPath Foundation** — if you're willing to open-source SysPeek on GitHub. See Option C below.

#### Azure Trusted Signing setup

1. Create an Azure account at https://portal.azure.com
2. Subscribe to "Trusted Signing" service
3. Create a signing account
4. Register your identity (business verification — takes 1-3 days)
5. Create an app registration (for API access)
6. Note these values:
   - **Endpoint**: `https://<your-account>.eus.codesigning.azure.net/`
   - **App ID** (Client ID)
   - **Tenant ID**
   - **Client Secret**
   - **Certificate name** (e.g. "SysPeek")

Install AzureSignTool:
```pwsh
dotnet tool install --global AzureSignTool
```

#### Traditional cert (OV/EV USB token) setup

1. Purchase cert from DigiCert/SSL.com/Sectigo
2. Complete identity verification
3. Receive USB token (or download cert for OV)
4. Install cert into Windows Certificate Store:
   - Insert USB token
   - Open `certmgr.msc` → Personal → Certificates
   - Find your cert, note the **Thumbprint** (right-click → Properties → Details → Thumbprint)
5. Install `signtool.exe` (comes with Windows SDK):
   ```pwsh
   # If not already installed:
   # Download Windows 10/11 SDK from:
   # https://developer.microsoft.com/windows/downloads/windows-sdk/
   # Select only "Signing Tools for Desktop" during install
   ```

### Step 2: Configure the signing environment

#### For Azure Trusted Signing

Set these environment variables (or save to a `.env` file you source before building):

```pwsh
# PowerShell — run before building
$env:AZ_SIGN_ENDPOINT = "https://youraccount.eus.codesigning.azure.net/"
$env:AZ_SIGN_APP_ID   = "your-app-id-guid"
$env:AZ_SIGN_TENANT   = "your-tenant-id-guid"
$env:AZ_SIGN_SECRET   = "your-client-secret"
$env:AZ_SIGN_CERT     = "SysPeek"
```

#### For traditional cert (DigiCert/SSL.com/Sectigo)

Find your cert thumbprint:
```pwsh
# List all code signing certs in your Personal store
Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.EnhancedKeyUsageList -match "Code Signing"
} | Format-List Subject, Thumbprint
```

Copy the **Thumbprint** value (a 40-char hex string like `A1B2C3D4E5...`).

Set it as an environment variable:
```pwsh
$env:SIGN_CERT_THUMBPRINT = "A1B2C3D4E5F6..."
```

### Step 3: Build and sign

#### Azure Trusted Signing

The included `build.ps1` uses `signtool.exe` (for traditional certs). For Azure Trusted Signing, use this modified build command:

```pwsh
# 1. Build
.\build.ps1

# 2. Sign with AzureSignTool
$files = Get-ChildItem -Recurse ".\dist\SysPeek" -Include *.exe, *.dll
foreach ($f in $files) {
    Write-Host "Signing: $($f.Name)"
    azuresigntool sign `
        -kvu $env:AZ_SIGN_ENDPOINT `
        -kvi $env:AZ_SIGN_APP_ID `
        -kvt $env:AZ_SIGN_TENANT `
        -kvs $env:AZ_SIGN_SECRET `
        -kvc $env:AZ_SIGN_CERT `
        -tr http://timestamp.digicert.com `
        -v $f.FullName
}
```

#### Traditional cert (DigiCert/SSL.com/Sectigo)

```pwsh
$env:SIGN_CERT_THUMBPRINT = "your-thumbprint-here"
.\build.ps1
```

`build.ps1` automatically signs all `.exe` and `.dll` files in the output with `signtool.exe` using SHA-256 + RFC 3161 timestamping.

### Step 4: Verify the signature

```pwsh
# Check the main exe
signtool verify /pa /v .\dist\SysPeek\SysPeek.exe

# Should output:
# Successfully verified: ...SysPeek.exe
```

You can also right-click `SysPeek.exe` → Properties → Digital Signatures tab to see the certificate.

---

## Option C: Sign for FREE with SignPath Foundation (open-source projects)

[SignPath Foundation](https://signpath.org/) provides **free code signing certificates** for open-source projects. The cert is issued to "SignPath Foundation" and signed binaries are verified as originating from your GitHub repository. No payment, no USB token, no recurring fees.

### Requirements (read carefully)

SignPath Foundation is selective about which projects they accept. You must meet ALL of these:

1. **Open-source license** — Your project must use an [OSI-approved license](https://opensource.org/licenses) (MIT, Apache 2.0, GPL, BSD, etc.) for ALL components, with no commercial dual-licensing
2. **No proprietary code** — All code must be open source, including build scripts. You may include system libraries (DLLs, runtimes) in signed packages
3. **Actively maintained** — The project must have recent commits and be actively developed
4. **Already released** — The project must already have a public release (not just a repo with code)
5. **Documented** — The project's functionality must be described on a download/readme page
6. **No hacking tools** — Software must not include features that exploit security vulnerabilities or circumvent security measures
7. **Reputation** — SignPath must be comfortable with the project's reputation (they review this manually)
8. **MFA required** — All team members must use multi-factor authentication on GitHub and SignPath

### Step 1: Open-source your project on GitHub

1. Create a GitHub repository for SysPeek (if not already done)
2. Add an OSI-approved license file (e.g., `LICENSE` with MIT or Apache 2.0)
3. Add a `README.md` describing the project
4. Make sure all code is committed (no proprietary/private code held back)
5. Create a GitHub release (tag a version, e.g., `v4.11`)

### Step 2: Add a code signing policy

Add a "Code signing policy" section to your `README.md` or a `SIGNING.md` file:

```markdown
## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

- **Committers and reviewers**: [Members team](https://github.com/YOUR_USERNAME/SysPeek/graphs/contributors)
- **Approvers**: [Owners](https://github.com/YOUR_USERNAME/SysPeek)

### Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.
```

Replace `YOUR_USERNAME` with your GitHub username.

### Step 3: Apply at SignPath Foundation

Go to https://signpath.org/apply and fill out the application:

- **Project name**: SysPeek
- **Repository URL**: https://github.com/YOUR_USERNAME/SysPeek
- **License**: MIT (or whatever you chose)
- **Description**: Windows system information and diagnostics viewer
- **Team members**: Your GitHub username(s)

Approval takes 1-2 weeks (manual review).

### Step 4: Set up SignPath.io

Once approved, you'll get access to [SignPath.io](https://about.signpath.io):

1. **Connect your GitHub repo** — SignPath integrates via a GitHub App that watches for releases
2. **Configure artifact settings** — Tell SignPath which files to sign (`SysPeek.exe`, all DLLs in `_internal/`)
3. **Set metadata restrictions** — Configure product name ("SysPeek") and version to be enforced on all signed files
4. **Define build pipeline** — SignPath can either:
   - **Option A**: Build automatically via GitHub Actions on every release tag, then sign automatically
   - **Option B**: You build locally, upload the artifacts, and manually request signing (requires approval by a designated team member)

### Step 5: Build and sign via GitHub Actions (recommended)

Create `.github/workflows/build-and-sign.yml` in your repo:

```yaml
name: Build and Sign

on:
  release:
    types: [published]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Build
        run: .\build.ps1
        shell: pwsh

      - name: Sign with SignPath
        uses: signpath/github-action-submit-signing-request@v1
        with:
          api-token: ${{ secrets.SIGNPATH_API_TOKEN }}
          organization-id: ${{ secrets.SIGNPATH_ORG_ID }}
          project-slug: syspeek
          signing-policy-slug: release-signing
          artifact-configuration-slug: release-config
          github-artifact-id: ${{ github.event.release.tag_name }}
          wait-for-completion: true
          output-artifact-directory: dist\signed

      - name: Upload to release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/signed/SysPeek-*.zip
```

Set these GitHub secrets (from your SignPath dashboard):
- `SIGNPATH_API_TOKEN` — your API token
- `SIGNPATH_ORG_ID` — your organization ID

### Step 6: Approve the signing request

Each release requires manual approval by a designated "Approver" (you can be the approver for solo projects). You'll get an email when a signing request is pending. Log into SignPath.io, review, and approve.

Once approved, SignPath signs the artifacts on their HSM and uploads them back to your GitHub release automatically.

### Step 7: Verify the signature

Download the signed release and verify:
```pwsh
signtool verify /pa /v SysPeek.exe
```

Should show:
```
Signing Certificate Chain:
    CN=SignPath Foundation
    ...
Successfully verified: SysPeek.exe
```

### SignPath limitations (be aware)

| Aspect | Detail |
|---|---|
| **SmartScreen** | SignPath uses an OV cert, so SmartScreen reputation builds over time (~100+ downloads before warnings stop). For immediate SmartScreen trust, you'd still need an EV cert (~$200+/year). |
| **Manual approval** | Every release needs a human to click "Approve" in SignPath.io — no fully automated CI/CD |
| **Build from source** | SignPath verifies the binary was built from your repo's source code. You can't sign arbitrary binaries — they must come from a verifiable build |
| **Review process** | SignPath reviews your project manually before approval. Smaller/newer projects may be rejected if they lack reputation |
| **Certificate name** | The cert says "SignPath Foundation" as the publisher, not your name/company. Users see "Verified publisher: SignPath Foundation" |

### Alternative: Self-signed certificate (free, NOT for distribution)

If you just want to test the signing flow locally (NOT for distributing to others — SmartScreen will always block self-signed exes):

```pwsh
# 1. Create a self-signed code signing cert
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject "CN=SysPeek Dev" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyAlgorithm RSA -KeyLength 2048 `
    -NotAfter (Get-Date).AddYears(1)

# 2. Build (unsigned)
.\build.ps1

# 3. Sign with your self-signed cert
$thumb = $cert.Thumbprint
Get-ChildItem -Recurse ".\dist\SysPeek" -Include *.exe, *.dll | ForEach-Object {
    signtool sign /fd sha256 /sha1 $thumb $_.FullName
}

# 4. (Optional) Make Windows trust your self-signed cert (dev machine only)
# Add to Trusted Root CAs:
$certPath = "Cert:\CurrentUser\My\$thumb"
Export-Certificate -Cert $certPath -FilePath SysPeekDev.cer
Import-Certificate -FilePath SysPeekDev.cer -CertStoreLocation "Cert:\LocalMachine\Root"
```

> ⚠️ **Self-signed certs are ONLY useful for testing on your own machine.** Other users will see "Unknown publisher" warnings. For public distribution, use SignPath (free, OSS) or a paid cert.

---

## Step 5: Package for distribution

### Zip (simplest)

```pwsh
Compress-Archive `
    -Path .\dist\SysPeek\* `
    -DestinationPath .\dist\SysPeek-4.11.zip `
    -Force
```

Distribute the zip. Users extract and run `SysPeek.exe`.

### MSI installer (enterprise SCCM/Intune)

For enterprise deployment via SCCM or Microsoft Intune, wrap the `--onedir` output in an MSI:

1. Install WiX Toolset: https://wixtoolset.org/releases/
2. Create `SysPeek.wxs` (WiX source file):
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
     <Package Name="SysPeek" Version="4.11.0.0" Manufacturer="Stavros Antoniou"
              Language="1033" Codepage="1252" UpgradeCode="YOUR-GUID-HERE">
       <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
       <Media Id="1" Cabinet="SysPeek.cab" EmbedCab="yes" />
       <Directory Id="TARGETDIR" Name="SourceDir">
         <Directory Id="ProgramFilesFolder">
           <Directory Id="INSTALLDIR" Name="SysPeek">
             <Component Id="MainFiles" Guid="*" KeyPath="yes">
               <File Id="SysPeekExe" Source="dist\SysPeek\SysPeek.exe" />
               <!-- Add all other files/dirs here, or use heat.exe -->
             </Component>
           </Directory>
         </Directory>
       </Directory>
       <Feature Id="Complete" Level="1">
         <ComponentRef Id="MainFiles" />
       </Feature>
     </Package>
   </Wix>
   ```
3. Build the MSI:
   ```pwsh
   wix build SysPeek.wxs -o SysPeek-4.11.0.msi
   ```
4. Sign the MSI:
   ```pwsh
   signtool sign /fd sha256 /td sha256 /tr http://timestamp.digicert.com `
       /sha1 $env:SIGN_CERT_THUMBPRINT SysPeek-4.11.0.msi
   ```

Deploy via SCCM/Intune using the MSI.

---

## How the build works

### `build.ps1` pipeline

```
1. pip install -r requirements.txt      ← install/upgrade deps
2. python -m py_compile ...             ← check for syntax errors
3. Remove-Item build, dist               ← clean previous build
4. pyinstaller syspeek.spec              ← build the exe
5. signtool sign (if cert available)    ← sign all exe/dll
```

### `syspeek.spec` (PyInstaller config)

| Setting | Value | Why |
|---|---|---|
| Mode | `--onedir` | Faster startup (~1s vs 3-8s for onefile), lower AV false-positives |
| `uac_admin` | `True` | Manifest requests elevation — no self-relaunch needed |
| `runtime_hooks` | `runtime_hook.py` | Sets `os.chdir(exe_dir)` + `QT_PLUGIN_PATH` |
| `hiddenimports` | pythonnet, PySide6, wmi, etc. | PyInstaller can't auto-trace these |
| `datas` | `app.ico`, `icons/`, `tools source/`, `lib/*.dll` | Bundled read-only assets |
| `excludes` | tkinter, test, unittest | Smaller output |
| `version` | `version.txt` | Windows file properties (right-click → Details) |

### `paths.py` (frozen-exe path resolution)

When running as a script, all paths resolve to the script directory.

When frozen as exe:
- **`resource_dir()`** → `sys._MEIPASS` (PyInstaller's temp extraction dir) — for read-only assets (icons, DLLs, PowerShell lib)
- **`data_dir()`** → exe directory if writable, else `%LOCALAPPDATA%\SysPeek` — for writable data (config.json, app.log, cache/, LHM.exe download)

This means the exe works from:
- A USB stick (writable → portable mode)
- `C:\Program Files\SysPeek\` (read-only → data goes to `%LOCALAPPDATA%\SysPeek`)
- A network share (read-only → data goes to `%LOCALAPPDATA%\SysPeek`)

### `runtime_hook.py`

Runs before any Python code. Sets the working directory to the exe's location so relative paths work correctly.

---

## Troubleshooting

### "PowerShell execution policy" error

```pwsh
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Build fails with "ModuleNotFoundError"

Ensure all deps are installed:
```pwsh
python -m pip install -r requirements.txt --upgrade
```

Verify critical imports:
```pwsh
python -c "import psutil, requests, wmi, pythoncom, PySide6, clr; print('OK')"
```

### App crashes on launch with "Failed to load platform plugin windows"

PySide6 plugins weren't bundled. Ensure `runtime_hook.py` sets `QT_PLUGIN_PATH`:
```python
os.environ["QT_PLUGIN_PATH"] = os.path.join(sys._MEIPASS, "PySide6", "plugins")
```

### "pythonnet" / "clr" fails to load

pythonnet requires .NET Framework 4.x on the target machine. Windows 10/11 includes this by default. On older Windows or stripped-down enterprise images, install .NET Framework 4.8 runtime:
https://dotnet.microsoft.com/download/dotnet-framework/net48

### Sensors don't work (no motherboard temps/fans)

The exe needs admin (for the PawnIO kernel driver). The `uac_admin=True` in the spec handles this — Windows shows a UAC prompt on launch. If UAC is disabled or the user clicks "No", sensors won't work.

LHM.exe is downloaded on first launch (~6.6 MB from GitHub). In air-gapped environments, pre-bundle `lib/lhm_standalone/` by copying the cached files into the exe's `_internal\lib\lhm_standalone\` directory.

### Signing fails with "signtool not found"

Install Windows SDK (select "Signing Tools for Desktop"):
https://developer.microsoft.com/windows/downloads/windows-sdk/

Or find it in:
```
C:\Program Files (x86)\Windows Kits\10\bin\10.0.xxxxx.0\x64\signtool.exe
```

### Signing fails with "no certificate found"

Ensure the cert is in the Windows Certificate Store:
```pwsh
Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.EnhancedKeyUsageList -match "Code Signing"
}
```

If empty, import the cert:
```pwsh
Import-PfxCertificate -FilePath "your-cert.pfx" -CertStoreLocation Cert:\CurrentUser\My
```

For EV certs on USB tokens, install the manufacturer's middleware (SafeNet, etc.) and ensure the token is inserted.

### SmartScreen still warns after signing

OV certs build reputation over time (users click "Run anyway" → after ~100 downloads, warnings stop). For immediate reputation, use an **EV cert** — SmartScreen trusts EV-signed exes immediately.

---

## Quick reference

| Option | Cost | SmartScreen | Requirements |
|---|---|---|---|
| **Option A** — Build unsigned | Free | ⚠️ Warns users | None |
| **Option B** — Paid cert (Azure/DigiCert) | $10-300/yr | ✅ EV = immediate, OV = builds over time | Code signing cert |
| **Option C** — SignPath Foundation | **Free** | ⚠️ Builds over time | Open-source on GitHub, approval |

### Build (unsigned — quick test)
```pwsh
.\build.ps1
```

### Build + sign (free — SignPath for open source)
```pwsh
# 1. Open-source SysPeek on GitHub
# 2. Apply at https://signpath.org/apply
# 3. Add .github/workflows/build-and-sign.yml (see Option C, Step 5)
# 4. Tag a release: git tag v4.11 && git push --tags
# 5. Approve signing request at SignPath.io
```

### Build + sign (traditional cert — paid)
```pwsh
$env:SIGN_CERT_THUMBPRINT = "your-thumbprint"
.\build.ps1
```

### Build + sign (Azure Trusted Signing — paid)
```pwsh
.\build.ps1
# Then sign with AzureSignTool (see Option B, Step 3)
```

### Build + sign (self-signed — testing only)
```pwsh
# Create cert, build, sign (see Option C, Alternative section)
.\build.ps1
# Then sign with signtool using self-signed cert thumbprint
```

### Verify signature
```pwsh
signtool verify /pa /v .\dist\SysPeek\SysPeek.exe
```

### Test the built exe
```pwsh
.\dist\SysPeek\SysPeek.exe
```
