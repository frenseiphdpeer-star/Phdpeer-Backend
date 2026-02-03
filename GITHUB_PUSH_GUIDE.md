# GitHub Push Guide - Complete Instructions

## Current Situation
- ✅ Code is committed locally (commit: `cb45dc3`)
- ❌ Push failing due to authentication issues

## Repository
- URL: `https://github.com/frenseiphdpeer-star/Phdpeer-Backend.git`
- Type: Organization repository

## Solutions

### Option 1: HTTPS with Personal Access Token (Recommended)

**Step 1: Create/Regenerate Token with Correct Scopes**

1. Go to: https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Name: `Frensei-Engine-Push`
4. **IMPORTANT: Check these scopes:**
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (if using GitHub Actions)
5. Click **"Generate token"**
6. **COPY THE TOKEN** immediately

**Step 2: Push Using Token**

```powershell
cd d:\Frensei-Engine
git push origin main
```

When prompted:
- **Username:** `Uttkarsh700` (or your GitHub username)
- **Password:** `<paste your token here>` (NOT your GitHub password)

**Or use token in URL (one-time):**
```powershell
git remote set-url origin https://YOUR_TOKEN@github.com/frenseiphdpeer-star/Phdpeer-Backend.git
git push origin main
git remote set-url origin https://github.com/frenseiphdpeer-star/Phdpeer-Backend.git
```

### Option 2: SSH Authentication

**Step 1: Generate SSH Key**
```powershell
ssh-keygen -t ed25519 -C "your_email@example.com"
# Press Enter to accept default location
# Optionally set a passphrase
```

**Step 2: Add SSH Key to GitHub**
1. Copy your public key:
   ```powershell
   Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
   ```
2. Go to: https://github.com/settings/keys
3. Click **"New SSH key"**
4. Paste the key and save

**Step 3: Test Connection**
```powershell
ssh -T git@github.com
```

**Step 4: Push**
```powershell
cd d:\Frensei-Engine
git remote set-url origin git@github.com:frenseiphdpeer-star/Phdpeer-Backend.git
git push origin main
```

### Option 3: Request Organization Access

If the repository is part of an organization:

1. Ask the repository owner to:
   - Add you as a collaborator with **write** access
   - Or grant your token organization access

2. Organization settings:
   - Go to organization settings
   - Third-party access → Personal access tokens
   - Approve your token for the organization

### Option 4: Fork and Pull Request

If you can't get direct access:

1. **Fork the repository** on GitHub
2. **Update remote to your fork:**
   ```powershell
   git remote set-url origin https://github.com/YOUR_USERNAME/Phdpeer-Backend.git
   git push origin main
   ```
3. **Create Pull Request** from your fork to the main repository

## Troubleshooting

### Error: "Permission denied"
- Token doesn't have `repo` scope → Regenerate token with `repo` checked
- Organization restrictions → Request organization access

### Error: "Publickey authentication failed"
- SSH key not added to GitHub → Add key at https://github.com/settings/keys
- Wrong SSH key → Check with `ssh -T git@github.com`

### Error: "Repository not found"
- Check repository URL is correct
- Verify you have access to the repository

## What's Ready to Push

Your commit includes:
- ✅ 68 files changed
- ✅ 9,850+ lines added
- ✅ Frontend architecture (API client, state, guards)
- ✅ All pages (upload, timeline, progress, assessment, dashboard)
- ✅ Debug instrumentation
- ✅ Documentation and guides

**Commit hash:** `cb45dc3`

## Quick Command Reference

```powershell
# Check status
git status

# View commit
git log --oneline -1

# Push (will prompt for credentials)
git push origin main

# Check remote
git remote -v
```
