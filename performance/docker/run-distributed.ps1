<#
.SYNOPSIS
  Launch N independent boost-jmeter containers in parallel, each driving a
  slice of a target thread-group's user count. No JMeter master/slave (RMI)
  coordination -- each container is a fully independent JMeter process;
  Datadog is the aggregation point (see performance/README.md).

.EXAMPLE
  # 3 containers, 300 total Mixed Journey users (100 each), reading the
  # same registered-identity pool, pushing to Datadog with the key already
  # saved in the host's user.properties.
  .\run-distributed.ps1 -Containers 3 -TotalUsers 300 -UsersProp mixedUsers -RampupProp mixedRampup -Rampup 60 -CsvFile ..\testusers_registered.csv

.NOTES
  KNOWN LIMITATION (documented, not yet solved): every container currently
  mounts the SAME csv pool file and starts reading from row 1 independently
  -- it does not slice the pool across containers. Fine for a small proof-
  of-concept run; for real distributed load you want each container reading
  a disjoint slice of a large registered-users pool (e.g. split
  all_testusers.csv into N chunks first). Revisit once the mechanism itself
  is proven out.
#>
param(
    [int]$Containers = 3,
    [int]$TotalUsers = 300,
    [string]$UsersProp = "mixedUsers",
    [string]$RampupProp = "mixedRampup",
    [int]$Rampup = 60,
    [string]$CsvFile = "..\testusers_registered.csv",
    [string]$Image = "boost-jmeter:local",
    [string]$ExtraArgs = "",
    [switch]$NoDatadog
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resultsDir = Join-Path $scriptDir "results"
$dataDir = Join-Path $scriptDir "data"
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$resolvedCsv = Resolve-Path (Join-Path $scriptDir $CsvFile)
$csvName = Split-Path -Leaf $resolvedCsv
Copy-Item $resolvedCsv (Join-Path $dataDir $csvName) -Force

$ddKey = $null
if (-not $NoDatadog) {
    $propsFile = "$env:TEMP\jmeter-install\apache-jmeter-5.6.3\bin\user.properties"
    if (Test-Path $propsFile) {
        $line = Select-String -Path $propsFile -Pattern "^ddApiKey="
        if ($line) { $ddKey = ($line.Line -split "=", 2)[1] }
    }
    if (-not $ddKey) {
        Write-Warning "No ddApiKey found -- pass -NoDatadog to run without it, or save one to $propsFile first."
    }
}

$base = [math]::Floor($TotalUsers / $Containers)
$remainder = $TotalUsers - ($base * $Containers)
Write-Output "Launching $Containers containers -- base $base users each (+1 on the first $remainder) = $TotalUsers total"

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$containerIds = @()

for ($i = 1; $i -le $Containers; $i++) {
    $share = $base
    if ($i -le $remainder) { $share++ }
    $label = "boost-load-$runId-$i"

    $dockerArgs = @(
        "run", "-d", "--name", $label,
        "-e", "CONTAINER_LABEL=$label",
        "-v", "${resultsDir}:/opt/jmeter-test/results",
        "-v", "${dataDir}:/opt/jmeter-test/data"
    )
    if ($ddKey) { $dockerArgs += @("-e", "DD_API_KEY=$ddKey") }
    $dockerArgs += $Image
    $dockerArgs += @("-J$UsersProp=$share", "-J${RampupProp}=$Rampup", "-Jcsvfile=/opt/jmeter-test/data/$csvName")
    if ($ExtraArgs) { $dockerArgs += ($ExtraArgs -split " ") }

    Write-Output "  [$i/$Containers] $label -> $share users"
    $id = & docker @dockerArgs
    $containerIds += $id.Trim()
}

Write-Output "`nAll $Containers containers started. Waiting for them to finish..."
docker wait @containerIds | Out-Null

Write-Output "`n--- Per-container exit status ---"
foreach ($id in $containerIds) {
    $name = (docker inspect --format "{{.Name}}" $id).TrimStart("/")
    $exitCode = docker inspect --format "{{.State.ExitCode}}" $id
    Write-Output "$name : exit $exitCode"
}

Write-Output "`nResults written to: $resultsDir (one .jtl + .jmeter.log per container)"
Write-Output "Cleaning up containers (logs/results already on disk)..."
docker rm @containerIds | Out-Null
