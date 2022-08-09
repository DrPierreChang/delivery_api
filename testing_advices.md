Testing advices
===============

1. For calling views use [django test client](https://docs.djangoproject.com/en/1.10/topics/testing/tools/#the-test-client). TestCase object contains it as client field.

    Notes:

    - Django test client doesn't call server. It create WSGIRequest object and call request handler with it as argument. If you need run tests on the "live" server you can use [LiveServerTestCase](https://docs.djangoproject.com/en/1.10/topics/testing/tools/#liveservertestcase).

2. Separate tests to the more simple. One test must check one action.

    Notes:

    - Complex tests are admissible if that test case have been discovered as a result of fuсtional testing.

3. Use fixtures and direct calling to the database. There are not reason to duplicate tested functional. (http://www.django-rest-framework.org/api-guide/testing/#forcing-authentication)

4. Tests have been perfomed within a single transaction. After database rollback to the initial state. So you can not be afraid of data conflict between tests. Also you cannot reuse data from one test in another. If you use additional database remove data from it after test.

5. For testing using side services you can use [mock](https://pypi.python.org/pypi/mock) package. It allow you to replace your functional (function) with mock objects and make assertions about how they have been used.

6. For check test coverage you can use "coverage" package. (https://coverage.readthedocs.io/)

7. "tox" package help you to run tests on different environment. (https://tox.readthedocs.io/en/latest/)


TestCase class architecture
---------------------------


```python
class TestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        "This method have been called once at the begining of testing."
        
    def setUp(self):
        "This method have been called before every test."
        
    def tearDown(self):
        "This method have been called after every test."
        
    def test_1(self):
        "Test 1."
        
    def test_2(self):
        "Test 2."
```


Mock usage example
------------------


Let's we have view that use send_sms. Test case:

```python
from mock import patch


class TestCase(TestCase):
    @patch('path.to.send_sms')
    def test_view(self, send_sms_mock):
        view()
        assert send_sms_mock.called
```

In patch decorator send_sms function replace with MagicMock object that have been transmitted to test as argument. After this view call send_sms_mock object instead for send_sms and it store their calls. In this case original function havn't been called.

Notes:

- Patch decorator replace function in namespace that you specify. For example, if you import function from tasks into views and use it you must specify import path to views module.


Coverage usage example
----------------------


```bash
$ coverage run manage.py test
Creating test database for alias 'default'...
...


$ coverage report -m tasks/view.py
Name             Stmts   Miss  Cover   Missing
----------------------------------------------
tasks/views.py      99     56    43%   32-40, 47-57, 67-80, 84-98, 102-105, 109-118, 121, 129-131, 134-137


$ coverage html tasks/{,**/}*.py
```


tox.ini example
---------------


```
[tox]
envlist =
    {py27,py33,py34,py35}-django18,
    {py27,py34,py35}-django{19,110},
[testenv]
deps =
    django18: django>=1.8,<1.9
    django19: django>=1.9,<1.10
    django110: django>=1.10,<1.11
    mock
    coverage
commands =
    coverage erase
    coverage run ./runtests.py
    coverage report --fail-under=90 --include=package/*.py --skip-covered
```
