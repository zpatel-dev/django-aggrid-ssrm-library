from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('ssrm/', views.athletes_ssrm, name='athletes-ssrm'),
    path('column-values/', views.athletes_column_values, name='athletes-column-values'),
]
