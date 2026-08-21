# Replace the existing repository without leaving old files behind

Old CI files must be deleted, not merely overwritten. The safest method is:

1. Extract this package **outside** your existing cloned repository.
2. Back up the existing repository.
3. Run one of the included replacement scripts.

macOS / Linux:

```bash
./tools/replace-existing-repo.sh /absolute/path/to/oppo-austria-ai-kaufberater
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\replace-existing-repo.ps1 -RepositoryPath "C:\path\to\oppo-austria-ai-kaufberater"
```

Then:

```bash
git add -A
git commit -m "Rebuild OPPO Austria AI Kaufberater complete baseline"
git push origin main
```

This preserves `.git` but removes every old working file, including obsolete GitHub Actions workflows.
