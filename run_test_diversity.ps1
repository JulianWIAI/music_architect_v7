# Diversity fix verification — 10 tracks per genre, seeded from Gen3 golden matrices
# Uses the fixed config_from_golden (scale mutation + 5 BPM floor + 5-semitone root shift)
# Output: batch_test_fix/<genre>/

$gen3Dir  = "batch_gen3"
$testDir  = "batch_test_fix"

$genres = "pop","hiphop","trap","cinematic","classical","techno","jpop","phonk","edm","house"
$prompts = @{
    pop       = "upbeat pop song bright happy"
    hiphop    = "hip hop beat groovy soulful"
    trap      = "aggressive dark trap beat"
    cinematic = "epic cinematic orchestral score"
    classical = "classical orchestral symphonic piece"
    techno    = "driving techno beat industrial"
    jpop      = "j-pop bright anime uplifting"
    phonk     = "phonk drift dark aggressive"
    edm       = "edm electronic dance energetic"
    house     = "house music groovy deep funky"
}

foreach ($genre in $genres) {
    $reportPath = "$gen3Dir\$genre\math_fitness_report.json"
    $outDir     = "$testDir\$genre"
    $prompt     = $prompts[$genre]

    Write-Host ""
    Write-Host "=== TEST - $($genre.ToUpper()) ===" -ForegroundColor Yellow
    Write-Host "    seed-pool : $reportPath" -ForegroundColor DarkGray
    Write-Host "    output    : $outDir"     -ForegroundColor DarkGray

    if (-not (Test-Path $reportPath)) {
        Write-Host "    SKIP: no fitness report found" -ForegroundColor Red
        continue
    }

    python -m src.orchestration.batch_commander --prompt $prompt --count 10 --outdir $outDir --seeds-dir seeds --seed-pool $reportPath --mutation-factor 0.05
}

Write-Host ""
Write-Host "Test batch complete. Written to '$testDir'" -ForegroundColor Yellow
