@echo off
cd /d D:\AI\api_gateway
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo API Gateway environment setup complete.

