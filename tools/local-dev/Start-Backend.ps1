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
param()
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Test-LocalPrerequisites.ps1')
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env.local'))) {
    throw 'Run Initialize-Local.ps1 first.'
}
$composeTask = @('compose','--project-name','capstone-fineract-local','--env-file',
    (Join-Path $PSScriptRoot '.env.local'),'-f',(Join-Path $PSScriptRoot 'compose.yaml'))
& docker @composeTask config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed validation.' }
& docker @composeTask up -d db fineract
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Inspect this project only; do not remove database volumes.' }
Write-Host 'Containers requested. First migration may take several minutes.'
Write-Host 'Next: inspect logs, then run Test-LocalApi.ps1. A running container is not a successful login.'
& docker @composeTask ps
