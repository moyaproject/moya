from moya.wsgi import Application

application = Application('./', 'production.ini', server='main', logging="prodlogging.ini")
