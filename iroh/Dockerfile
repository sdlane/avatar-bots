 FROM python:3

 RUN mkdir -p /usr/src/bot
 WORKDIR /usr/src/bot

 COPY ./iroh .
 RUN python -m venv env
 RUN pip install --no-cache-dir -r requirements.txt


 CMD [ "python3", "iroh.py" ]