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
    [ValidateSet('https://127.0.0.1:8443','http://127.0.0.1:4200','http://127.0.0.1:9002')]
    [string]$BaseUrl = 'https://127.0.0.1:8443',
    [PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
if (-not $Credential) { $Credential = Get-Credential -UserName 'mifos' -Message 'Local dummy Fineract login only. Fresh database default password is password.' }
if (-not $Credential) { throw 'Local credentials are required.' }
Add-Type -AssemblyName System.Net.Http
$handlerTask = [Net.Http.HttpClientHandler]::new()
$handlerTask.AllowAutoRedirect = $false
# Scope self-signed certificate acceptance to this loopback-only HttpClient instance.
$handlerTask.ServerCertificateCustomValidationCallback = [Net.Http.HttpClientHandler]::DangerousAcceptAnyServerCertificateValidator
$clientTask = [Net.Http.HttpClient]::new($handlerTask)
$clientTask.Timeout = [TimeSpan]::FromSeconds(20)
try {
    $clientTask.DefaultRequestHeaders.Add('Fineract-Platform-TenantId','default')
    $bodyTask = @{ username=$Credential.UserName; password=$Credential.GetNetworkCredential().Password } | ConvertTo-Json -Compress
    $contentTask = [Net.Http.StringContent]::new($bodyTask,[Text.Encoding]::UTF8,'application/json')
    $responseTask = $clientTask.PostAsync("$BaseUrl/fineract-provider/api/v1/authentication",$contentTask).GetAwaiter().GetResult()
    if (-not $responseTask.IsSuccessStatusCode) { throw "Authentication failed: HTTP $([int]$responseTask.StatusCode). Inspect tenant, migrations, TLS, proxy and credentials; response body is deliberately not printed." }
    $authTask = $responseTask.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
    if (-not $authTask.authenticated -or -not $authTask.base64EncodedAuthenticationKey) { throw 'Unexpected auth response: authenticated=true and a Basic token are required.' }
    $clientTask.DefaultRequestHeaders.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Basic',$authTask.base64EncodedAuthenticationKey)
    $checkTask = $clientTask.GetAsync("$BaseUrl/fineract-provider/api/v1/offices").GetAwaiter().GetResult()
    if (-not $checkTask.IsSuccessStatusCode) { throw "Authenticated offices request failed: HTTP $([int]$checkTask.StatusCode)." }
    Write-Host "PASS: default-tenant authentication and authorised offices request through $BaseUrl."
    Write-Host 'Credentials, returned tokens and office/client records were not printed.'
} finally { $clientTask.Dispose(); $handlerTask.Dispose() }
