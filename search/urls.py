"""
URL configuration for search app.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('job/<str:job_id>/', views.home_with_job, name='home_with_job'),
    path('logs/', views.logs, name='logs'),
    path('all-the-subs/', views.all_subs, name='all_subs'),
    path('help/', views.help_page, name='help'),
    path('docs/', views.developer_docs, name='developer_docs'),

    # API endpoints
    path('status/<str:job_id>/', views.status, name='status'),
    path('stop/<str:job_id>/', views.stop_job, name='stop_job'),
    path('job/<str:job_id>/download.csv', views.job_download_csv, name='job_download_csv'),

    path('api/recent-runs/', views.api_recent_runs, name='api_recent_runs'),
    path('api/queue/', views.api_queue, name='api_queue'),
    path('api/subreddits/', views.api_subreddits, name='api_subreddits'),

    # Legacy redirect
    path('sub_search/', views.home, name='sub_search'),

    # Favicon
    path('favicon.ico', views.favicon, name='favicon'),
]
