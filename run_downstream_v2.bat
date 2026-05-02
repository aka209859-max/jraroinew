@echo off
cd /d E:\jraroinew
echo ============================================================
echo  DOWNSTREAM PIPELINE v2 (new COURSE_27 definition)
echo  Started: %DATE% %TIME%
echo ============================================================

echo.
echo [STEP 1/5] clean_and_reextract_bins (memory-efficient v2)...
py -3.12 -u -m backend.batch.clean_and_reextract_bins
if %ERRORLEVEL% neq 0 (
    echo [FAIL] clean_and_reextract_bins exited with %ERRORLEVEL%
    exit /b 1
)

echo.
echo [STEP 2/5] split_bins_by_sample_size...
py -3.12 -u -m backend.batch.split_bins_by_sample_size
if %ERRORLEVEL% neq 0 (
    echo [FAIL] split_bins_by_sample_size exited with %ERRORLEVEL%
    exit /b 1
)

echo.
echo [STEP 3/5] export_fragmentation_analysis...
py -3.12 -u -m backend.batch.export_fragmentation_analysis
if %ERRORLEVEL% neq 0 (
    echo [FAIL] export_fragmentation_analysis exited with %ERRORLEVEL%
    exit /b 1
)

echo.
echo [STEP 4/5] export_segment_summary...
py -3.12 -u -m backend.batch.export_segment_summary
if %ERRORLEVEL% neq 0 (
    echo [FAIL] export_segment_summary exited with %ERRORLEVEL%
    exit /b 1
)

echo.
echo [STEP 5/5] extract_premium_factors_v2...
py -3.12 -u -m backend.batch.extract_premium_factors_v2
if %ERRORLEVEL% neq 0 (
    echo [FAIL] extract_premium_factors_v2 exited with %ERRORLEVEL%
    exit /b 1
)

echo.
echo ============================================================
echo  ALL_DOWNSTREAM_DONE
echo  Finished: %DATE% %TIME%
echo ============================================================
