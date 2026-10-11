name: windows-powershell
triggers: powershell, windows, backslash, start-process, wait-process, venv, pip install, encoding, path, get-childitem
- No `&&`; chain with `;`. Never end a quoted path with a backslash. Use `python -m <module>`.
- `$env:PYTHONUTF8=1` before any script that reads or writes text. Use `pathlib`, not string paths.
- `Select-String -Path <glob> -Pattern <re>` to search code. `Get-ChildItem -Recurse -Filter` to locate files.
- Check a tool exists with `Get-Command <tool>` before using it. Quote paths containing spaces.
- Background job: `Start-Process ... -RedirectStandardOutput ... -PassThru -WindowStyle Hidden`, then ONE `Wait-Process -Timeout 1500`.
- DataLoader `num_workers` 0-2. Guard entry points with `if __name__ == "__main__":`.
