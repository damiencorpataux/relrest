"""
Rest Joint.

Terminology:

    - sqla: sqlalchemy
    - model: is a sqla declarative Base child class that represent a RDS table
    - column: is a sqla column property of a model that represent a RDS table column
    - result: is an instance of an sqla model that respresent an RDS table row

    - rest: representative state transfer
    - resource: is a lowercase string that represent a sqla model or record
    - record: is a json object representing a sqla result
    - recordtuple: is a json object representing a sqla result tuple
    - field: is a lowercase string that represent a sqla model column
    - id: is an integer that represent the primary key of a sqla model

    - uri: eg. /resource/id/field?filter=abc&/subresource=1
    - restjoint-request: is an object that is decoded from a given uri; this object represents
          a restjoint rest request on a resource (`see util.uri.decode()`)
          it is a central part of the framework !

Conventions:

    - field '+': to be described (todo: use inline notes from code)
    - field '-': to be described (todo: use inline notes from code)
    - resource '+': to be described (todo: use inline notes from code)

    - filter... to be described
    - join... to be described

TODO: unhardcode default primary key for models (currently 'id')
and make it configurable by the user, globally but also via an optional per-model mapping,
maybe via a hook like we do with the relational field (see `get_relcolumn()`).

TODO: make clean implementation of the relational field hook `get_relcolumn()`.
"""

from . import util

import sqlalchemy
from collections import defaultdict
import logging

log = logging.getLogger(__name__)  # logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(filename)s:%(lineno)s - %(name)s.%(funcName)s - %(levelname)s - %(message)s")


# Note: in uri, id '+' and '-' allow to specify a field without having to specify an id,
# eg: /author/+/name or /author/-/name?/artwork=123
#
# Value '-' returns a single record,
# value '+' returns a list of records.
reserved_ids = ["+", "-"]

# Note: in uri, resource '+' allow to not specify joins without having to specify a resource,
# eg: /author/+/name or /+?/author/artwork=12
#
# Value '+' returns the records for all the resources specified in joins.
#
# TODO: let specify a list of resources to limit the presence of resources in response,
#       eg: /topic,autor?/autor/artwork/topic
# reserved_resources = ["+"]  # FIXME: it is not used, actually...

