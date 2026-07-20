$genres = @(
    @{ prompt = "upbeat pop song bright happy";           outdir = "batch_output/pop"       },
    @{ prompt = "hip hop beat groovy soulful";            outdir = "batch_output/hiphop"    },
    @{ prompt = "aggressive dark trap beat";              outdir = "batch_output/trap"       },
    @{ prompt = "epic cinematic orchestral score";        outdir = "batch_output/cinematic"  },
    @{ prompt = "classical orchestral symphonic piece";   outdir = "batch_output/classical"  },
    @{ prompt = "driving techno beat industrial";         outdir = "batch_output/techno"     },
    @{ prompt = "j-pop bright anime uplifting";           outdir = "batch_output/jpop"       },
    @{ prompt = "phonk drift dark aggressive";            outdir = "batch_output/phonk"      },
    @{ prompt = "edm electronic dance energetic";         outdir = "batch_output/edm"        },
    @{ prompt = "house music groovy deep funky";          outdir = "batch_output/house"      }
)

foreach ($g in $genres) {
    Write-Host "`n=== Starting: $($g.outdir) ===" -ForegroundColor Cyan
    python -m src.orchestration.batch_commander `
        --prompt $g.prompt `
        --count 100 `
        --outdir $g.outdir `
        --seeds-dir seeds
}

Write-Host "`nAll 10 genres done." -ForegroundColor Green
