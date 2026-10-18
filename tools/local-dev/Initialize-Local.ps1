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
param(
    [string]$FineractRoot = ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))),
    [string]$JarPath
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env.local')) {
    Write-Host 'Local configuration already exists. Preserving it and its database password.'
    return
}
$dockerTask = Get-Command docker.exe -ErrorAction Stop
& $dockerTask.Source info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop before initializing the demo configuration.' }
& $dockerTask.Source volume inspect capstone-fineract-local_capstone_db *> $null
if ($LASTEXITCODE -eq 0) { throw 'Existing demo volume detected. Restore its original private .env.local; do not generate a different password.' }
if (-not $JarPath) {
    $jars = @(Get-ChildItem -LiteralPath (Join-Path $FineractRoot 'fineract-provider\build\libs') -Filter '*.jar' |
        Where-Object { $_.Name -notmatch 'plain|sources|javadoc' })
    if ($jars.Count -ne 1) { throw 'Pass -JarPath with the exact reviewed executable JAR; auto-selection is ambiguous.' }
    $JarPath = $jars[0].FullName
}
$jarTask = Get-Item -LiteralPath $JarPath
if ($jarTask.PSIsContainer) { throw 'JarPath must identify a file.' }
$jarTaskPath = $jarTask.FullName.Replace('\', '/')
if ($jarTaskPath -match "['`r`n]") { throw 'JAR path cannot contain apostrophes or newlines in this env-file format.' }
$secretTask = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).ToLowerInvariant()
$linesTask = @("FINERACT_JAR='$jarTaskPath'", "LOCAL_DB_PASSWORD=$secretTask")
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot '.env.local'), $linesTask, [Text.UTF8Encoding]::new($false))
Write-Host 'Created .env.local with a new local-only database password. Keep this file private and out of Git.'
Write-Host ('Selected JAR SHA256: ' + (Get-FileHash -LiteralPath $jarTask.FullName -Algorithm SHA256).Hash)
