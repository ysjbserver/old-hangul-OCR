web: env PYTHONDONTWRITEBYTECODE=1 MALLOC_ARENA_MAX=2 MALLOC_MMAP_THRESHOLD_=131072 gunicorn --bind=0.0.0.0:8000 --workers=1 --threads=4 --timeout=900 app:app
