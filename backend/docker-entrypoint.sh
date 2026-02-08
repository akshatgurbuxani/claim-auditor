#!/bin/sh
if [ "$MODE" = "api" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
else
    exec streamlit run streamlit_app.py --server.port "${PORT:-8501}" --server.address 0.0.0.0
fi
