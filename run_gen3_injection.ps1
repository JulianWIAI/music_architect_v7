# Gen 3 - Golden Matrix Injection (tighter mutation) for all 10 genres
# Reads golden matrices from batch_gen2/<genre>/math_fitness_report.json
# Writes new tracks to batch_gen3/<genre>/

$gen2Dir  = "batch_gen2"
$gen3Dir  = "batch_gen3"

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
    $reportPath = "$gen2Dir\$genre\math_fitness_report.json"
    $outDir     = "$gen3Dir\$genre"
    $prompt     = $prompts[$genre]

    Write-Host ""
    Write-Host "=== Gen 3 - $($genre.ToUpper()) ===" -ForegroundColor Magenta
    Write-Host "    seed-pool : $reportPath" -ForegroundColor DarkGray
    Write-Host "    output    : $outDir"     -ForegroundColor DarkGray

    python -m src.orchestration.batch_commander --prompt $prompt --count 100 --outdir $outDir --seeds-dir seeds --seed-pool $reportPath --mutation-factor 0.03
}

Write-Host ""
Write-Host "Gen 3 complete. All genres written to '$gen3Dir'" -ForegroundColor Magenta
