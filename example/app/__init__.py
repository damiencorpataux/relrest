"""
RelRest web service example.
"""

# TODO: role based access management: https://flask-user.readthedocs.io/en/latest/authorization.html

import data

import flask
from flask_sqlalchemy import SQLAlchemy
try:
    import relrest
except ModuleNotFoundError:
    # FIXME: in case relrest is not installed
    import sys; from os import path
    sys.path.append(path.join(path.dirname(__file__), "../.."))
    import relrest

app = flask.Flask(__name__)

app.config["SECRET_KEY"] = "changeme!"
app.config["SQLALCHEMY_DATABASE_URI"] = data.engine.url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

if app.config["DEBUG"]:
    relrest.log.setLevel(relrest.logging.DEBUG) # FIXME: not having any effect

db = SQLAlchemy(app)
models = relrest.util.models_from(data)
rest_service = relrest.Service(db.session, models, roles={
    "*": {
        "event": ["create", "read", "update"]
    },
    "user": {
        "tag": ["*"],
        "type": ["*", "-update", "-delete"]},
    "admin": {
        "*": ["*"]}})

users = {
    # "username": ("password", ["role1", "role2"])
    "admin": ("password", ["admin"]),
    "user": ("password", ["user"])}

@app.before_request
def authenticate_every_request():
    """
    Process basic authentication on every request.
    This allows http-basic-auth at once, eg when running
        curl user:password@localhost/resource/type
    """
    authenticate()

@app.errorhandler(Exception)
def unhandled_exception(e):
    import traceback
    traceback.print_exc()
    status = {
        AssertionError: 403, # forbidden
        ValueError: 400 # bad request
    }.get(type(e), 500)
    return dict(error=f"{e.__class__.__name__}: {e}"), status

@app.route("/")
def index():
    """
    Root page.
    """
    import urllib
    return flask.render_template("index.html",
        service_info=service_info(),
        examples=examples(),
        rest_service=rest_service,
        users=users,
        unquote=urllib.parse.unquote)

@app.route("/authenticate")
def authenticate():
    """
    HTTP Basic authentication example.
    """
    if flask.request.authorization:

        username = flask.request.authorization.username
        password = flask.request.authorization.password

        if not users.get(username) or not users[username][0] == password:
            raise ValueError("Invalid credentials")

        flask.session["username"] = username
        flask.session["roles"] = users[username][1]

    return dict(
        username=flask.session.get("username"),
        roles=flask.session.get("roles", []))

@app.route("/resource/<path:uri>", methods=["PUT", "GET", "PATCH", "DELETE", "HEAD"])
def resource(uri):
    """
    Rest interface for CRUD operations.
    """
    roles = flask.session.get("roles", [])
    method = flask.request.method
    uri = uri + "?" + flask.request.query_string.decode()  # join url and query string
    handler = {
           "PUT": lambda: rest_service.create(uri, flask.request.json, roles),
           "GET": lambda: rest_service.read(uri, roles),
          "HEAD": lambda: rest_service.read(uri, roles),  # eg. curl -I issues a HEAD request
         "PATCH": lambda: rest_service.update(uri, flask.request.json, roles),
        "DELETE": lambda: rest_service.delete(uri, id, roles)}

    result = handler[method]()

    # if "_debug" in flask.request.args:
    #     result = dict(result=result, debug=dict(
    #         uri=uri,
    #         decoded=relrest.util.uri.decode(uri)))

    return flask.jsonify(result)


# Some meta information about the resources and the service

@app.route("/resource-graph")
def resource_graph():
    return flask.render_template("resource-graph.html")

@app.route("/resource/")  # for convenience
@app.route("/resource-index")
def resource_index():
    """
    Return the resource index with resources name and uri.
    """
    from sqlalchemy.inspection import inspect
    resources = {}
    for resource in rest_service.model.keys():
        inspected = inspect(rest_service.model[resource])
        resources[resource] = {
            "fields": inspected.columns.keys(),
            "relations": inspected.relationships.keys()
        }
    return resources

@app.route("/decode/<path:uri>")
def decode(uri):
    """
    For development, debug and educational purpose.
    Decode and re-encode the given `uri` and
    return the raw value `as_received`, the `decoded` object and the re-`encoded` uri string.
    """
    # TODO: add the generated sql (prepare statement) !
    uri = uri + "?" + flask.request.query_string.decode()  # Note: marshalling here (returns an equivalent but not always identical uri)
    decoded = relrest.util.uri.decode(uri)
    encoded = relrest.util.uri.encode(**decoded)
    return dict(
        uri=dict(
            as_received=uri,
            decoded=decoded,
            encoded=encoded))

@app.route("/service-info")
def service_info():
    """
    Return information about `relrest.Service`.
    """
    engine = rest_service.session.get_bind()
    return {
        "relrest.version": "#todo",

        "sqlalchemy.version": "#todo",

        "sqlalchemy.session.engine.url": str(engine.url),
        "sqlalchemy.session.engine.tables": engine.table_names(),
        "sqlalchemy.session.engine.name": str(engine.name),
        "sqlalchemy.session.engine.driver": str(engine.driver),

        "sqlalchemy.session.engine.dialect.dialect_description": str(engine.dialect.dialect_description),
        # "sqlalchemy.session.engine.dialect": str(engine.dialect),
        # "sqlalchemy.session.engine.dialect.dbapi": str(engine.dialect.dbapi),
        # "sqlalchemy.session.engine.dialect.ddl_compiler": str(engine.dialect.ddl_compiler),
        # "sqlalchemy.session.engine.dialect.default_paramstyle": str(engine.dialect.default_paramstyle),
        # "sqlalchemy.session.engine.dialect.description_encoding": str(engine.dialect.description_encoding)
        }


