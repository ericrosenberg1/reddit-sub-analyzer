"""
URL configuration for nodes app.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.nodes_home, name='nodes_home'),
    path('join/', views.node_join, name='node_join'),
    path('manage/<str:token>/', views.node_manage, name='node_manage'),
]
