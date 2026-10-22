FROM python:3.12
ENV PYTHONUNBUFFERED 1
ARG REQUIREMENTS

WORKDIR /app

# need to manually install chrome dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
COPY requirements-test.txt /app/
RUN echo $REQUIREMENTS
RUN pip install -r $REQUIREMENTS
COPY ./lti/ /app/
EXPOSE 8000
# To run Gunicorn AND RQ worker:
CMD ["/bin/sh", "-c", "./prestart.sh"]
