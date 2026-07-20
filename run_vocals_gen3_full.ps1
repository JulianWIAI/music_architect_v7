# ============================================================
#  Vocals Generation 3  -  100 tracks per genre
#  Seed pool: Top-5 Golden Matrices from vocals_generation_2
#  Mutation factor: 0.05  |  Vocal mask: ON
# ============================================================

$Root    = $PSScriptRoot
$VocGen2 = Join-Path $Root "vocals_generation_2"
$OutDir  = Join-Path $Root "vocals_generation_3"
$Python  = "python"

$Genres = @(
    @{ prompt = "pop music track"; genre = "pop"       },
    @{ prompt = "hip hop beat";    genre = "hiphop"    },
    @{ prompt = "trap music";      genre = "trap"      },
    @{ prompt = "cinematic music"; genre = "cinematic" },
    @{ prompt = "classical music"; genre = "classical" },
    @{ prompt = "techno music";    genre = "techno"    },
    @{ prompt = "jpop music";      genre = "jpop"      },
    @{ prompt = "phonk music";     genre = "phonk"     },
    @{ prompt = "edm music";       genre = "edm"       },
    @{ prompt = "house music";     genre = "house"     },
    @{ prompt = "drum and bass";   genre = "dnb"       }
)

if (Test-Path $OutDir) {
    Write-Host "Removing old vocals_generation_3..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Path $OutDir | Out-Null

$Total    = $Genres.Count
$Index    = 0
$StartAll = Get-Date

foreach ($g in $Genres) {
    $Index++
    $GenreDir = Join-Path $OutDir $g.genre
    $SeedPool = Join-Path $VocGen2 ($g.genre + "\math_fitness_report.json")
    $Elapsed  = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")

    Write-Host ""
    Write-Host ("[$Index/$Total]  " + $g.genre.ToUpper() + "  ($Elapsed elapsed)") -ForegroundColor Cyan

    $pyArgs = @(
        "-m", "src.orchestration.batch_commander",
        "--prompt",     $g.prompt,
        "--count",      "100",
        "--outdir",     $GenreDir,
        "--seeds-dir",  "seeds",
        "--vocal-mask"
    )

    if (Test-Path $SeedPool) {
        Write-Host "  seed-pool : $SeedPool"
        $pyArgs += "--seed-pool"
        $pyArgs += $SeedPool
        $pyArgs += "--mutation-factor"
        $pyArgs += "0.05"
    } else {
        Write-Host "  [WARN] No vocals_generation_2 report - free exploration" -ForegroundColor Yellow
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
Write-Host "Running Pure Math Grader on vocals_generation_3..." -ForegroundColor Magenta

& $Python -m src.orchestration.telemetry_grader_midi --batch-dir $OutDir

$TotalTime = ((Get-Date) - $StartAll).ToString("hh\:mm\:ss")
Write-Host ""
Write-Host ("Vocals Generation 3 complete.  Total time: $TotalTime") -ForegroundColor Green

# ── Cross-generation comparison ───────────────────────────────
Write-Host ""
Write-Host "Running cross-generation comparison..." -ForegroundColor Magenta
& $Python compare_generations.py vocals_generation_1 vocals_generation_2 vocals_generation_3
