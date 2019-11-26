FROM python:3.7.0-slim-stretch

# Install System Dependencies
RUN apt update -y && apt upgrade -y
RUN apt install git gcc libffi-dev -y

# Acquire Codebase
WORKDIR /code
COPY . /code

# Install Monitor Dependencies
RUN pip3 install -U pip
RUN pip3 install . -r requirements.txt

ENTRYPOINT ["nucypher-monitor"]
