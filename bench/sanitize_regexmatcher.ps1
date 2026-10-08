# Sanitizer record for RegexMatcher v2's whole test suite on Windows (lab host W): AddressSanitizer,
# MSVC or clang-cl (design/round2/regexmatcher-v2.md, section 8.4). Windows counterpart of
# bench/sanitize_regexmatcher.sh; the record is written by the same bench/regexmatcher_record.py.
#
# Usage: sanitize_regexmatcher.ps1 -Commit SHA [-RmRepo DIR] [-GoogleTestDir DIR] [-Compiler cl|clang-cl]
#                                  [-RecordsDir DIR] [-Work DIR] [-Note TEXT]
#
# Exports Commit from the RegexMatcher clone RmRepo (git archive, so the checkout's working files
# and branch do not matter), configures it with its tests and REGEXMATCHER_SANITIZER=address
# (Ninja, Release, from a vcvars shell so the ASan runtime DLL resolves), builds every target, and
# runs the whole CTest suite with every test's output kept (ctest -V): the regex engine's tests,
# the route matcher's, the compile-time tables (REGEXMATCHER_CT_JOBS=1, their default) and the
# negative-compilation cases. Then lab/bin/inputs_hash.py hashes what the test targets compiled
# (project mode, root label regexmatcher) with the hash of their inputs under
# regexmatcher/include/ (CRLF read as LF, so it can equal the L records' hash of the same commit).
# Green: the build succeeded, every test passed, the inputs were hashed, and the build and test
# output hold no sanitizer report (the shared report pattern below, checked by
# lab/bin/test_report_pattern.sh; bench/regexmatcher_record.py applies it, and this script checks
# that its own count, .NET's regex over the same logs, is the same).
#
# Writes RecordsDir\regexmatcher-<commit, 9 characters>-W-asan.json (-W-asan-clangcl.json for
# clang-cl). Only records with the host part L gate a measured build (bench/gate_lib.py); P2
# measures on L, so a W record is extra coverage. MSVC and LLVM ship no LeakSanitizer and no
# UndefinedBehaviorSanitizer runtime for this target.
#
# GoogleTest: with -GoogleTestDir, that local source (FETCHCONTENT_SOURCE_DIR_GOOGLETEST), whose
# origin the -Note should state; without it, RegexMatcher's own CMake fetches GoogleTest from its
# official repository at the commit RegexMatcher pins (v1.15.2).
#
# Logs: %USERPROFILE%\lab\records-logs\<record>\ (build.log, ctest.log, inputs.json, inputs.err,
# SHA256SUMS), packed into <record>.tar.gz beside it, whose sha256 goes into the record and into
# <record>.tar.gz.sha256. A record whose log directory or archive exists is never made again.
# Build trees go to -Work (default %USERPROFILE%\lab\records-build\<record>).
#
# clang-cl: CMake links with lld-link directly, so clang-cl's driver never adds the ASan runtime;
# LDFLAGS names it (lld-link finds LLVM's copy before the MSVC one of the same name). LLVM's
# runtime directory goes first on PATH for the build and the tests, because the vcvars PATH holds
# MSVC's clang_rt.asan_dynamic-x86_64.dll, which a clang-cl binary cannot load. As in the Papers
# repo's lab/bin/sanitize.ps1.
param(
    [Parameter(Mandatory = $true)][string]$Commit,
    [string]$RmRepo = "D:\Dev\GitHub\RegexMatcher",
    [string]$GoogleTestDir = "",
    [string]$Compiler = "cl",
    [string]$RecordsDir = "",
    [string]$Work = "",
    [string]$Note = ""
)
$ErrorActionPreference = "Stop"
# A sanitizer report: the first line of every report the runtimes print and every SUMMARY line;
# the same text as the Papers repo's lab/bin/sanitize.sh, checked by lab/bin/test_report_pattern.sh.
$ReportPattern = 'ERROR: (Address|Memory|Leak|Thread)Sanitizer|WARNING: (Memory|Thread)Sanitizer|SUMMARY: [A-Za-z]+Sanitizer|runtime error:'

$here = $PSScriptRoot
$repo = Split-Path $here -Parent
$papers = (Resolve-Path (Join-Path $repo "..\..")).Path
if (-not $RecordsDir) { $RecordsDir = Join-Path $papers "lab\sanitizer-records" }
New-Item -ItemType Directory -Force $RecordsDir | Out-Null
$RecordsDir = (Resolve-Path $RecordsDir).Path
$inputsPy = Join-Path $papers "lab\bin\inputs_hash.py"

