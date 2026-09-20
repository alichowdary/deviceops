FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY deviceops_api/ ./deviceops_api/

RUN pip install --no-cache-dir . \
    && addgroup --system deviceops \
    && adduser --system --ingroup deviceops deviceops

COPY alembic.ini ./
COPY migrations/ ./migrations/

USER deviceops

EXPOSE 8000

CMD ["uvicorn", "deviceops_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
