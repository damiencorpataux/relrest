"""
Rest Joint.

URI encoder and decoder.

This is a central part of the framework because it defines
the interface between the format and content of a URI and the generated SQL.

URI specification:

    - URI format is: [/]<resource>[/id[/fields]]?[filter]&filter&...&joinpath&joinpath&...]
      where path and query follow the rules:

        - path
            - Leading slash is optional
            - `<resource>` is mandatory
            - `/fields` is optional when `/id` is specified
            - `filter` can be specified in URI multiple times
            - `joinpath` can be specified in URI multiple times
            -  Note: specifying the same `filter` or `joinpath` multiple time is not supported:
            only the last declaration is taken into account (see `encode()`)

        - query
            - `filter` format is: resource[.field[.comparator]]
            - `joinpath` format is: resource[.field[.comparator]]

TODO: provide with the equivalent in language javascript for easy URI generation and manipulation from the browser side.

"""

import urllib

def encode(resource, id=None, fields=[], joinpaths={}, filters={}, limit=None):
    """
    Return an uri from the given `resource_id_field` and `query` object.

    Note: the returned uri string is not url escaped.
    """
    # FIXME: what to do when no `id` is given ? for now it crashes

    if isinstance(resource, dict):
        raise ValueError(f"Argument 'resource' must be a str, not a dict. Did you do mean 'uri.encode(**uri.decode(...))' ?")

    # Build uri `path` component, setting `fields_rf` to be eg: ['field'] or ['resource.field']
    fields_rf = [
        '.'.join(filter(lambda rf_element: rf_element is not None, [f_resource, f_field]))
        for f_resource, f_field in fields]
    fields = ','.join(fields_rf)
    path = '/'.join([resource, id, fields]).rstrip('/')

    # Build uri `query` string component (removing duplicate declarations for the filters and joinpaths)
    filters = set(f"{resource}.{field}.{comparator}={value}" for resource, field, comparator, value in filters)
    joinpaths = set(''.join([f"/{resource}.{field}.{comparator}={value}" for resource, field, comparator, value in joinpath]) for joinpath in joinpaths)
    query = '&'.join([
        *filters,
        *joinpaths,
        *[f"_limit={limit}"]*(limit is not None)])  # do not include limit if None

    return urllib.parse.urlunparse((
        '',  # scheme
        '',  # netloc
        path,
        '',  # params (ie. ;params)
        query,
        ''))

def decode(uri, default_resource=None, default_field='id', default_comparator='eq'):
    """
    Return an object containing the serialized respresentation of the given uri.

    We call this object a 'restjoint-request' and it is a central part of the framework,
    see the docstring of the `restjoint` module.

    Missing components for filter and joinpaths specifications are defaulted to the value of given
    `default_resource`, `default_field` and `default_comparator`. For example:
        uri 'resource' -> 'resource.id.eq' where id and eq are the defaults
        uri 'resource.field' -> 'resource.field.eq' where id and eq are the defaults

    FIXME: `default_resource` makes little sense and is no use. Shall we remove it for clarity ?

    FIXME: shall the reserved_fields and reserved_ids here ?

        it would detect that resource=='+' and return instead of resource = '+':
            resource = list of first resource of each joinpath

        it would detect that resource=='-' and return instead of resource = '-':
            resource = unique list of all resources describes in all joinpaths
            (actually, it's reverse: + returns more resources than -, but for now + is implemented to return less...)
    """
    parsed_uri = urllib.parse.urlparse(uri)

    limit = None

    # Extract resource, id and fields from uri path; path is formatted as [resource[/id[/fields]]]
    path = parsed_uri.path.strip('/').split('/')
    path = [*path, *[''] * (3-len(path))]  # pad splitted path to ensure a list of length 3
    try:
        RESOURCE, ID, FIELDS_CSV = path  # all caps variables mean: pristine from the given `uri`
        QUERY = {}
        for arg, value in urllib.parse.parse_qsl(parsed_uri.query, keep_blank_values=True):
            if arg.startswith('/'):
                # a joinpath can contain sign equal (=) so we join the value into the arg
                arg = '='.join((arg, value))
                value = ''
            QUERY[arg] = value

    except ValueError:
        raise ValueError(
            f"URI '{uri}' contains too many components."
            f"URI path must contain at most 3 components, eg. /resource/id/fields")

    # Extract fields
    fields = []
    for rf in filter(len, FIELDS_CSV.split(',')):
        fields.append(field__resource_field(rf, default_resource))

    # Extract filters and joinpaths from uri query string
    joinpaths = []
    filters = []
    for arg, value in QUERY.items():

        if arg.startswith('/'):
            # query `arg`: is a joinpath: a rfc description formatted as: [/[[resource.]field[.comparator]][=value]]*]
            # to be decoded into a list of tuples.
            joinpath_nodes = []
            joinpath = arg.strip('/').split('/')  # arg eg: '/tag=1/event.id=2'

            for joinpath_node in joinpath:
                # a node of the joinpath is formatted as: [resource[.field[.comparator]]][=value]]
                rfc, joinpath_node_value = [*joinpath_node.split('='), *['']][:2]  # pad splitted list with value '' to length 2
                joinpath_node_rfc = joinpath_node__resource_field_comparator(
                    rfc, default_resource, default_field, default_comparator)  # a tuple, eg. ('resource', 'field', 'comparator')
                joinpath_node = (*joinpath_node_rfc, joinpath_node_value)  # a tuple, eg. ('resource', 'field', 'comparator', 'value')

                joinpath_nodes.append(joinpath_node)

            joinpaths.append(joinpath_nodes)  # a list of tuples

        elif arg == '_limit':
            # query `arg`: is a limit, `value` is a scalar
            limit = value

        else:
            # query `arg`: is a filter: a rfc description formatted as: [[resource.]field[.comparator]][=value]]
            filter_rfc = filter__resource_field_comparator(arg, default_resource, default_field, default_comparator)
            filters.append((*filter_rfc, value))  # a tuple, eg. ('resource', 'field', 'value')

    return {
        'resource': RESOURCE,
        'id': ID,
        'fields': fields,
        'joinpaths': joinpaths,
        'filters': filters,
        'limit': limit}


