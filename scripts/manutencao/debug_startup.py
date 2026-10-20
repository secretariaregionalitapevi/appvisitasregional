import os
import sys

print("Step 1: Setting DJANGO_SETTINGS_MODULE")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')

try:
    print("Step 2: Importing django")
    import django
    print("Step 3: Setup django")
    django.setup()
    print("Step 4: Importing settings")
    from django.conf import settings
    print("Step 5: Initialization successful")
except Exception as e:
    print(f"Error during startup: {e}")
    import traceback
    traceback.print_exc()
