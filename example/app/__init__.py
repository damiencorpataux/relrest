"""
Rest Joint web service example.
"""

# TODO: role based access management: https://flask-user.readthedocs.io/en/latest/authorization.html

import data

import flask
from flask_sqlalchemy import SQLAlchemy
try:
    raise ModuleNotFoundError()#import restjoint
except ModuleNotFoundError:
    # FIXME
    import sys; from os import path
    sys.path.append(path.join(path.dirname(__file__), "../.."))
    import restjoint

app = flask.Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = data.engine.url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

db = SQLAlchemy(app)
models = restjoint.util.models_from(data)
rest_service = restjoint.Service(db.session, models)

@app.route("/")
def index():
    """
    Root page.
    """
    import urllib
    return flask.render_template("index.html",
        resource_index=resource_index(),
        service_info=service_info(),
        examples=examples(),
        rest_service=rest_service,
        unquote=urllib.parse.unquote)

@app.route("/resource/<path:uri>", methods=["PUT", "GET", "PATCH", "DELETE", "HEAD"])
def resource(uri):
    """
    Rest interface for CRUD operations.
    """
    uri = uri + "?" + flask.request.query_string.decode()  # join url and query string

    method = flask.request.method
    handler = {
           "PUT": lambda: rest_service.create(uri, flask.request.json),
           "GET": lambda: rest_service.read(uri),
          "HEAD": lambda: rest_service.read(uri),  # eg. curl -I issues a HEAD request
         "PATCH": lambda: rest_service.update(uri, flask.request.json),
        "DELETE": lambda: rest_service.delete(uri, id)}

    result = handler[method]()

    # if "_debug" in flask.request.args:
    #     result = dict(result=result, debug=dict(
    #         uri=uri,
    #         decoded=restjoint.util.uri.decode(uri)))

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
    return {resource: flask.url_for("resource", uri=resource) for resource in rest_service.model.keys()}

@app.route("/decode/<path:uri>")
def decode(uri):
    """
    For development, debug and educational purpose.
    Decode and re-encode the given `uri` and
    return the raw value `as_received`, the `decoded` object and the re-`encoded` uri string.
    """
    # TODO: add the generated sql (prepare statement) !
    uri = uri + "?" + flask.request.query_string.decode()  # Note: marshalling here (returns an equivalent but not always identical uri)
    decoded = restjoint.util.uri.decode(uri)
    encoded = restjoint.util.uri.encode(**decoded)
    return dict(
        uri=dict(
            as_received=uri,
            decoded=decoded,
            encoded=encoded))

@app.route("/service-info")
def service_info():
    """
    Return information about `restjoint.Service`.
    """
    engine = rest_service.session.get_bind()
    return {
        "restjoint.version": "#todo",

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

        - uri: a list of URI examples formatted for jointrest
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