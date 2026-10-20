import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()

from django.test import RequestFactory
from ColorAdminApp.views import index, dashboardv3
from ColorAdminApp.utils.context_processors import sidebar_menu

factory = RequestFactory()
request = factory.get('/')

print("Testing sidebar_menu...")
try:
    context = sidebar_menu(request)
    print("sidebar_menu successful")
except Exception as e:
    print(f"sidebar_menu failed: {e}")

print("Testing dashboardv3 render...")
try:
    response = dashboardv3(request)
    print(f"dashboardv3 status: {response.status_code}")
except Exception as e:
    print(f"dashboardv3 failed: {e}")
