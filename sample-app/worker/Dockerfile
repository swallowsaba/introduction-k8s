FROM python:3.12-slim
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -d /app app
WORKDIR /app
RUN pip install --no-cache-dir \
    sqlalchemy==2.0.35 \
    psycopg[binary]==3.2.2 \
    redis==5.0.8
COPY notify.py .
USER 1000
CMD ["python","notify.py"]
