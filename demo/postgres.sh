#!/bin/sh

sudo apt update
sudo apt install postgresql postgresql-contrib -y
sudo -u postgres sh -c "psql -c \"CREATE USER cloud WITH PASSWORD 'cloud';\" && createdb -O cloud tasks"
sudo -u postgres sed -i "s/^#listen_addresses/listen_addresses = '*' #/g" /etc/postgresql/10/main/postgresql.conf
sudo -u postgres sh -c 'echo "host all all 0.0.0.0/0 md5" >> /etc/postgresql/10/main/pg_hba.conf'
sudo systemctl restart postgresql
