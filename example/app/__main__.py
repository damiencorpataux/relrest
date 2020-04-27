from app import app

app.run(
    host='0.0.0.0',
    debug=True)


# Alternatively, use gevent:
#
# from gevent.pywsgi import WSGIServer
# from gevent import monkey
# monkey.patch_all() # need to patch sockets to make requests async, you may also need to call this before importing other packages that setup ssl

# from app import app
# http = WSGIServer(('', 5000), app.wsgi_app)
# http.serve_forever()