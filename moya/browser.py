class Browser(object):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "<browser '{}'>".format(self.name)
