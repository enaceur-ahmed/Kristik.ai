FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings \
    pandas numpy scipy scikit-learn openpyxl python-multipart \
    aiofiles python-dotenv httpx openai

RUN mkdir -p data uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
