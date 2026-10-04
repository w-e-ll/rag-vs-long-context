param(
    [ValidateSet('Setup','Up','Verify','Test','CheckOCR','Down','DownloadVision','DiagnoseVision','CheckVision','DownloadText','UpText')][string]$Action = 'Up',
    [int]$Workers = 2,
    [switch]$Vision,
    [switch]$Gpu
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$ComposeArgs = @('compose', '-f', 'docker-compose.yml')
if ($Action -in @('DownloadText','UpText')) {
    $ComposeArgs += @('-f', 'docker-compose.text.yml')
    if ($Gpu) { $ComposeArgs += @('-f', 'docker-compose.text-gpu.yml') }
} elseif ($Vision -or $Gpu -or $Action -in @('DownloadVision','DiagnoseVision','CheckVision')) {
    $ComposeArgs += @('-f', 'docker-compose.vision.yml')
    if ($Gpu) { $ComposeArgs += @('-f', 'docker-compose.gpu.yml') }
}
function Invoke-Checked { param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}
function Wait-Endpoint { param([string]$Name, [string]$Url)
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try {
            $null = Invoke-RestMethod -Uri $Url -TimeoutSec 3
            Write-Host "$Name reachable: $Url"
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "$Name unavailable at $Url. Check: docker compose logs --tail 50 gateway api ui; docker compose port gateway 8003. Run ./scripts/docker.ps1 Up to apply network changes."
}
switch ($Action) {
    'DownloadText' {
        # Include ollama in the validated service graph; --no-deps runs only the downloader.
        Invoke-Checked 'docker' ($ComposeArgs + @('--profile','local-models','--profile','model-download','run','--rm','--no-deps','text-download'))
    }
    'UpText' {
        # Serialize image exports to reduce peak Docker Desktop resource use.
        foreach ($service in @('api','worker','dispatcher','ui','migrate','parser')) {
            Invoke-Checked 'docker' ($ComposeArgs + @('--profile','local-models','build',$service))
            # Inspect the exported image without application data, secrets or networking.
            $identityCheck = "import os,pwd; assert os.getuid()==10001; assert os.getgid()==10001; assert pwd.getpwnam('app').pw_uid==10001; print('Image identity OK')"
            Invoke-Checked 'docker' @('run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--entrypoint','python',"sunday-rag-lab-$service",'-c',$identityCheck)
        }
        # One worker avoids concurrent model swaps on an 8 GB GPU.
        Invoke-Checked 'docker' ($ComposeArgs + @('--profile','local-models','up','-d','--no-build','--scale','worker=1'))
    }
    'CheckVision' {
        # Read the local module over stdin so no image rebuild is needed for this probe.
        # Load both updated modules in memory; neither file nor customer data is modified.
        $probe = @'
import sys, types
source = sys.stdin.read()
adapter, probe = source.split('\n# VISION_PROBE_BOUNDARY\n', 1)
module = types.ModuleType('rag_lab.ingestion.vision')
sys.modules[module.__name__] = module
exec(compile(adapter, 'vision.py', 'exec'), module.__dict__)
exec(compile(probe, 'vision_probe.py', 'exec'), {'__name__': '__main__'})
'@
        $source = (Get-Content 'rag_lab/ingestion/vision.py' -Raw) + "`n# VISION_PROBE_BOUNDARY`n" + (Get-Content 'rag_lab/ingestion/vision_probe.py' -Raw)
        $source | & docker @ComposeArgs exec -T parser python -c $probe
        if ($LASTEXITCODE -ne 0) { throw 'Vision probe failed; inspect the safe diagnostic result above.' }
    }
    'CheckOCR' {
        Invoke-Checked 'docker' ($ComposeArgs + @('--profile','tests','run','--build','--rm','--no-deps','tests','pytest','-q','-p','no:cacheprovider','tests/test_ocr_layout.py'))
    }
    'DiagnoseVision' {
        $visionId = & docker @ComposeArgs ps -q vision
        if ($LASTEXITCODE -ne 0 -or -not $visionId) { throw 'Vision container is not running.' }
        Write-Host 'Configured GPU requests (null/empty means no GPU was assigned):'
        Invoke-Checked 'docker' @('inspect','--format','{{json .HostConfig.DeviceRequests}}', $visionId.Trim())
        Write-Host 'Currently loaded models (empty means unloaded, not necessarily CPU-only):'
        Invoke-Checked 'docker' ($ComposeArgs + @('exec','-T','vision','ollama','ps'))
        Write-Host 'Recent runtime logs, excluding routine health checks:'
        $visionLog = & docker @ComposeArgs logs --since 2h vision 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'Could not read vision logs.' }
        $visionLog | Where-Object {
            $_ -notmatch '\[GIN\].*(HEAD\s+"/"|POST\s+"/api/show"|GET\s+"/api/ps")'
        } | Select-Object -Last 80
    }
    'Setup' { Invoke-Checked 'uv' @('run','python','scripts/setup.py') }
    'Up' { Invoke-Checked 'docker' ($ComposeArgs + @('up','-d','--build','--scale',"worker=$Workers")) }
    'DownloadVision' {
        Invoke-Checked 'docker' ($ComposeArgs + @('--profile','model-download','run','--rm','--no-deps','vision-download'))
    }
    'Verify' {
        Invoke-Checked 'docker' @('compose','ps')
        Invoke-Checked 'docker' @('compose','port','gateway','8003')
        Invoke-Checked 'docker' @('compose','port','gateway','8503')
        Wait-Endpoint 'API' 'http://127.0.0.1:8003/health/db'
        Wait-Endpoint 'UI' 'http://127.0.0.1:8503/_stcore/health'
        Wait-Endpoint 'Grafana' 'http://127.0.0.1:3003/api/health'
        Wait-Endpoint 'Prometheus' 'http://127.0.0.1:9093/-/ready'
    }
    'Test' { Invoke-Checked 'docker' @('compose','--profile','tests','run','--build','--rm','tests') }
    'Down' { Invoke-Checked 'docker' ($ComposeArgs + @('down')) }
}
