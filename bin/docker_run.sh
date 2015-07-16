# Startup script for running Zamboni under Docker.

# Check for mysql being up and running.
mysqladmin -u root --host mysql_1 --silent --wait=30 ping || exit 1

# Check database exists. If not create it first.
mysql -u root --host mysql_1 -e 'use zamboni;'
if [ $? -ne 0 ]; then
    echo "Zamboni database doesn't exist. Let's create it"
    mysql -u root --host mysql_1 -e 'create database zamboni default character set=utf8 collate=utf8_general_ci;'
    echo "Syncing db..."
    python manage.py migrate --noinput
    echo "Initialising data..."
    python manage.py loaddata init
    echo "Creating the initial index"
    python manage.py reindex
    echo "Creating fake apps."
    python manage.py generate_feed
fi

python manage.py runserver 0.0.0.0:2600
