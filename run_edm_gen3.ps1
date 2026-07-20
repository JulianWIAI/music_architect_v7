# ============================================================
#  EDM / House  --  Generation 3  (1000-Track Commercial Payload)
#  500 EDM + 500 House  |  Top-5 seeds from Gen2, mutation 0.05
# ============================================================

$Root   = $PSScriptRoot
$Gen2   = Join-Path $Root "edm_gen2"
$OutDir = Join-Path $Root "edm_gen3"
$Python = "python"

$Genres = @(
    @{ prompt = "edm music";   genre = "edm";   count = 500 },
    @{ prompt = "house music"; genre = "house"; count = 500 }
)

if (Test-Path $OutDir) {
    Write-Host "Removing old edm_gen3..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Path $OutDir | Out-Null

$Total    = $Genres.Count
$Index    = 0
$StartAll = Get-Date

foreach ($g in $Genres) {
    $Index++
    $GenreDir = Join-Path $OutDir $g.genre
    $SeedPool = Join-Path $Gen2 ($g.genre + "\math_fitness_report.json")
    $Elapsed  = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")

    Write-Host ""
    Write-Host ("[$Index/$Total]  " + $g.genre.ToUpper() + "  x$($g.count)  ($Elapsed elapsed)") -ForegroundColor Cyan

    $pyArgs = @(
        "-m", "src.orchestration.batch_commander",
        "--prompt", $g.prompt,
        "--count",  "$($g.count)",
        "--outdir", $GenreDir,
        "--seeds-dir", "seeds"
    )

    if (Test-Path $SeedPool) {
        Write-Host "  seed-pool : $SeedPool"
        $pyArgs += "--seed-pool"
        $pyArgs += $SeedPool
        $pyArgs += "--mutation-factor"
        $pyArgs += "0.05"
    } else {
        Write-Host "  [WARN] Gen2 report not found -- falling back to free exploration" -ForegroundColor Yellow
        Write-Host "         Expected: $SeedPool"
    }

    & $Python @pyArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  [ERROR] failed for " + $g.genre) -ForegroundColor Red
    } else {
        Write-Host "  Done" -ForegroundColor Green
    }
}

# ---- Pure Math Grader -------------------------------------------------------
Write-Host ""
Write-Host "Running Pure Math Grader on EDM Generation 3..." -ForegroundColor Magenta
& $Python -m src.orchestration.telemetry_grader_midi --batch-dir $OutDir

# ---- Cross-Generation Comparison --------------------------------------------
Write-Host ""
Write-Host "Cross-Generation Comparison (EDM/House pipeline)..." -ForegroundColor Magenta

$Batches = @(
    @{ path = (Join-Path $Root "edm_gen1"); label = "EDM Gen1 Baseline   (200 tracks)" },
    @{ path = (Join-Path $Root "edm_gen2"); label = "EDM Gen2 Evolved    (500 tracks)" },
    @{ path = (Join-Path $Root "edm_gen3"); label = "EDM Gen3 Commercial (1000 tracks)" }
)

foreach ($b in $Batches) {
    if (Test-Path $b.path) {
        Write-Host ""
        Write-Host ("  --- " + $b.label + " ---") -ForegroundColor Cyan
        & $Python -m src.orchestration.telemetry_grader_midi --batch-dir $b.path
    }
}

$TotalTime = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")
Write-Host ""
Write-Host ("EDM Generation 3 complete.  Total time: $TotalTime") -ForegroundColor Green
Write-Host "1000-track EDM/House commercial payload ready at:" -ForegroundColor Cyan
Write-Host "  $OutDir"
