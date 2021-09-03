FROM tiangolo/uwsgi-nginx-flask:python3.7
ARG REQUIREMENTS
RUN apt-get update && apt-get install -y ca-certificates
RUN apt-get update && apt-get -y install libffi-dev gcc python3-dev libffi-dev libssl-dev libxml2-dev libxmlsec1-dev libxmlsec1-openssl
RUN pip install --upgrade pip
WORKDIR /app
COPY requirements.txt /app/
COPY devops/nginx.conf /app/
COPY devops/uwsgi.ini /app/

COPY $REQUIREMENTS /app/
RUN echo $REQUIREMENTS
RUN pip install -r $REQUIREMENTS
COPY . /app/