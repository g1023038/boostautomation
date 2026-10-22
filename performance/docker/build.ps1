# Builds the image from performance/ as the context (not performance/docker/),
# so the Dockerfile COPYs the real test plan directly -- no duplicate jmx copy
# to go stale like the Downloads-folder one did.
$perfDir = Split-Path -Parent $PSScriptRoot
Push-Location $perfDir
try {
    docker build -f docker/Dockerfile -t boost-jmeter:local .
} finally {
    Pop-Location
}
