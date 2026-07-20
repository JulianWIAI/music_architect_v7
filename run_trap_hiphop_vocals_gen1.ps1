# ============================================================
#  Trap / Hip-Hop  VOCAL MASK  --  Generation 1  (Baseline)
#  100 Trap + 100 Hip-Hop  |  Free exploration, no seeds
# ============================================================

$Root   = $PSScriptRoot
$OutDir = Join-Path $Root "trap_hiphop_vocals_gen1"
$Python = "python"

$Genres = @(
    @{ prompt = "trap music";   genre = "trap";   count = 100 },
    @{ prompt = "hip hop beat"; genre = "hiphop"; count = 100 }
)

if (Test-Path $OutDir) {
    Write-Host "Removing old trap_hiphop_vocals_gen1..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Path $OutDir | Out-Null

$Total    = $Genres.Count
$Index    = 0
$StartAll = Get-Date

foreach ($g in $Genres) {
    $Index++
    $GenreDir = Join-Path $OutDir $g.genre
    $Elapsed  = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")

    Write-Host ""
    Write-Host ("[$Index/$Total]  " + $g.genre.ToUpper() + "  x$($g.count)  ($Elapsed elapsed)  [VOCAL MASK ON]") -ForegroundColor Cyan
    Write-Host "  Mode: free exploration (no seed pool)"

    $pyArgs = @(
        "-m", "src.orchestration.batch_commander",
        "--prompt", $g.prompt,
        "--count",  "$($g.count)",
        "--outdir", $GenreDir,
        "--seeds-dir", "seeds",
        "--vocal-mask"
    )

    & $Python @pyArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  [ERROR] failed for " + $g.genre) -ForegroundColor Red
    } else {
        Write-Host "  Done" -ForegroundColor Green
    }
}

# ---- Pure Math Grader -------------------------------------------------------
Write-Host ""
Write-Host "Running Pure Math Grader on Vocals Generation 1..." -ForegroundColor Magenta
& $Python -m src.orchestration.telemetry_grader_midi --batch-dir $OutDir

$TotalTime = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")
Write-Host ""
Write-Host ("Vocals Generation 1 complete.  Total time: $TotalTime") -ForegroundColor Green
Write-Host "Golden matrices saved to:" -ForegroundColor Cyan
Write-Host "  $OutDir\trap\math_fitness_report.json"
Write-Host "  $OutDir\hiphop\math_fitness_report.json"
Write-Host ""
Write-Host "Next step: run_trap_hiphop_vocals_gen2.ps1" -ForegroundColor Yellow
