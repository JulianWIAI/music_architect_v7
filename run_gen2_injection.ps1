# Gen 2 - Golden Matrix Injection for all 10 genres

$batchDir = "batch_output"
$gen2Dir  = "batch_gen2"

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
    $reportPath = "$batchDir\$genre\math_fitness_report.json"
    $outDir     = "$gen2Dir\$genre"
    $prompt     = $prompts[$genre]

    Write-Host ""
    Write-Host "=== Gen 2 - $($genre.ToUpper()) ===" -ForegroundColor Cyan
    Write-Host "    seed-pool : $reportPath" -ForegroundColor DarkGray
    Write-Host "    output    : $outDir"     -ForegroundColor DarkGray

    python -m src.orchestration.batch_commander --prompt $prompt --count 100 --outdir $outDir --seeds-dir seeds --seed-pool $reportPath --mutation-factor 0.05
}

Write-Host ""
Write-Host "Gen 2 complete. All genres written to '$gen2Dir'" -ForegroundColor Green
