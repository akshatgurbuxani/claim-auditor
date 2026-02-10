FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data

# Don't set PORT here - let docker-entrypoint.sh defaults handle it
# (8501 for streamlit, 8000 for api)
ENV MODE=streamlit

EXPOSE 8501 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