def field__resource_field(rf_description, default_resource):
    """
    Return a tuple of (resource, field) for the given field `description`,

    A field description is formatted as: [[resource.]field]

    Examples: 'resource' or 'resource.field':
        'field' -> (default_resource, field)
        'resource.field' -> (resource, field)
    """
    if not rf_description:
        raise('Field description cannot parsed when be empty: it makes no sense')

    rf = rf_description.split('.')
    resource = field = None
    try:
        resource, field = rf
    except ValueError:
        if len(rf) > 2:
            raise ValueError(f"Field '{field}' must contain at most 2 components, eg: resource.field")
        try:
            field = rf.pop()
        except IndexError:
            raise ValueError(f"Field '{field}' must contain at least 1 components, eg: resource.field.comparator")

    resource, field = [resource or default_resource, field]

    return resource, field

def joinpath_node__resource_field_comparator(rfc_description, default_resource, default_field, default_comparator):
    """
    Return a tuple of (resource, field, comparator) for the given joinpath `description`.

    A joinpath node description is formatted as: [resource[.field[.comparator]]][=value]]

    Examples: 'resource' or 'resource.field' or 'resource.field.comparator'.
        'resource' -> (resource, default_field, default_comparator)
        'resource.field' -> (resource, field, default_comparator)
        'resource.field.comparator' -> (resource, field, comparator)
    """
    rfc = resource_field_comparator = rfc_description.split('.')
    try:
        rfc = [*rfc, *[''] * (3-len(rfc))]  # pad to ensure a list of length 3
    except ValueError:
        raise ValueError(f"Filter '{description}' must contain at most 3 components, eg: resource.field.comparator")

    resource, field, comparator = rfc
    resource, field, comparator = [
        resource or default_resource,
        field or default_field,
        comparator or default_comparator]

    return (resource, field, comparator)

def filter__resource_field_comparator(rfc_description, default_resource, default_field, default_comparator):
    """
    Return a tuple of (resource, field, comparator) for the given filter `description`,

    A filter description is formatted as: [[resource.]field[.comparator]][=value]]

    Examples: 'resource' or 'resource.field' or 'resource.field.comparator'.
        'field' -> (default_resource, field, default_comparator)
        'field.comparator' -> (default_resource, field, default)
        'resource.field.comparator' -> (resource, field, default)
    """
    rfc = resource_field_comparator = rfc_description.split('.')

    resource = field = comparator = None
    try:
        resource, field, comparator = rfc
    except ValueError:
        try:
            if len(rfc) > 3:
                raise ValueError(f"Filter '{description}' must at most 3 components, eg: resource.field.comparator")
            field, comparator = rfc
        except ValueError:
            try:
                field = rfc.pop()
            except IndexError:
                raise ValueError(f"Filter '{description}' must contain at least 1 component, eg: field")

    resource, field, comparator = [
        resource or default_resource,
        field or default_field,
        comparator or default_comparator]

    return (resource, field, comparator)