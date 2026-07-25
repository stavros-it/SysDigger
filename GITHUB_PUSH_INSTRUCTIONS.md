# Instructions: Create GitHub Repo and Push

Follow these steps when you're ready to put SysPeek on GitHub.
Everything is already committed locally and ready to push.

---

## Step 1: Create the repo on GitHub

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `SysPeek`
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
   - **Note**: `SysPeek push access`
   - **Expiration**: 90 days
   - **Scopes**: check **`repo`** (full repository access)
4. Click **Generate token**
5. **Copy the token immediately** — you won't see it again

## Step 3: Connect your local repo to GitHub

Open PowerShell and run:

```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysPeek"

# Connect to your GitHub repo
git remote add origin https://github.com/stavros-it/SysPeek.git

# Push your code
git push -u origin main
```

When prompted:
- **Username**: `stavros-it`
- **Password**: paste your **Personal Access Token** (not your GitHub password)

Windows Credential Manager will remember the token, so you only do this once.

### If you get "remote origin already exists"

```pwsh
git remote set-url origin https://github.com/stavros-it/SysPeek.git
git push -u origin main
```

### If authentication fails

Clear the old saved credential and try again:

```pwsh
cmdkey /delete:git:https://github.com
git push -u origin main
```

## Step 4: Verify

Go to https://github.com/stavros-it/SysPeek — you should see:
- All your files
- README.md displayed on the front page
- LICENSE file (MIT License)

## Step 5: Apply for free code signing (optional, do this later)

1. Go to https://signpath.org/apply
2. Fill in:
   - **Project name**: SysPeek
   - **Repository URL**: `https://github.com/stavros-it/SysPeek`
   - **License**: MIT
   - **Description**: Windows system information and diagnostics viewer with 26 maintenance tools. Built with Python/PySide6. Uses LibreHardwareMonitorLib for sensor data.
3. Wait 1-2 weeks for approval email
4. Follow `GITHUB_SIGNING_GUIDE.md` Part 6 onwards to complete SignPath setup

---

## The routine (after initial setup)

Every time you change code and want to update GitHub:

```pwsh
cd "C:\Users\Stavros\OneDrive\My AI Apps\SysPeek"

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
1. Go to https://github.com/stavros-it/SysPeek/releases
2. Click **Draft a new release**
3. Select tag `v4.12`
4. Title: `SysPeek v4.12`
5. Describe changes
6. Click **Publish release**

The GitHub Actions workflow will automatically build the exe and (if SignPath is configured) submit it for signing.
