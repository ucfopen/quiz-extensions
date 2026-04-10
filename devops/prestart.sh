echo "Starting gunicorn..."
gunicorn --conf gunicorn_conf.py --bind 0.0.0.0:8000 views:app &
echo "Starting RQ..."
/bin/sh -c 'rq worker quizext --url $REDIS_URL'
