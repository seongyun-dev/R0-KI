param(
    [Parameter(Mandatory = $true)]
    [string]$Jetson
)

$ErrorActionPreference = "Stop"
$hardware = $PSScriptRoot
$robot = Split-Path -Parent $hardware

Write-Host "Copying the three line-follow test files to $Jetson"
& scp `
    (Join-Path $hardware "line_follow_field_test.py") `
    (Join-Path $hardware "esp32_port.py") `
    "${Jetson}:~/robot-hw-test/"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& scp `
    (Join-Path $robot "roki/control/line_follower.py") `
    "${Jetson}:~/roki/control/"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Deployment complete. Run the field-test command on the Jetson."
