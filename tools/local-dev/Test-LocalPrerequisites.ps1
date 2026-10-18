# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

#requires -Version 7.0
[CmdletBinding()]
param([double]$MinimumSystemFreeGiB = 8)
$ErrorActionPreference = 'Stop'
$problemsTask = [Collections.Generic.List[string]]::new()
$diskTask = [IO.DriveInfo]::new($env:SystemDrive + '\')
$freeTask = [math]::Round($diskTask.AvailableFreeSpace / 1GB, 2)
Write-Host "System drive free space: $freeTask GiB; chosen startup threshold: $MinimumSystemFreeGiB GiB."
if ($freeTask -lt $MinimumSystemFreeGiB) { $problemsTask.Add('Free system-drive space before starting Docker or downloading/building images.') }
$dockerTask = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $dockerTask) { $problemsTask.Add('Docker CLI is missing.') }
else {
    $psiTask = [Diagnostics.ProcessStartInfo]::new()
    $psiTask.FileName = $dockerTask.Source
    $psiTask.UseShellExecute = $false
    $psiTask.CreateNoWindow = $true
    $psiTask.RedirectStandardOutput = $true
    $psiTask.RedirectStandardError = $true
    foreach ($argTask in @('version','--format','{{.Server.Version}}')) { $psiTask.ArgumentList.Add($argTask) }
    $processTask = [Diagnostics.Process]::new()
    $processTask.StartInfo = $psiTask
    [void]$processTask.Start()
    $outTask = $processTask.StandardOutput.ReadToEndAsync()
    $errTask = $processTask.StandardError.ReadToEndAsync()
    if (-not $processTask.WaitForExit(12000)) {
        $processTask.Kill($true)
        $processTask.WaitForExit()
        $problemsTask.Add('Docker engine did not answer within 12 seconds. Check Docker Desktop after resolving disk pressure.')
    } elseif ($processTask.ExitCode -ne 0) {
        $problemsTask.Add('Docker engine check failed. Check Desktop engine state and named-pipe permissions.')
    } else { Write-Host ('Docker engine: ' + $outTask.GetAwaiter().GetResult().Trim()) }
    $processTask.Dispose()
}
foreach ($portTask in @(8443,4200)) {
    $listenerTask = @(Get-NetTCPConnection -State Listen -LocalPort $portTask -ErrorAction SilentlyContinue)
    if ($listenerTask.Count) {
        Write-Warning "Port $portTask is already listening. Identify it before starting another service; do not kill it blindly."
    }
}
if ($problemsTask.Count) { throw ($problemsTask -join [Environment]::NewLine) }
Write-Host 'Preflight passed. This does not prove Fineract, database migrations or the client are healthy.'
