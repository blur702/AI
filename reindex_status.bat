@echo off
REM Show Weaviate ingestion status and pending queue

echo.
echo ========================================
echo  Weaviate Ingestion Status
echo ========================================
echo.

echo --- Collection Status ---
python -m api_gateway.services.ingestion_trigger status

echo.
echo --- Pending Queue ---
python -m api_gateway.services.ingestion_trigger queue
