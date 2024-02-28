FROM python:3-slim

WORKDIR /opt/incsender

COPY ./script .

RUN pip install --progress-bar off -r requirements.txt

CMD [ "python", "./incsender.py"]
