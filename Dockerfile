FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/static/img && chmod 777 /app/data /app/static/img

ENV FLASK_APP=src/entrypoints/flask_app.py
ENV DATABASE_URL=sqlite:////app/data/redteam.db
ENV SECRET_KEY=change-this-in-production
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=admin123

EXPOSE 7331

CMD ["gunicorn", "--bind", "0.0.0.0:7331", "--workers", "2", "--timeout", "60", "wsgi:app"]
