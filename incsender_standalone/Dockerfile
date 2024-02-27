FROM python:3-slim

WORKDIR /opt/incsender

COPY ./script .

RUN pip install -r requirements.txt

CMD [ "python", "./incsender.py"]
