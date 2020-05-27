"""
RelRest.

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
    - relrest-request: is an object that is decoded from a given uri; this object represents
          a relrest rest request on a resource (`see util.uri.decode()`)
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
# eg: /author/+/name or /author/-/name?/writing=123
#
# Value '-' returns a single record,
# value '+' returns a list of records.
reserved_ids = ["+", "-"]

# Note: in uri, resource '+' allow to not specify joins without having to specify a resource,
# eg: /author/+/name or /+?/author/writing=12
#
# Value '+' returns the records for all the resources specified in joinpaths.
# Value '-' returns the records for resources specified in first node of each joinpath.
reserved_resources = ["+", "-"]

class Service(object):

    # FIXME: make those defaults non-static
    default_field = "id"  # default field for filters and joinpath decoder
    default_comparator = "eq"  # default comparator for filters and joinpath decoder
    default_order = {}  # by-resource default order, eg: {
                        # "event": [("event", "time", "asc"), ("event", "summary", "asc")],
                        # "type": [("type", "name", "asc")],
                        # "tag": [("tag", "name", "asc")]}
    default_direction = 'asc'  # default direction

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

    def __init__(self, sqla_session, sqla_model_dict, roles={}):
        """
        Create a rest service instance providing crud operations
        for the given sqla `models` and `session`.

        Argument `models` is an object whose properties contain the models to expose as rest resource.
        Argument `session` is a sqla session object.
        Argument `roles` is a dict describing the per-role operations that are authorized on resources.
        Not that the role `None` is the default role that anybody is granted:
            {"admin": {"*": ["create", "read", "update", "delete"]},
             "user": {"event": ["create", "read", "update", "delete"],
                      "tag": ["create", "read", "update", "delete"],
                      "type": ["read"]},
             "*": {"event": ["read"]}}
        """
        super().__init__()

        for key, not_model in filter(lambda model: not util.is_model(model), sqla_model_dict.values()):
            raise ValueError(f"Argument sqla_model_dict contains a key '{key}'={model} which is not a sqla model")

        self.session = sqla_session

        self._model = sqla_model_dict
        self._resource = {v: k for k, v in self._model.items()}

        self.rights = defaultdict(lambda: defaultdict(set))
        self.add_roles(**roles)

    def add_roles(self, **roles_descriptions):
        """
        Add the given `roles` description to `self.rights`.
        Argument `roles` is eg: {
            "role-1": {
                "*": ["*"],
                "resource": ["-delete"]},
            "role-2": {
                "*": ["*", "-delete"],
                "resource": ["-*", "read"]}}
        Wildcard (*) for resources
        """
        roles_expanded = []
        for role, role_description in roles_descriptions.items():
            for resource, operations in role_description.items():

                if resource == "*":
                    resources_expanded = self.model.keys()
                else:
                    resources_expanded = [resource]

                for resource_expanded in resources_expanded:

                    for operation in operations:

                        if operation == "*":
                            operations_expanded = ["c", "r", "u", "d"]
                        elif operation == "-*":
                            operations_expanded = ["-c", "-r", "-u", "-d"]
                        else:
                            operations_expanded = [operation]

                        for operation_expanded in operations_expanded:

                            discard = operation_expanded[0] == "-"
                            op = (operation_expanded[1] if discard else operation_expanded[0]).lower()
                            if op not in "crud":
                                raise ValueError(f"Invalid operation '{operation}' (on resource '{resource}' for role '{role}')")

                            roles_expanded.append((role, resource_expanded, op, discard))

        for role, resource, op, discard in roles_expanded:
            # add roles after validation of everything
            if discard:
                self.rights[role][resource].discard(op)
            else:
                self.rights[role][resource].add(op)

        for role, role_rights in self.rights.items():
            print(f"Computed rights for role {role}:", dict(role_rights))

    def authorize(self, operation, request, for_roles):
        """
        Raise AssertionError if the given `operation` on `resource`
        is not allowed for the given `roles`, eg:
            authorize("create", "event", ["user"])

        TODO: allow `roles` to specify resource and optional field, eg:
              {"user": {"credentials": ["read"],
                        "credentials.password": []},
                        "post.id": ["read"]}
        makes user allowed to read resource 'credentials' except field 'password',
        and to read only the field 'id' of resource 'post'.
        """
        if not self.rights:
            return  # empty self.rights means disabled authorization

        operation = operation[0]  # 'c' or 'r' or 'u' or 'd'
        for_roles = ["*", *for_roles]  # role "*" is the default role that anybody is granted
        resources_involved = [request["resource"]] if request["resource"] not in reserved_resources else []
        resources_involved += [resource for joinpath in request['joinpaths'] for resource, _, _, _  in joinpath]
        allowed = any(operation in self.rights[for_role][resource_involved]
            for resource_involved in resources_involved
            for for_role in for_roles)

        if not allowed:
            raise AssertionError(
                f"Roles {for_roles} not allowed to perform operation '{operation}' "
                f"for request {request}' involving resources {resources_involved} ")

    def decode(self, uri):
        """
        Return `util.uri.decode(uri)` with default field and comparator
        from this instance `default_field` and `default_comparator` properties.
        """
        return util.uri.decode(uri,
            default_resource=None,
            default_field=self.default_field,
            default_comparator=self.default_comparator,
            default_direction=self.default_direction)

    def create(self, uri, record, for_roles=[]):
        """
        Add the given `record` to database.
        """
        request = self.decode(uri)

        self.authorize("create", request, for_roles)

        record = self.create_resource(
            resource=request["resource"],
            record=record)

        return self.read_resource(
            resource=request["resource"],
            id=record.id)

    def read(self, uri, for_roles=[]):
        """
        Read and return record(s) for the given `uri`.
        """
        request = self.decode(uri)

        self.authorize("read", request, for_roles)  # FIXME: pass request dict to allow authorize() to check all involved resources

        log.debug(f"Reading 'uri={uri}' decoded into {request}")

        return self.read_resource(
            resource=request["resource"],
            id=request["id"],
            fields=request["fields"],
            filters=request["filters"],
            joinpaths=request["joinpaths"],
            order=request["order"],
            limit=request["limit"])

    def update(self, uri, record, for_roles=[]):
        """
        Update the existing resource `id` with the given `record`.

        The given `record` can contain 0..n fields can be updated
        and fields do not exist in sqla model are ignored.
        """
        request = self.decode(uri)

        self.authorize("update", request, for_roles)

        if request["fields"]:
            # ignore fields description in rest request
            # raise ValueError(f"Update operation does not support fields in URI and field '{fields}' was given")
            pass

        self.update_resource(
            resource=request["resource"],
            id=request["id"],
            record=record)

        return self.read_resource(
            resource=request["resource"],
            id=request["id"],
            fields=request["fields"])

    def delete(self, uri, for_roles=[]):
        request = self.decode(uri)
        self.authorize("delete", request, for_roles)
        self.delete_resource(
            resource=request["resource"],
            id=request["id"])

        return None

    def create_resource(self, resource, record={}):
        """
        Create resource and return created model.
        """
        row = self.model[resource]()
        for field, value in record.items():
            self.set_property(row, field, value)

        self.session.add(row)
        self.session.commit()
        return row

    def read_resource(self, resource, id=None, fields=[], filters=[], joinpaths=[], order=[], limit=None):
        """
        Query database and return a single or multiple record(s) or recordtuple(s).

        Create a sqla query from the given arguments, execute the query, serialize the result
        and return a dict that is json serializable.

        Support wildcard filters on multiple fields using 'and' operator.
        Support joining tables in a chaining manner to filter on foreign fields (a joinpath),
        up to arbitrary degree of relationship.
        Support `resource='+'`, used to return recordtuples of multiple resources according the given `joinpath`. Eg:
            /+/writing.id=1 or /+?/writing/topic
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
                    f"Using resource '+' requires a joins-path specification, eg: /+?/topic/writing")

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
                #   s.query(data.Author).join(data.Author.writing).join(data.Writing.activity).join(data.Activity.topic).filter(data.Topic.id.in_([1]))
                joincolumn = getattr(last_relmodel or surrogate_base_model or base_model, relcolumn)  # use base_model or surrogate_base_model for first iteration
                if resource == '+':
                    # FIXME: allow to describe joinpath to use `query.outerjoin`
                    #   to include empty relationships in combinatory result, eg:
                    #   /author=25/+writing/+activity & /activity/+activity_type & /activity/topic
                    #   -> need to: update util.uri.decode() to parse the +
                    #               and return joinpaths=[(type, resource, field, comparator, value)]
                    #
                    # For now, resourceless requests trigger outerjoin
                    query = query.outerjoin(joincolumn)
                else:
                    query = query.join(joincolumn)

                last_relmodel = self.model[relresource] # last_relmodel is used in next iteration to create the "joins chain"

        # Apply limit to sqla query
        query = query.limit(limit)

        # Handle field ':count'
        if ":count" in [field for f_resource, field in fields]:
            # Note: field :count is a virtual field that triggers the
            # return of dict(count = the number of records matched by the given uri query).
            return {":count": query.count()}

        # Apply order to sqla query
        order = order + self.default_order.get(resource, [])
        for o_resource, o_field, o_direction in order:

            if o_resource:
                o_model = self.model[o_resource]
            else:
                o_model = base_model

            query = query.order_by(getattr(getattr(o_model, o_field), o_direction)())
            # FIXME: handle lowercase ordering:
            # column = getattr(model, o_field)
            # modifier = sqlalchemy.func.lower
            # direction = getattr(sqlalchemy.func, o_direction)
            # query = query.order_by(direction(column))

        # Process and apply fields to sqla query
        if resource in ["+", "-"]:
            # allow to specify fields in resourceless query which returns a sqla tuple
            # containing only the described fields.
            # Note that relationships are never loaded for resourceless requests
            entities = []
            if not fields:
                # if no field is given, all the fields of the computed `models` are included.
                entities = [
                    getattr(m, attr.key).label(f"{self.resource[m]}.{attr.key}")
                    for m in models for attr in m._sa_class_manager.attributes
                    if not util.is_relationship(getattr(m, attr.key))]
            else:
                for f_resource, f_field in fields:
                    if f_resource:
                        f_model = self.model[f_resource]
                        if not util.is_relationship(getattr(f_model, f_field)):
                            entities.append(getattr(f_model, f_field).label(f"{f_resource}.{f_field}"))
                    else:
                        # If a field does not describe a resource, the given field is loaded for all the computed `models`.
                        f_models = [
                            m for m in models
                            if hasattr(m, f_field)
                            and not util.is_relationship(getattr(m, f_field))]

                        for f_model in f_models:
                            entities.append(getattr(f_model, f_field).label(f"{self.resource[f_model]}.{f_field}"))

            query = query.with_entities(*[entity for entity in entities])

        else:
            for f_resource, f_field in fields:

                if f_resource:
                    f_model = self.model[f_resource]
                elif base_model:
                    f_model = base_model

                # apply field selection to sqla query select statement,
                # see https://docs.sqlalchemy.org/en/latest/orm/loading_columns.html
                try:
                    # field is a property
                    query = query.options(sqlalchemy.orm.Load(f_model).load_only(f_field))

                except sqlalchemy.orm.exc.LoaderStrategyException:
                    # field is a relationship
                    column = getattr(f_model, f_field)
                    query = query.options(sqlalchemy.orm.joinedload(column).load_only("id"))  # hardcode to foreign field "id"
                    query = query.options(sqlalchemy.orm.Load(f_model).load_only("id"))  # to ensure limiting local fields, we set option load_only on local primary key (which is always loaded in anyway)

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
        Update database accoring the given `resource`, `id` and `record`.
        """
        if not id or id in reserved_ids:
            # TODO: update using filters and reserved_ids features is not yet implemented
            raise ValueError(f"Missing id in URI, or invalid id format: '{id}'")

        query = self.session.query(self.model[resource])
        if id: query = query.filter_by(id=id)
        row = query.one()
        for field, value in record.items():
            self.set_property(row, field, value)

        self.session.commit()

    def delete_resource(self, resource, id):
        """
        Delete from database accoring the given `resource` and `id`.
        """
        if not id or id in reserved_ids:
            # TODO: update using filters and reserved_ids features is not yet implemented
            raise ValueError(f"Missing id in URI, or invalid id format: '{id}'")

        query = self.session.query(self.model[resource])
        query = query.filter_by(id=id)
        self.session.delete(query.one())
        self.session.commit()

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

        # Handle column type: marshal value accordingly
        cast = {
            sqlalchemy.sql.sqltypes.Integer: lambda value: int(value),
            sqlalchemy.sql.sqltypes.Boolean: lambda value: True if not value.isnumeric() else bool(int(value))}

        value = cast.get(type(column.type), lambda value: value)(value)

        # Handle comparator
        if comparator == 'eq':
            return column == value
        if comparator == 'ne':
            return column != value
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
            return getattr(column, 'in_')(str(value).split(',') if value else [])
        elif comparator == 'notin':
            return getattr(column, 'notin_')(str(value).split(',') if value else [])
        else:
            raise KeyError(f'Comparator not supported: {comparator}')


    def set_property(self, model_instance, property_name, value):
        """
        Set the given `value` on the `property` of the given `model`, handling
        ..n and ..1 relationships by setting models instance(s) accordingly.
        """
        column = getattr(model_instance.__class__, property_name)

        if type(column.impl) == sqlalchemy.orm.attributes.ScalarAttributeImpl:
            # column is a scalar
            try:
                setattr(model_instance, property_name, value)
            except Exception as e:
                raise ValueError(
                    f"Cannot set property {property_name}={value} to model '{model_instance.__class__.__name__}': "
                    f"{e.__class__.__name__}: {e}")

        elif util.is_relationship(column):
            relation = self.model[property_name]
            relation_id = getattr(relation, "id")

            if isinstance(column.impl, sqlalchemy.orm.attributes.ScalarObjectAttributeImpl):
                # column is a 1.. relationship
                relation = self.session.query(relation).filter(relation_id == value)
                setattr(model_instance, property_name, relation.one() if value else None)

            elif isinstance(column.impl, sqlalchemy.orm.attributes.CollectionAttributeImpl):
                # column is a n.. relationship
                relations = self.session.query(relation).filter(relation_id.in_(value))
                setattr(model_instance, property_name, relations.all())
                # TODO: allow to add and remove relations one by one, eg:
                # relation: ["+1", "-2"]        <-- add relation id 1, remove relation id 2
                # relation: ["+1", "-2", 3, 4]  <-- resets all relations to ids [3, 4] and do same as above
                # use column.add() and column.remove()
            else:
                raise NotImplementedError("Column relationship impl not supported: {column.impl}")

        else:
            raise NotImplementedError("Column impl not supported: {column.impl}")
