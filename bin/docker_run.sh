# Startup script for running Zamboni under Docker.

# Check database exists. If not create it first.
mysql -u root --host mysql_1 -e 'use zamboni;'
if [ $? -ne 0 ]; then
    echo "Zamboni database doesn't exist. Let's create it"
    mysql -u root --host mysql_1 -e 'create database zamboni'
    echo "Since we didn't have a db. Let's grab some data"
    wget --no-check-certificate -P /tmp https://landfill-mkt.allizom.org/db_data/landfill-`date +%Y-%m-%d`.sql.gz
    zcat /tmp/landfill-`date +%Y-%m-%d`.sql.gz | mysql -u root --host mysql_1 zamboni
    echo "And now lets run the migrations to update"
    schematic migrations/
fi

python manage.py runserver 0.0.0.0:2600
