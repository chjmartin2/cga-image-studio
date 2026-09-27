# Make Explorer launch the source build with its configuration and resource cwd.
param([string]$ExportDisk)
$ErrorActionPreference = 'Stop'
$martyWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$martyInstall = Join-Path $martyWorkspace 'external\martypc\install'
$martyExecutable = Join-Path $martyWorkspace 'external\martypc\target\release\martypc.exe'
$martyConfig = Join-Path $martyInstall 'martypc-cga.toml'
foreach ($martyRequired in @($martyExecutable, $martyConfig)) {
    if (-not (Test-Path -LiteralPath $martyRequired -PathType Leaf)) {
        throw "Required MartyPC file missing: $martyRequired"
    }
}
$martyShell = New-Object -ComObject WScript.Shell
try {
    # Also place a launcher beside the raw exe, where it is easy to discover.
    foreach ($martyFolder in @($martyWorkspace, (Split-Path -Parent $martyExecutable))) {
        $martyLinkPath = Join-Path $martyFolder 'MartyPC Latest.lnk'
        $martyLink = $martyShell.CreateShortcut($martyLinkPath)
        $martyLink.TargetPath = $martyExecutable
        $martyLink.Arguments = '--configfile "' + $martyConfig + '"'
        $martyLink.WorkingDirectory = $martyInstall
        $martyLink.IconLocation = $martyExecutable + ',0'
        $martyLink.Description = 'MartyPC 0.5.0 - local CGA build with its configuration and ROMs'
        $martyLink.Save()
        Write-Output "Created $martyLinkPath"
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($martyLink)
    }
    $martyDemoLauncher = Join-Path $martyWorkspace 'run_startlock.cmd'
    if (Test-Path -LiteralPath $martyDemoLauncher -PathType Leaf) {
        $martyDemoLinkPath = Join-Path $martyWorkspace 'STARTLCK Demo.lnk'
        $martyDemoLink = $martyShell.CreateShortcut($martyDemoLinkPath)
        $martyDemoLink.TargetPath = $martyDemoLauncher
        $martyDemoLink.WorkingDirectory = $martyWorkspace
        $martyDemoLink.IconLocation = $martyExecutable + ',0'
        $martyDemoLink.Description = 'Boot the STARTLCK mode-4 demo disk in MartyPC'
        $martyDemoLink.Save()
        Write-Output "Created $martyDemoLinkPath"
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($martyDemoLink)
    }
    $martyImageLauncher = Join-Path $martyWorkspace 'run_imagelock.cmd'
    if (Test-Path -LiteralPath $martyImageLauncher -PathType Leaf) {
        $martyImageLinkPath = Join-Path $martyWorkspace 'Picard CGA Demo.lnk'
        $martyImageLink = $martyShell.CreateShortcut($martyImageLinkPath)
        $martyImageLink.TargetPath = $martyImageLauncher
        $martyImageLink.WorkingDirectory = $martyWorkspace
        $martyImageLink.IconLocation = $martyExecutable + ',0'
        $martyImageLink.Description = 'Boot Picard with acquired mode-4 palette timing in MartyPC'
        $martyImageLink.Save()
        Write-Output "Created $martyImageLinkPath"
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($martyImageLink)
    }
    if ($ExportDisk) {
        $martyExportDisk = (Resolve-Path -LiteralPath $ExportDisk).Path
        $martyExportLinkPath = Join-Path $martyWorkspace 'Test My CGA Export.lnk'
        $martyExportLink = $martyShell.CreateShortcut($martyExportLinkPath)
        $martyExportLink.TargetPath = Join-Path $martyWorkspace 'run_cga_disk.cmd'
        $martyExportLink.Arguments = '"' + $martyExportDisk + '"'
        $martyExportLink.WorkingDirectory = $martyWorkspace
        $martyExportLink.IconLocation = $martyExecutable + ',0'
        $martyExportLink.Description = 'Freshly load the exported CGA disk and start TEST with verified settings'
        $martyExportLink.Save()
        Write-Output "Created $martyExportLinkPath"
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($martyExportLink)
    }
} finally {
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($martyShell)
}
