web: gunicorn reddit_analyzer.wsgi:application --bind 0.0.0.0:$PORT --workers 2
worker: celery -A reddit_analyzer worker -l info --concurrency 1
beat: celery -A reddit_analyzer beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
