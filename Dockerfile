FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WATCH_DB=/data/watch.db

# Обычный пользователь вместо root; в /data лежит база
RUN useradd --create-home --uid 1000 watch \
    && mkdir /data \
    && chown watch:watch /data

WORKDIR /app
# Зависимостей нет — только стандартная библиотека, поэтому pip не нужен
COPY watchlog/ ./watchlog/

USER watch
VOLUME /data

ENTRYPOINT ["python", "-m", "watchlog"]
CMD ["--help"]
