FROM python:3.13.9-slim
WORKDIR /bot
COPY bot.py world.py /bot/
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
