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

## Example Projects

In addition to the `example projects` directory in the Moya repos, you can check out the following complete projects:

* [Social Links](https://github.com/moyaproject/sociallinks)
  A social linking (Reddit like) application

* [Short URL](https://github.com/moyaproject/shorturl)
  A super simple URL shortener application

## Running a project

Navigate to the project directory you want to run, then do the following:

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


## Package Index

Find packages for Moya on the [Moya Package Index](https://packages.moyaproject.com).

Install packages `moya-pm` which comes with Moya:

```
moya-pm install moya.sociallinks
```


## More Information

See the [Moya Homepage](http://www.moyaproject.com/) for more information. Or go straight to [Moya's Documentation](http://docs.moyaproject.com/).