"""
Relrest request specification implementation.
"""

class Request(object):
    """
    Represent a REST request.
    """

    def __init__(self, uri=''):
        self.resource = None
        self.identifier = None
        self.fields = []
        self.filters = []
        self.joins = []
        self.limit = None
        self.order = []

        self.loads(uri)

    @classmethod
    def loads(cls, uri):
        """
        Return an instance of Request from `uri`.
        """
        pass

    def dumps(self):
        """
        Return an uri from the state of this instance.
        """
        pass

class Resource(object):
    pass

class Identifier(object):
    pass

class Field(object):
    pass

class Filter(object):
    pass

class Join(object):
    pass

class Limit(object):
    pass

class Order(object):
    pass