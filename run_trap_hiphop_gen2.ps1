# ============================================================
#  Trap / Hip-Hop  —  Generation 2  (Golden Matrix Injection)
#  250 Trap + 250 Hip-Hop  |  Top-5 seeds from Gen1, mutation 0.05
# ============================================================

$Root   = $PSScriptRoot
$Gen1   = Join-Path $Root "trap_hiphop_gen1"
$OutDir = Join-Path $Root "trap_hiphop_gen2"
$Python = "python"

$Genres = @(
    @{ prompt = "trap music";   genre = "trap";   count = 250 },
    @{ prompt = "hip hop beat"; genre = "hiphop"; count = 250 }
)

if (Test-Path $OutDir) {
    Write-Host "Removing old trap_hiphop_gen2..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Path $OutDir | Out-Null

$Total    = $Genres.Count
$Index    = 0
$StartAll = Get-Date

foreach ($g in $Genres) {
    $Index++
    $GenreDir = Join-Path $OutDir $g.genre
    $SeedPool = Join-Path $Gen1 ($g.genre + "\math_fitness_report.json")
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
        Write-Host "  [WARN] Gen1 report not found -- falling back to free exploration" -ForegroundColor Yellow
        Write-Host "         Expected: $SeedPool"
    }

    & $Python @pyArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  [ERROR] failed for " + $g.genre) -ForegroundColor Red
    } else {
        Write-Host "  Done" -ForegroundColor Green
    }
}

# ── Pure Math Grader ─────────────────────────────────────────
Write-Host ""
Write-Host "Running Pure Math Grader on Generation 2..." -ForegroundColor Magenta
& $Python -m src.orchestration.telemetry_grader_midi --batch-dir $OutDir

$TotalTime = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")
Write-Host ""
Write-Host ("Generation 2 complete.  Total time: $TotalTime") -ForegroundColor Green
Write-Host "Refined golden matrices saved to:" -ForegroundColor Cyan
Write-Host "  $OutDir\trap\math_fitness_report.json"
Write-Host "  $OutDir\hiphop\math_fitness_report.json"
Write-Host ""
Write-Host "Next step: run_trap_hiphop_gen3.ps1" -ForegroundColor Yellow
