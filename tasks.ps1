param([string]$Task = "dev", [string]$msg = "")

# Load .env into current process environment
Get-Content .env | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

switch ($Task) {
    "dev" {
        alembic upgrade head
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        uvicorn app.main:app --reload
    }
    "reset" {
        $env:PGPASSWORD = $env:DB_PASSWORD
        psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME `
            -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "Database reset complete. Run '.\tasks.ps1 dev' to recreate schema."
    }
    "migrate" {
        if (-not $msg) { $msg = Read-Host "Migration message" }
        alembic revision --autogenerate -m $msg
    }
    default {
        Write-Host "Usage: .\tasks.ps1 <dev|reset|migrate> [-msg 'description']"
    }
}