@app.route("/examples")
def examples():
    """
    Return a list of examples:

        - uri: a list of URI examples formatted for RelRest
    """
    # TODO: this example dataset could be stored in database, for une mise en abime sympa
    import urllib  # unquote urls for readability
    examples = {
            "Base queries": [
                ("Get all tags",
                    "tag"),
                ("Get tag 1",
                    "tag/1"),
            ],

            "Filters": [
                ("Get tag 1",
                    "tag?id=1"),
                ("Get tag 1",
                    "tag?id.eq=1"),
                ("Get tag 1",
                    "tag?tag.id.eq=1"),
                ("Get tags starting with 'a'",
                    "tag?name.like=a%"),
                ("Get tags starting with 'a' and id in 1,2,3",
                    "tag?name.like=a%&id.in=1,2,3"),
                ("Get tags with name starting with 'a' and id greater than 10",
                    "tag?name.like=a%&id.gt=10"),
            ],

            "Limit and count (offset is todo)": [
                ("Get tag with limit 10",
                    "tag?_limit=10"),
                ("Count tags (id=+ means any id)",
                    "tag/+/:count"),
                ("Count tags with name starting with 'a'",
                    "tag/+/:count?name.like=a%"),
            ],

            "Resource-less (or relational) requests using join-paths": [
                ("Get all resource (not allowed: a join-path is required)",
                    "+"),
                ("Get all tags",
                    "+?/tag"),
                ("Get tag 1",
                    "+?/tag=1"),
                ("Get tag 1",
                    "+?/tag.id=1"),
                ("Get tag 1",
                    "+?/tag.id.eq=1"),
                ("Get tags with id greater than 50",
                    "+?/tag.id.gt=50"),
                ("Get tags starting with 'a'",
                    "+?/tag.name.like=a%"),
                ("Get combinations of tags starting with 'a' and events having a summary starting with 'l'",
                    "+?/tag.name.like=A%&/event.summary.like=l%"),
                ("Get tags starting with 'a' that have an event summary starting with 'l'",
                    "+?/tag.name.like=A%/event.summary.like=l%"),
                ("Get tags starting with 'a' that have an event summary starting with 'l', returning the first resource of each join path (here: tag)",
                    "-?/tag.name.like=A%/event.summary.like=l%"),
            ],

            "Join-paths: Combinaisons (without joins, as a starter)": [
                ("Count the tag resource: traditional way = 100",
                    "tag/+/:count"),
                ("Count the tag resource: combinatory way = 100",
                    "+/+/:count?/tag"),
                ("Count the event resource = 1000",
                    "+/+/:count?/event"),
                ("Count the combinations of tag with event resources = 100000",
                    "+/+/:count?/tag&/event"),
                ("Count the combinations of tag resource 1 with all event resources = 1000",
                    "+/+/:count?/tag=1&/event"),
                ("Count the combinations of event resource 1 with all tag resources = 100",
                    "+/+/:count?/tag&/event=1"),
                ("Count the combinations of event resource 1 with tag resource 1 = 1",
                    "+/+/:count?/tag=1&/event=1"),
                ("Count the combinations of event resource 1,2,3 with all tag resources = 3000",
                    "+/+/:count?/tag.id.in=1,2,3&/event"),
                ("Count the combinations of event resource 1,2,3 with tag resources 1 = 3",
                    "+/+/:count?/tag.id.in=1,2,3&/event=1"),
                ("Count the combinations of event resource 1,2,3 with tag resources 1,2,3 = 9",
                    "+/+/:count?/tag.id.in=1,2,3&/event.id.in=1,2,3"),
                ("Get the data of the combinations of event resource 1,2,3 with tag resources 1,2,3...",
                    "+?/tag.id.in=1,2,3&/event=1"),
            ],

            "Join-paths: Relations (with joins)": [
                ("Count the relations between events and tags",
                    "+/+/:count?/tag/event"),
                ("Count the relations between tags and events (same result as above)",
                    "+/+/:count?/event/tag"),
                ("Count the relations between tags with id >50 and events",
                    "+/+/:count?/tag.id.ge=50/event"),
                ("Count the relations between tags with id >50 events starting with 'a'",
                    "+/+/:count?/tag.id.ge=50/event.summary.like=a%"),
                ("Get relations between tags with an id >50 and events starting with 'a', returning the tag and event records tuples",
                    "+?/tag.id.ge=50/event.summary.like=a%"),
                ("Get relations between tags with an id >50 and events starting with 'a', returning the tag records",
                    "-?/tag.id.ge=50/event.summary.like=a%"),
            ],

            "Fields selection": [
                ("Get the time of event 1 (id is always returned, eagely loaded relationships are always returned for now)",
                    "event/1/time"),
                ("Get the time of all events",
                    "event/+/time"),
                ("Get the summary and time of all events",
                    "event/+/time,summary"),
                ("Get the summary and time of all events and the color of their tags (#fixme)",
                    "+/+/event.time,event.summary,tag.color?/event/tag"),
            ]
    }

    # "resource",

    # "resource/id",

    # "resource/id/field1",

    # "resource/id/field1,field2",

    # "resource/id/field1,field2?"
    # "field1=value1",

    # "resource/id/field1,field2?"
    # "field1=value1"
    # "&field2.id.in=1,2,3",

    # "resource/id/field1,field2?"
    # "field1=value1"
    # "&field2.id.in=1,2,3"
    # "&/resource/relation",

    # "resource/id/field1,field2?"
    # "field1=value1"
    # "&field2.id.in=1,2,3"
    # "&/resource/relation"
    # "&/resource/other_relation.name.like=The%"]]

    return examples
