# Point the workspace at the driving docs without moving them.
#
# The apply workflow reads identity docs, the job-search session context and the
# resume generator. Those live in OneDrive and ~/.claude so they stay synced and
# shared with other tooling, but an agent rooted in this repo should not be
# reaching outside it. Junctions inside profile/ (gitignored) give every path an
# in-workspace form while the files stay where they are.
#
# Junctions, not symlinks: they need no administrator rights.
# Removing one (`rmdir profile\inputs`) deletes only the link, never the target.
#
#   powershell -ExecutionPolicy Bypass -File scripts\link_profile_dirs.ps1

$ErrorActionPreference = "Stop"
$profileDir = Join-Path $PSScriptRoot "..\profile" | Resolve-Path

$links = @(
  @{ name = "inputs";       target = "$env:USERPROFILE\OneDrive\Documents\Job Search\2026\inputs" },
  @{ name = "applications"; target = "$env:USERPROFILE\OneDrive\Documents\Job Search\2026\applications" },
  @{ name = "ai_skills";    target = "$env:USERPROFILE\.claude\ai_skills" }
)

foreach ($l in $links) {
  $link = Join-Path $profileDir $l.name
  if (Test-Path $link) { Write-Host "already linked: profile\$($l.name)"; continue }
  if (-not (Test-Path $l.target)) {
    Write-Warning "target missing, skipping: $($l.target)"
    continue
  }
  cmd /c mklink /J "`"$link`"" "`"$($l.target)`"" | Out-Null
  Write-Host "linked: profile\$($l.name) -> $($l.target)"
}

Write-Host ""
Write-Host "profile/profile.toml [paths] should now use the in-workspace form:"
Write-Host '  inputs_dir           = "profile/inputs"'
Write-Host '  applications_dir     = "profile/applications"'
Write-Host '  session_context_path = "profile/ai_skills/SESSION_CONTEXT_Jobsearch.md"'
Write-Host '  resume_skill_path    = "profile/ai_skills/resume_generator/generate_resume.py"'
