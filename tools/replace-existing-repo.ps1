param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath
)

$Source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Target = (Resolve-Path $RepositoryPath).Path

if (-not (Test-Path (Join-Path $Target ".git"))) {
    throw "Target is not a Git repository: $Target"
}

if ($Source -eq $Target) {
    throw "Extract this package outside the existing repository first."
}

$confirmation = Read-Host "Delete all working files in $Target except .git and replace them? Type YES"
if ($confirmation -ne "YES") {
    Write-Host "Cancelled."
    exit 0
}

Get-ChildItem -LiteralPath $Target -Force |
    Where-Object { $_.Name -ne ".git" } |
    Remove-Item -Recurse -Force

Get-ChildItem -LiteralPath $Source -Force |
    Where-Object { $_.Name -ne ".git" } |
    ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force
    }

Write-Host "Replacement complete. Next: cd $Target; git add -A; git commit; git push"
