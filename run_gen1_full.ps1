# ============================================================
#  Generation 1  —  100 random-seed tracks per genre
#  Then: Pure Math Grader  →  Top-5 Golden Matrices per genre
# ============================================================

$Root    = $PSScriptRoot
$OutDir  = Join-Path $Root "Generation1"
$Python  = "python"

$Genres = @(
    @{ prompt = "pop music track";   genre = "pop"       },
    @{ prompt = "hip hop beat";      genre = "hiphop"    },
    @{ prompt = "trap music";        genre = "trap"      },
    @{ prompt = "cinematic music";   genre = "cinematic" },
    @{ prompt = "classical music";   genre = "classical" },
    @{ prompt = "techno music";      genre = "techno"    },
    @{ prompt = "jpop music";        genre = "jpop"      },
    @{ prompt = "phonk music";       genre = "phonk"     },
    @{ prompt = "edm music";         genre = "edm"       },
    @{ prompt = "house music";       genre = "house"     },
    @{ prompt = "drum and bass";     genre = "dnb"       }
)

# ── Wipe old Generation1 ─────────────────────────────────────
if (Test-Path $OutDir) {
    Write-Host "Removing old Generation1..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Path $OutDir | Out-Null

$TotalGenres = $Genres.Count
$GenreIndex  = 0
$StartAll    = Get-Date

foreach ($g in $Genres) {
    $GenreIndex++
    $GenreDir = Join-Path $OutDir $g.genre
    $Elapsed  = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")

    Write-Host ""
    Write-Host "[$GenreIndex/$TotalGenres]  $($g.genre.ToUpper())  ($Elapsed elapsed)" -ForegroundColor Cyan
    Write-Host "  outdir : $GenreDir"
    Write-Host "  prompt : $($g.prompt)"

    $t0 = Get-Date
    & $Python -m src.orchestration.batch_commander `
        --prompt $g.prompt `
        --count  100 `
        --outdir $GenreDir `
        --seeds-dir seeds
    $dt = [math]::Round(((Get-Date) - $t0).TotalSeconds)

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] batch_commander failed for $($g.genre)" -ForegroundColor Red
    } else {
        Write-Host "  Done in ${dt}s" -ForegroundColor Green
    }
}

# ── Pure Math Grader ─────────────────────────────────────────
Write-Host ""
Write-Host "======================================================" -ForegroundColor Magenta
Write-Host "  Running Pure Math Grader on Generation1..." -ForegroundColor Magenta
Write-Host "======================================================" -ForegroundColor Magenta

& $Python -m src.orchestration.telemetry_grader_midi --batch-dir $OutDir

$TotalTime = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")
Write-Host ""
Write-Host "Generation 1 complete.  Total time: $TotalTime" -ForegroundColor Green
Write-Host "Golden matrices written to: Generation1/<genre>/math_fitness_report.json"