$full = (git -C $RmRepo rev-parse --verify "$Commit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or -not $full) { throw "no commit $Commit in $RmRepo" }

$suffix = ""
$sanitizer = "msvc-asan"
$ldflags = ""
$runtimeDir = ""
if ($Compiler -match '^clang-cl') {
    $suffix = "-clangcl"
    $sanitizer = "clang-cl-asan"
    $runtimeDir = Join-Path ((& $Compiler /clang:-print-resource-dir) | Select-Object -First 1).Trim() "lib\windows"
    if (-not (Test-Path (Join-Path $runtimeDir "clang_rt.asan_dynamic-x86_64.dll"))) {
        throw "no clang_rt.asan_dynamic-x86_64.dll in $runtimeDir"
    }
    $ldflags = "clang_rt.asan_dynamic-x86_64.lib /include:__asan_seh_interceptor " +
               "/wholearchive:clang_rt.asan_dynamic_runtime_thunk-x86_64.lib"
} elseif ($Compiler -ne "cl") {
    throw "unsupported compiler '$Compiler' (cl or clang-cl)"
}

$record = "regexmatcher-" + $full.Substring(0, 9) + "-W-asan$suffix"
$logsRoot = Join-Path $env:USERPROFILE "lab\records-logs"
$logs = Join-Path $logsRoot $record
$tar = "$logs.tar.gz"
if ((Test-Path $logs) -or (Test-Path $tar)) { throw "$logs or $tar exists; record logs are never overwritten" }
if (-not $Work) { $Work = Join-Path $env:USERPROFILE "lab\records-build\$record" }
New-Item -ItemType Directory -Force $logs | Out-Null
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
$src = Join-Path $Work "src"
$bin = Join-Path $Work "build"
New-Item -ItemType Directory -Force $src | Out-Null
& git -C $RmRepo archive --format=tar -o (Join-Path $Work "src.tar") $full
if ($LASTEXITCODE -ne 0) { throw "cannot export $full" }
& tar.exe -xf (Join-Path $Work "src.tar") -C $src
if ($LASTEXITCODE -ne 0) { throw "cannot unpack $full" }

$asan = "detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1"
$options = "ASAN_OPTIONS=$asan"
$cmakeArgs = "-G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=$Compiler -DCMAKE_CXX_COMPILER=$Compiler " +
             "-DREGEXMATCHER_BUILD_TESTS=ON -DREGEXMATCHER_SANITIZER=address"
if ($GoogleTestDir) {
    $GoogleTestDir = (Resolve-Path $GoogleTestDir).Path
    $cmakeArgs += " -DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=$($GoogleTestDir -replace '\\', '/')"
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
$vcvars = Join-Path (& $vswhere -latest -products * -property installationPath) "VC\Auxiliary\Build\vcvarsall.bat"
if (-not (Test-Path $vcvars)) { throw "vcvarsall.bat not found" }
$head = @("@echo off", "call `"$vcvars`" x64 >nul || exit /b 1")
if ($ldflags) { $head += "set `"LDFLAGS=$ldflags`"" }
if ($runtimeDir) { $head += "set `"PATH=$runtimeDir;%PATH%`"" }
$head += "set `"ASAN_OPTIONS=$asan`""

# One cmd file per step, so each step's exit code is its own.
function Invoke-Step([string]$step, [string[]]$lines) {
    $bat = Join-Path $Work "$step.cmd"
    ($head + $lines + @("exit /b %ERRORLEVEL%")) | Set-Content -Encoding ascii $bat
    & cmd.exe /c $bat | Out-Host
    return $LASTEXITCODE
}

$start = Get-Date
$buildLog = Join-Path $logs "build.log"
$buildRc = Invoke-Step "build" @(
    "cmake -S `"$src`" -B `"$bin`" $cmakeArgs > `"$buildLog`" 2>&1 || exit /b 2"
    "cmake --build `"$bin`" >> `"$buildLog`" 2>&1 || exit /b 3"
    "cmd /c exit 0"
)
$ctestRc = -1
$inputsRc = -1
if ($buildRc -eq 0) {
    $ctestRc = Invoke-Step "ctest" @("cd /d `"$bin`"", "ctest -V > `"$(Join-Path $logs 'ctest.log')`" 2>&1")
    $inputsRc = Invoke-Step "inputs" @(
        "python `"$inputsPy`" --build `"rm=$bin`" --target route_tests --target route_checked_tests " +
        "--target route_ct_table_tests --target tests --root-label regexmatcher --label-hash regexmatcher/include/ " +
        "--out `"$(Join-Path $logs 'inputs.json')`" > nul 2> `"$(Join-Path $logs 'inputs.err')`""
    )
}
$seconds = [int]((Get-Date) - $start).TotalSeconds

# The report count by this script's pattern, to compare with the record writer's.
$reports = 0
foreach ($f in @("build.log", "ctest.log")) {
    $p = Join-Path $logs $f
    if (Test-Path $p) { $reports += @(Select-String -Path $p -Pattern $ReportPattern).Count }
}

# Every log's sha256, then the logs packed with the archive's sha256 beside it.
$sums = Get-ChildItem -File $logs | Where-Object { $_.Name -ne "SHA256SUMS" } | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower())  ./$($_.Name)"
}
[System.IO.File]::WriteAllText((Join-Path $logs "SHA256SUMS"), (($sums -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
& tar.exe -czf $tar -C $logsRoot $record
if ($LASTEXITCODE -ne 0) { throw "tar of $logs failed" }
$sha = (Get-FileHash -Algorithm SHA256 $tar).Hash.ToLower()
[System.IO.File]::WriteAllText("$tar.sha256", "$sha  $record.tar.gz`n", (New-Object System.Text.UTF8Encoding($false)))

$recordPath = Join-Path $RecordsDir "$record.json"
if ($ldflags) { $Note = ("$Note LDFLAGS=$ldflags; PATH first: $runtimeDir").Trim() }
# Windows PowerShell drops an empty argument, so every value is given as --name=value.
$writerArgs = @("--record=$recordPath", "--logs=$logs", "--logs-archive=$tar", "--logs-sha256=$sha",
                "--repo=cpp-for-everything/RegexMatcher (local branch v2/route-matcher)", "--commit=$full",
                "--sanitizer=$sanitizer", "--options=$options", "--cmake-args=$cmakeArgs",
                "--build-exit=$buildRc", "--ctest-exit=$ctestRc", "--inputs-exit=$inputsRc",
                "--seconds=$seconds", "--host=$env:COMPUTERNAME", "--note=$Note")
& python (Join-Path $here "regexmatcher_record.py") @writerArgs
$writerRc = $LASTEXITCODE
$written = Get-Content -Raw $recordPath | ConvertFrom-Json
if ($written.sanitizer_reports -ne $reports) {
    throw "the record counts $($written.sanitizer_reports) sanitizer reports, this script $reports"
}
exit $writerRc
