"""
WSGI config for Reddit Sub Analyzer.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reddit_analyzer.settings')

application = get_wsgi_application()
