FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV FLASK_APP=app.py
ENV BLUEK9_USERNAME=bluek9
ENV BLUEK9_PASSWORD=warhammer
ENV BLUEK9_SECRET=change-me
CMD ["python", "app.py"]
