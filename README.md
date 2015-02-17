# Moya

Moya is a Web Application server, written in Python.

## Installation

You can install from PyPi with the following:

```
pip install moya
```

Or download the repos and run the following:

```
python setup.py install
```

Whichever method you use, this will add a `moya` command line application.

## Running a project

See the `example projects` directory for an example. The is a Twitter clone there.

Navigate to the project you want to run, then do the following:

```
moya db sync
moya auth#cmd.init
```

This will initialize the database and users system. You only need to do this once.

To run a development server, do the following:

```
moya runserver
```

And navigate to http://127.0.0.1:8000

## More information

See the [Moya Homepage](http://www.moyaproject.com/) for more information. Or go straight to [Moya's Documentation](http://docs.moyaproject.com/).