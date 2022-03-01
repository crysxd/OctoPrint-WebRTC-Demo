import string
import asyncio
import threading
from flask import Flask, Response, json, request, abort
import logging
import uuid

_logger = logging.getLogger('octoprint.plugins.webrtcdemo')
_port = 15370
_host = "127.0.0.1"
_turnServer = None
_app = Flask(__name__)
_turnRegistryApiKey = str(uuid.uuid4())
_turnRegistryApi = "http://{0}:{1}/turn".format(_host, _port)


def startTurnReigistry():
    _logger.info("TURN: starting TURN server registry at {0} with API key {1}".format(_turnRegistryApi, _turnRegistryApiKey))
    _app.run(host=_host, port=_port)

def stopTurnRegistry():
    return

@_app.route('/turn', methods=['POST'])
def _registerTurnServer():
    global _turnServer
    _checkApiKey()

    turnServer = request.get_json()
    _logger.debug("TURN: regstering server: {}".format(turnServer))

    if (turnServer.get("username") is None):
        _logger.info("TURN: server missing 'username'")
        return  Response("{\"error\":\"TURN server missing 'username'\"}", status=406, mimetype='application/json')
    if (turnServer.get("password") is None):
        _logger.info("TURN: server missing 'password'")
        return  Response("{\"error\":\"TURN server missing 'password'\"}", status=406, mimetype='application/json')
    if (turnServer.get("ttl") is None):
        _logger.info("TURN: server missing 'ttl'")
        return  Response("{\"error\":\"TURN server missing 'ttl'\"}", status=406, mimetype='application/json')
    if (turnServer.get("uris") is None):
        _logger.info("TURN: server missing 'uris'")
        return  Response("{\"error\":\"TURN server missing 'uris'\"}", status=406, mimetype='application/json')
    if (isinstance(turnServer.get("uris"), list) is False):
        _logger.info("TURN: server 'uris' is not array")
        return  Response("{\"error\":\"TURN server 'uris' is not array\"}", status=406, mimetype='application/json')
    if (len(turnServer.get("uris")) is 0 ):
        _logger.info("TURN: server 'uris' is empty")
        return  Response("{\"error\":\"TURN server 'uris' is empty\"}", status=406, mimetype='application/json')
    
    _logger.info("TURN: server passed all checks".format(turnServer))
    _turnServer = turnServer

    return  Response("{}", status=201, mimetype='application/json')

@_app.route('/turn', methods=['GET'])
def _getTurnServer():
    global _turnServer
    _checkApiKey()

    if _turnServer is None:
        _logger.debug("TURN: no server available")
        return Response("{}", status=404, mimetype='application/json')
    else:
        _logger.debug("TURN: server returned".format(_turnServer))
        return json.dumps(_turnServer)

def _checkApiKey():
    _logger.debug("TURN: Checking API key: {0} <--> {1}".format(request.args.get('key'), _turnRegistryApiKey))
    if str(request.args.get('key')) != _turnRegistryApiKey:
        abort(status=403)
    
