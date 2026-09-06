param(
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildPython = if ($PythonExecutable) {
    [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $PythonExecutable))
} else {
    Join-Path $ProjectRoot ".build-venv\Scripts\python.exe"
}
$SpecFile = Join-Path $ProjectRoot "invoice_attachment_tool.spec"
$UsageGuide = Join-Path $ProjectRoot "README.md"
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
    throw "未找到构建环境。请先执行: python -m venv .build-venv，或使用 -PythonExecutable 指定 Python"
}

if (-not (Test-Path -LiteralPath $SpecFile -PathType Leaf)) {
    throw "未找到 PyInstaller spec: $SpecFile"
}

Push-Location $ProjectRoot
try {
    Remove-SafeBuildDirectory $DistDirectory
    Remove-SafeBuildDirectory $WorkDirectory
    New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null

    & $BuildPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistDirectory `
        --workpath $WorkDirectory `
        $SpecFile

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败，退出码: $LASTEXITCODE"
    }

    $ApplicationDirectory = Join-Path $DistDirectory $ApplicationName
    foreach ($File in @($UsageGuide, (Join-Path $ProjectRoot "LICENSE"), (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md"))) {
        Copy-Item -LiteralPath $File -Destination $ApplicationDirectory -Force
    }
    Write-Host "Build complete: $(Join-Path $ApplicationDirectory ($ApplicationName + '.exe'))"
}
finally {
    Pop-Location
}
