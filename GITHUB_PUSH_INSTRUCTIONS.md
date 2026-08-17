# Instructions: Create GitHub Repo and Push

Follow these steps when you're ready to put SysDigger on GitHub.
Everything is already committed locally and ready to push.

---

## Step 1: Create the repo on GitHub

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `SysDigger`
   - **Description**: `Windows system information and diagnostics viewer`
   - **Visibility**: **Public** (required for SignPath free signing)
   - **DO NOT** check "Add a README file"
   - **DO NOT** add .gitignore or license (both already exist in your code)
3. Click **Create repository**

## Step 2: Create a Personal Access Token (PAT)

GitHub no longer accepts passwords for Git operations. You need a token:

1. Go to https://github.com/settings/tokens
2. Click **Generate new token** → **Generate new token (classic)**
3. Fill in:
   - **Note**: `SysDigger push access`
   - **Expiration**: 90 days
   - **Scopes**: check **`repo`** (full repository access)
4. Click **Generate token**
5. **Copy the token immediately** — you won't see it again

## Step 3: Connect your local repo to GitHub

Open PowerShell and run:

```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysDigger"

# Connect to your GitHub repo
git remote add origin https://github.com/stavros-it/SysDigger.git

# Push your code
git push -u origin main
```

When prompted:
- **Username**: `stavros-it`
- **Password**: paste your **Personal Access Token** (not your GitHub password)

Windows Credential Manager will remember the token, so you only do this once.

### If you get "remote origin already exists"

```pwsh
git remote set-url origin https://github.com/stavros-it/SysDigger.git
git push -u origin main
```

### If authentication fails

Clear the old saved credential and try again:

```pwsh
cmdkey /delete:git:https://github.com
git push -u origin main
```

## Step 4: Verify

Go to https://github.com/stavros-it/SysDigger — you should see:
- All your files
- README.md displayed on the front page
- LICENSE file (Proprietary License)

## Step 5: Apply for free code signing (NOT available — app is proprietary)

> SignPath free signing requires an OSI-approved open-source license
> (MIT, Apache, etc.). Since SysDigger is now proprietary, the free
> SignPath workflow is **not available**.

Use one of these paid alternatives instead:
- **Azure Trusted Signing** (~$10/month) — Microsoft's managed signing
- **OV certificate** (~$200/year) — standard code signing
- **EV certificate** (~$400/year) — immediate SmartScreen reputation

See `GITHUB_SIGNING_GUIDE.md` and `BUILD_GUIDE.md` for details.

---

## The routine (after initial setup)

Every time you change code and want to update GitHub:

```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysDigger"

# Stage all changes
git add .

# Commit with a message
git commit -m "Description of what changed"

# Push to GitHub
git push
```

That's it. Three commands: `add` → `commit` → `push`.

### Publishing a new release

```pwsh
# Tag the version
git tag v4.12
git push origin v4.12
```

Then on GitHub:
1. Go to https://github.com/stavros-it/SysDigger/releases
2. Click **Draft a new release**
3. Select tag `v4.12`
4. Title: `SysDigger v4.12`
5. Describe changes
6. Click **Publish release**

The GitHub Actions workflow will automatically build the exe and (if SignPath is configured) submit it for signing.
