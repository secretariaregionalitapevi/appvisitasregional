#!/bin/bash
# Install dependencies
pip install -r requirements.txt

# Run collectstatic
python manage.py collectstatic --noinput

# Vercel serves the repository's /static directory through @vercel/static.
# Keep application-owned assets available there as part of the build as well.
cp -R ColorAdminApp/static/. static/
