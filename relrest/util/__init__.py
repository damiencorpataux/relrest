"""
RelRest.

General utility functions for the framework.

"""

from . import uri

import sqlalchemy

def models_from(module):
    """
    Return a dict of sqla models from the given `module`.
    The given module is iterated to extract its sqla models. Each sqla model is
    mapped to a resource name = modelname.lower().
    """
    return {model.__name__.lower(): model for model in vars(module).values() if is_model(model)}

def is_model(thing):
    """
    Return True if `thing` is a sqla model class.
    """
    return (isinstance(thing, sqlalchemy.ext.declarative.api.DeclarativeMeta)
            and hasattr(thing, '__table__'))  # disard sqlalchemy.ext.declarative.declarative_base()

def is_relationship(column):
    """
    Return True is the given sqla `column` is a relationship.
    """
    return isinstance(column.property, sqlalchemy.orm.relationships.RelationshipProperty)

def serialize_result(service_resource_map, result_or_resulttuple):
    """
    Serialize the given `result_or_resulttuple` according the given `service_resource_map`
    and return an object that is json serializable.

    Argument `service_resource_map` is a `relrest.Service.resource`.
    It is used for naming the resource key of the returned object
    when `result_or_resulttuple` is a sqla collection tuple.

    Argument `result_or_resulttuple` can be a sqla model instance or sqla result collection tuple,
    eg: [result_topic] and [(resource.field, resource.field)].

    TODO: provide with multiple serializers, at least:
        - combinatory: as implemented below
        - nested: return a result object with nested records according resources hierachy (joinpaths),
                  that can help the end-user with deduplication.
                  Eg, in example/app/templates/resource-grpah.html, we need to deduplicate
                  while creating edges in javascript function `load_edges()`.

    """
    if is_model(type(result_or_resulttuple)):
        # Note: `result` is a plain sqla result,
        # returned by sqla query execution eg: query.one() or query.all()
        result = result_or_resulttuple
        return serialize_model(result)

    else:
        # Note: `resulttuple` is the combinatory sqla result of all the joins with appiled filters,
        # returned by sqla query execution eg: query.one() or query.all()
        resulttuple = result_or_resulttuple
        return serialize_tuple(resulttuple)

    return serialized

def serialize_tuple(result):
    """
    Return a json encodable dict of the `sqlalchemy.util._collections.result` given as `result`,
    containing a key per resource containing a dict of key per field containing the field value.
    The collection keys must be formatted as 'resource.field'.
    """
    serialized = {}
    for key, value in result._asdict().items():
        resource, field = key.split('.')
        serialized[resource] = dict(**{field: value}, **serialized.get(resource, {}))

    return serialized

def serialize_model(result):
    """
    Return a json encodable dict of the `sqlalchemy.ext.declarative.api.DeclarativeMeta` given as `result`.
    """
    relation_prefix = '/'  # this prefix is added to fields that are a relation

    # Note: unloaded property is used to discard fields that are not loaded, ie. lazily loaded,
    # such as relationships (by default), and fields not specified in query select clause.
    selected = (lambda field: not field in sqlalchemy.orm.attributes.instance_state(result).unloaded)
    fields = list(filter(selected, result._sa_instance_state.attrs.keys()))

    object = {}
    for field in fields:

        try:
            value = getattr(result, field)
        except AttributeError:
            continue  # we are permissive

        if not is_relationship(getattr(result.__class__, field)):
            object[field] = value

        else:
            if isinstance(value, sqlalchemy.orm.collections.InstrumentedList):
                # ..n relationship: value is a list of sqla models
                object[relation_prefix + field] = list(map(lambda result: result.id, value))

            elif isinstance(type(value), sqlalchemy.ext.declarative.api.DeclarativeMeta):
                # ..1 relationship: value is a sqla model
                object[relation_prefix + field] = value.id

            else:
                # ..1 relationship: value shall be empty
                object[relation_prefix + field] = value

    return object
