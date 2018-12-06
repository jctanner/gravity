#!/bin/bash

export GRAVITY_VAR_DIR="/var/cache/gravity"
export CELERY_BROKER_URL="pyamqp://admin:mypass@172.20.0.2:5672"
export CELERY_RESULT_BACKEND="mongodb://172.20.0.3:27017"
export CELERY_MONGODB_BACKEND_DATABASE="gravity"
export CELERY_MONGODB_BACKEND_COLLECTION="results"

python flaskapp.py