class Service(object):

    # FIXME: make those defaults non-static
    default_field = 'id'  # default field for filters and joinpath decoder
    default_comparator = 'eq'  # default comparator for filters and joinpath decoder

    @property
    def model(self):
        """
        Mapping from rest resource name to sqla model.
        """
        return self._model

    @property
    def resource(self):
        """
        Mapping from sqla model to rest resource name (reverse mapping for `model`).
        """
        return self._resource

    def __init__(self, sqla_session, sqla_model_dict):
        """
        Create a rest service instance providing crud operations
        for the given sqla `models` and `session`.

        Argument `models` is an object whose properties contain the models to expose as rest resource.
        Argument `session` is a sqla session object.
        """
        super().__init__()

        for key, not_model in filter(lambda model: not util.is_model(model), sqla_model_dict.values()):
            raise ValueError(f"Argument sqla_model_dict contains a key '{key}'={model} which is not a sqla model")

        self._model = sqla_model_dict
        self._resource = {v: k for k, v in self._model.items()}
        self.session = sqla_session

    def decode(self, uri):
        """
        Return `util.uri.decode(uri)` with default field and comparator
        from this instance `default_field` and `default_comparator` properties.
        """
        return util.uri.decode(uri,
            default_resource=None,
            default_field=self.default_field,
            default_comparator=self.default_comparator)

    def create(self, resource, record):
        raise NotImplementedError()

    def read(self, uri):
        """
        Read and return record(s) for the given `uri`.
        """
        request = self.decode(uri)
        log.debug(f"Reading 'uri={uri}' decoded into {request}")

        return self.read_resource(
            resource=request["resource"],
            id=request["id"],
            fields=request["fields"],
            filters=request["filters"],
            joinpaths=request["joinpaths"],
            limit=request["limit"])

    def update(self, uri, record):
        """
        Update the existing resource `id` for with the given `record`.

        The given `record` can contain 0..n fields can be updated
        and fields do not exist in sqla model are ignored.
        """
        request = self.decode(uri)

        if request["field"]:
            raise ValueError(f"Update operation does not support fields in URI and field '{fields}' was given")

        return self.read_resource(
            resource=request["resource"],
            id=request["id"],
            record=record)

    def delete(self, resource, id):
        raise NotImplementedError()

    def read_resource(self, resource, id, fields, filters, joinpaths, limit):
        """
        Query database and return a single or multiple record(s) or recordtuple(s).

        Create a sqla query from the given arguments, execute the query, serialize the result
        and return a dict that is json serializable.

        Support wildcard filters on multiple fields using 'and' operator.
        Support joining tables in a chaining manner to filter on foreign fields (a joinpath),
        up to arbitrary degree of relationship.
        Support `resource='+'`, used to return recordtuples of multiple resources according the given `joinpath`. Eg:
            /+/artwork.id=1 or /+?/artwork/topic
        """

        # Create models to be queried in `session.query(models)`,
        # create base_model conditionally to be used as base model by filters and joinpaths.
        if resource in ("+", "-"):
            # Note: query on arbitrary resources based on the given joinpaths

            if id and id not in reserved_ids:
                raise ValueError(
                    f"Resource-less request with an id make little sense. Use id reserved id '+' "
                    f"and a query string filter on a specific resource id instead, eg: /+/+?/topic=1")

            if not joinpaths:
                raise ValueError(
                    f"Using resource '+' requires a joins-path specification, eg: /+?/topic/artwork")

            base_model = None  # base model will be set in query string processing below

            if resource == "+":
                # query all resources in joinpaths
                joinpath_resources = all_resources_in_joinpath = [joinnode[0] for joinpath in joinpaths for joinnode in joinpath]
            elif resource == "-":
                # query first resource of each joinpath in joinpaths
                joinpath_resources = first_resource_of_each_joinpath = [joinpath[0][0] for joinpath in joinpaths]

            models = [self.model[resource] for resource in joinpath_resources]

        else:
            # Note: normal query based on a single resource
            base_model = self.model[resource]
            models = [base_model]

        # Create base sqla query
        log.debug(f"Creating sqla query with models={models}")
        query = self.session.query(*models)
        if id and id not in reserved_ids:
            for model in models:
                query = query.filter(model.id == id)

        # Process and apply filters to sqla query
        for filter in filters:
            resource, field, comparator, value = filter

            if not resource:
                if base_model:
                    resource = self.resource[base_model]
                else:
                    raise ValueError(f"Filter '{filter}' is missing a resource component that is required in resourceless request, eg: resource.field.operator=1")

            queryfilter = self.make_filter(resource, field, comparator, value)
            query = query.filter(queryfilter)

        # Process and apply joinpaths to sqla query
        for joinpath in joinpaths:
            last_relmodel = None
            surrogate_base_model = None

            for joinnode in joinpath:
                relresource, relfield, comparator, value = joinnode
                relmodel = self.model[relresource]

                if value:
                    # Note: add join filter
                    relfilter = self.make_filter(*joinnode)
                    query = query.filter(relfilter)

                if not base_model and not surrogate_base_model:
                    # Note: simulate that a resource was given
                    # and that its valus is first element of the given joins path
                    surrogate_base_model = self.model[relresource]
                    continue

                # TODO: this hook should allow the user to specify a function to generate the name
                # of the local model column that is related to foreign model represented by relresource.
                get_relcolumn = lambda v: v
                relcolumn = get_relcolumn(relresource)

                # Note: adds a chain of joins and filters to the current query, in order to generate this kind of query:
                #   s.query(data.Author).join(data.Author.artwork).join(data.Artwork.activity).join(data.Activity.topic).filter(data.Topic.id.in_([1]))
                query = query.join(getattr(last_relmodel or surrogate_base_model or base_model, relcolumn))  # use base_model or surrogate_base_model for first iteration
                last_relmodel = self.model[relresource] # last_relmodel is used in next iteration to create the "joins chain"

        # Apply limit to sqla query
        query = query.limit(limit)

        # Handle field '_count'
        if "_count" in [field for f_resource, field in fields]:
            # Note: field _count is a virtual field that triggers the
            # return of dict(count = the number of records matched by the given uri query).
            return dict(_count=query.count())

        # Process and apply fields to sqla query
        for field in fields:
            f_resource, f_field = field

            if f_resource:
                model = self.model[f_resource]
            else:
                model = base_model

            if not model:
                raise ValueError(f"Field '{field}' is missing a resource component that is required in resourceless request, eg: resource.field")

            # apply field selection to sqla query select statement,
            # see https://docs.sqlalchemy.org/en/latest/orm/loading_columns.html
            try:
                # field is a property
                query = query.options(sqlalchemy.orm.Load(model).load_only(f_field))

            except sqlalchemy.orm.exc.LoaderStrategyException:
                # field is a relationship
                column = getattr(model, f_field)
                query = query.options(sqlalchemy.orm.joinedload(column).load_only('id'))  # hardcode to foreign field 'id'
                query = query.options(sqlalchemy.orm.Load(model).load_only('id'))  # to ensure limiting local fields, we set option load_only on local primary key (which is always loaded in anyway)

        # Serialize and return results
        # managing `result` as sqla model instance or sqla model instance tuple
        if not id or id == "+":
            results = query.all()
            return [util.serialize_result(self.resource, result) for result in results]

        if id or id == "-":
            result = query.one()
            return util.serialize_result(self.resource, result)

    def update_resource(self, resource, id, record):
        """
        TODO: implement mass update using filters and joinpaths ?
        """
        if not id or id in reserved_ids:
            # TODO: update using reserved_ids features is not yet implemented
            raise ValueError(f"Missing id in URI, or invaid id format '{id}'")

        query = self.session.query(self.model[resource])
        if id:
            query = query.filter_by(id=id)

        result = query.one()
        try:
            for key, value in record.items():
                # Note: this is disbled, but we keep it for now in case it was a good idea:
                # if (field and key != field):
                #     # Note: when the given `uri` specifies a field, the given `record` must contain exactly the field specified.
                #     raise AssertionError(f"The given record '{record}' must contain exactly the field '{field}' specified in URI")
                getattr(result, key)  # make sure that the field exists
                setattr(result, key, value)
            self.session.commit()
        except Exception as e:
            raise e  # FIXME
        finally:
            record = query.one()
            return {field: getattr(record, field) for field in userdata}


    # def get_field(self, column):
    #     """
    #     Return the field string corresponding to the given sqla column (property object of a sqla result object).
    #     Eg. data.Author().firstname -> 'author.firstname'
    #     """
    #     raise NotImplementedError('Not yet needed')


    def make_filter(self, resource, field, comparator, value):
        """
        Return a sqla filter object, according the given `field`, `comparator` and `value`.
        Used by rest api to apply filters specified as string in url.
        Comparator is a string containing a conventional value, see the code below.
        """
        column = getattr(self.model[resource], field)

        if comparator == 'eq':
            return column == value
        if comparator == 'lt':
            return column < value
        if comparator == 'le':
            return column <= value
        if comparator == 'gt':
            return column > value
        if comparator == 'ge':
            return column >= value
        elif comparator == 'like':
            return getattr(column, 'like')(value)
        elif comparator == 'in':
            return getattr(column, 'in_')(value.split(',') if value else [])
        else:
            raise KeyError(f'Comparator not supported: {comparator}')