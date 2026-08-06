FROM python:3.14-slim

WORKDIR /app

# The project is an installable package (pyproject declares `app` and `evals`), so all declared
# package sources must be present before `pip install .` can build the wheel.
COPY pyproject.toml ./
COPY app ./app
COPY evals ./evals
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
