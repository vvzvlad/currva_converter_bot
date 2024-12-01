FROM python:3.11-slim

WORKDIR /app
RUN mkdir -p data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY currva_converter_bot.py .
COPY exchange_rates_manager.py .
COPY currency_formatter.py .
COPY currency_parser.py .
COPY statistics_manager.py .

CMD ["python", "currva_converter_bot.py"]