#!/bin/bash

# load environment variables for postactivate
. ./env.config

PROJECT_NAME="delivery"

if [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ]; then
    echo "declare environment variables in env.config"
    exit 0
fi

# initialize virtualenvwrapper
source "/usr/local/bin/virtualenvwrapper.sh"
WORKON_HOME=$HOME/.virtualenvs


# create virtualenv
if [ -d "$WORKON_HOME/$PROJECT_NAME" ]; then
    echo "$PROJECT_NAME virtualenv already exists."
    workon $PROJECT_NAME
else
    mkvirtualenv $PROJECT_NAME --python=python3
fi

# write variables to postactivate
postactivate_file_path="$WORKON_HOME/$PROJECT_NAME/bin/postactivate"

printf 'export DB_USER="%s"\nexport DB_PASSWORD="%s"\nexport ENV="%s"' "$DB_USER" "$DB_PASSWORD" "$ENV" > "$postactivate_file_path"

# install requirements
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    echo "requirements.txt not found"
fi

# create database
PGPASSWORD=$DB_PASSWORD psql -U "$DB_USER" -c "CREATE DATABASE $PROJECT_NAME;"

# on the next step django.conf.setting will tru to get DB_USER , DB_PASSWORD, ENV from environment
# so we need to reload virtualenv
deactivate
workon $PROJECT_NAME

# make manage.py executable
chmod 755 manage.py

# change rights for *.pem
chmod 600 *.pem

# link pre-commit.sh to git's pre-commit for run before every commit
ln -s ../../pre-commit.sh .git/hooks/pre-commit
# add permissions to pre-commit file
chmod a+x .git/hooks/pre-commit

echo "RUNNING INITIAL MIGRATIONS"
python manage.py migrate
echo "CREATE SUPERUSER"
python manage.py createsuperuser

deactivate
exit 0
