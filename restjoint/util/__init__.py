"""
Rest Joint.

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

def serialize_result(service_resource_map, result_or_resulttuple):
    """
    Serialize the given `result_or_resulttuple` according the given `service_resource_map`
    and return an object that is json serializable.

    Argument `service_resource_map` is a `restjoint.Service.resource`.
    It is used for naming the resource key of the returned object
    when `result_or_resulttuple` is a list of tuples.

    Argument `result_or_resulttuple` can be a plain list of results and a list of tuples of results,
    eg: [result_topic] and [(result_topic, result_writing), (result_topic, result_writing)].

    If the given `result_or_resulttuple` is a list of results, the returned json contains
    eg: [result_topic, ...] where 'result_topic' is a dict of the serialized topic result.
    Otherwise, when `result_or_resulttuple` is a list of tuples of results, the returned json contains
    eg: [{'topic': result_topic, 'writing': result_writing}, ...].

    A result tuple is the tuple of sqla resultset for one combinatory result.

    TODO: provide with multiple serializers, at least:
        - combinatory: as implemented below
        - nested: return a result object with nested records according resources hierachy (joinpaths),
                  that can help the end-user with deduplication.
                  Eg, in example/app/templates/resource-grpah.html, we need to deduplicate
                  while creating edges in javascript function `load_edges()`.

    """
    if isinstance(result_or_resulttuple, tuple):
        # Note: `resulttuple` is the combinatory sqla result of all the joins with appiled filters,
        # returned by sqla query execution eg: query.one() or query.all()
        resulttuple = result_or_resulttuple

        return {service_resource_map[result.__class__]: serialize_single_result(result) for result in resulttuple}

    else:
        # Note: `result` is a plain sqla result,
        # returned by sqla query execution eg: query.one() or query.all()
        result = result_or_resulttuple

        return serialize_single_result(result)

def serialize_single_result(result):
    """
    Return a json encodable dict of the given sqla `result`.
    """
    relation_prefix = '/'  # this prefix is added to fields that are a relation

    selected = (lambda field:
        not field in sqlalchemy.orm.attributes.instance_state(result).unloaded)
        # Note: unloaded property is used to discard fields that are not loaded, ie. lazily loaded,
        # such as relationships (by default), and fields not specified in query select clause.
    fields = list(filter(selected, result._sa_instance_state.attrs.keys()))

    object = {}
    for field in fields:

        try:
            value = getattr(result, field)
        except AttributeError:
            continue  # we are permissive

        if isinstance(type(value), sqlalchemy.ext.declarative.api.DeclarativeMeta):
            # Note: value is a list of sqla row
            object[relation_prefix + field] = value.id

        elif isinstance(value, sqlalchemy.orm.collections.InstrumentedList):
            # Note: value is a list of sqla rows
            # FIXME: this generates a query on all columns of the foreign table,
            # but only id is needed. See the sql queries echoed by sqlalchemy, eg:
            # SELECT activity.published AS activity_published, activity.id AS activity_id, activity.name AS activity_name, activity.teaser AS activity_teaser
            # FROM activity, nn_activity_topic
            # WHERE ? = nn_activity_topic.topic_id AND activity.id = nn_activity_topic.activity_id
            object[relation_prefix + field] = list(map(lambda result: result.id, value))

        else:
            # Note: value is a scalar
            object[field] = value

    return object
