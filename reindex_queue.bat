@echo off
REM Process the Weaviate ingestion queue
REM Run this when you're done using LLMs and want to update the vector database
REM with changes made since your last commit(s).

echo.
echo ========================================
echo  Weaviate Ingestion Queue Processor
echo ========================================
echo.

REM Check if queue file exists
if not exist "D:\AI\logs\ingestion_queue.txt" (
    echo No queued files to process.
    echo.
    echo The queue is populated by git commits. Make some commits with
    echo code or documentation changes, then run this script.
    goto :end
)

REM Show what's queued
echo Checking queue...
python -m api_gateway.services.ingestion_trigger queue

echo.
echo ----------------------------------------
echo Starting ingestion...
echo ----------------------------------------
echo.

REM Process the queue
python -m api_gateway.services.ingestion_trigger process-queue

:end
echo.
pause
