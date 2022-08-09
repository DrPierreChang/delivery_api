1. Install pre-requisites
=========================

Virtualenv
----------
Standard installation with virtualevnwrapper.

PostgreSQL
----------
Standard installation.



# Standard project initialization
## 1. Create virtual environment


1. Clone repository: ``git clone https://bitbucket.org/razortheory/delivery.git``
2. Create virtual environment: ``mkvirtualenv delivery``
3. Install requirements ``pip install -r requirements-3.txt``
4. Edit $VIRTUAL_ENV/bin/postactivate to contain the following lines:


    export ENV=dev
    export DB_USER=your_psql_user
    export DB_PASSWORD=your_psql_user_pass
    export DEV_ADMIN_EMAIL=your_email


5. Deactivate and re-activate virtualenv:

```
deactivate
workon delivery
```

6. Add permissions for run pre-commit hook for git:
```
ln -s ../../pre-commit.sh .git/hooks/pre-commit
chmod a+x .git/hooks/pre-commit
```

## 2. Database

1. Create database table:

```
psql -Uyour_psql_user
CREATE DATABASE delivery;
```

2. Migrations: ``./manage.py migrate``
3. Create admin: ``./manage.py createsuperuser``
4. Run the server ``./manage.py runserver``


# Alternative project initialization
1. Clone repository: ``git clone https://bitbucket.org/razortheory/delivery.git``
2. Edit variables in env.config
3. **Make sure that you are not in any of existing virtual envs**
4. run ``./initproject.bash`` - will run all commands listed in standard initialization, including edition of postactivate
5. activate virtualenv ``workon delivery``
6. run ``./manage.py runserver``


Setup New Relic
---------------
See instructions in [`newrelic-readme.md`](newrelic-readme.md).
