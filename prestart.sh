#! /usr/bin/env bash

# Let the DB start
sleep 10;

FILE=/etc/nginx/conf.d/certs/nginx-selfsigned.key &&
if [ -f "/etc/nginx/conf.d/certs/nginx-selfsigned.key" ]; then
  echo "/etc/nginx/conf.d/certs/nginx-selfsigned.key exists."
else 
mkdir /etc/nginx/conf.d/certs/
openssl req -x509 -nodes -days 365 -subj "/C=CA/ST=QC/O=Company, Inc./CN=localhost" -addext "subjectAltName=DNS:localhost" -newkey rsa:2048 -keyout /etc/nginx/conf.d/certs/nginx-selfsigned.key -out /etc/nginx/conf.d/certs/nginx-selfsigned.crt
fi 