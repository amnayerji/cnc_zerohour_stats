FROM python:3.12
WORKDIR /app
ENV PYTHONUNBUFFERED 1

RUN pip install poetry
COPY pyproject.toml poetry.lock ./

RUN RUN set -eux; \
    poetry config virtualenvs.create false; \
    poetry install -n --no-ansi --no-root --no-cache

COPY . .

EXPOSE $PORT
CMD ["./docker-entrypoint.sh"]
