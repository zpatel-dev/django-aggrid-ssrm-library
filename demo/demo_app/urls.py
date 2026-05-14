from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('ssrm/', views.sales_ssrm, name='sales-ssrm'),
    path('column-values/', views.sales_column_values, name='sales-column-values'),
]
