#!/bin/bash

set -e

echo "Collecting static files"
python manage.py collectstatic --noinput

echo "Applying database migrations"
python manage.py migrate --fake-initial

if [ $ENVIRONMENT == 'dev' ]
then
    echo "Loading superuser fixture"
    python manage.py loaddata zh/fixtures/superuser.json &
fi

echo "Loading data fixture"
python manage.py loaddata zh/fixtures/data.json &

exec gunicorn "zh.wsgi" -c gunicorn.conf.py --bind 0.0.0.0:$PORT -w $GUNICORN_WORKERS --reload
