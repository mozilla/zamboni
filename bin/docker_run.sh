# Startup script for running Zamboni under Docker.

# Check database exists. If not create it first.
mysql -u root --host mysql_1 -e 'use zamboni;'
if [ $? -ne 0 ]; then
    echo "Zamboni database doesn't exist. Let's create it"
    mysql -u root --host mysql_1 -e 'create database zamboni'
    echo "Syncing db..."
    python manage.py syncdb
    echo "Initialising data..."
    python manage.py loaddata init
    echo "Running db migrations for the first time."
    schematic migrations/
fi

python manage.py runserver 0.0.0.0:2600
