$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildPython = Join-Path $ProjectRoot ".build-venv\Scripts\python.exe"
$EntryScript = Join-Path $ProjectRoot "invoice_attachment_gui.py"
$ManifestFile = Join-Path $ProjectRoot "app.manifest"
$UsageGuide = Join-Path $ProjectRoot "README.txt"
$DistDirectory = Join-Path $ProjectRoot "dist"
$WorkDirectory = Join-Path $ProjectRoot "build"
$ApplicationName = "invoice_attachment_tool"

function Remove-SafeBuildDirectory {
    param([string]$TargetPath)

    $ResolvedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $ResolvedTarget = [System.IO.Path]::GetFullPath($TargetPath).TrimEnd('\')
    $ExpectedParent = [System.IO.Path]::GetDirectoryName($ResolvedTarget)
    $TargetName = [System.IO.Path]::GetFileName($ResolvedTarget)

    if ($ExpectedParent -ne $ResolvedProjectRoot -or $TargetName -notin @("build", "dist")) {
        throw "Refusing to remove unexpected build path: $ResolvedTarget"
    }

    if (Test-Path -LiteralPath $ResolvedTarget) {
        Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    throw "未找到构建环境。请先执行: python -m venv .build-venv"
}

if (-not (Test-Path -LiteralPath $EntryScript -PathType Leaf)) {
    throw "未找到入口脚本: $EntryScript"
}

if (-not (Test-Path -LiteralPath $ManifestFile -PathType Leaf)) {
    throw "Manifest file not found: $ManifestFile"
}

Push-Location $ProjectRoot
try {
    Remove-SafeBuildDirectory $DistDirectory
    Remove-SafeBuildDirectory $WorkDirectory
    New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null

    & $BuildPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --manifest $ManifestFile `
        --name $ApplicationName `
        --distpath $DistDirectory `
        --workpath $WorkDirectory `
        --specpath $WorkDirectory `
        $EntryScript

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败，退出码: $LASTEXITCODE"
    }

    Copy-Item -LiteralPath $UsageGuide -Destination $DistDirectory -Force
    Write-Host "Build complete: $(Join-Path $DistDirectory ($ApplicationName + '.exe'))"
}
finally {
    Pop-Location
}
