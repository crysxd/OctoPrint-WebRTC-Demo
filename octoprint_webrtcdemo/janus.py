import os
import logging
import subprocess
import time

from threading import Thread
import backoff
import json
import socket
from octoprint.util import to_unicode

from .turn import _turnRegistryApi, _turnRegistryApiKey

try:
    import queue
except ImportError:
    import Queue as queue

from .utils import ExpoBackoff, get_tags, pi_version

_logger = logging.getLogger('octoprint.plugins.webrtcdemo')

JANUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'janus')
JANUS_SERVER = os.getenv('JANUS_SERVER', '127.0.0.1')
JANUS_WS_PORT = 8188
JANUS_DATA_PORT = 8009  # check streaming plugin config
MAX_PAYLOAD_SIZE = 1500  # hardcoded in streaming plugin


class JanusConn:

    def __init__(self, plugin):
        self.plugin = plugin
        self.janus_ws_backoff = ExpoBackoff(120, max_attempts=20)
        self.janus_ws = None
        self.janus_proc = None
        self.shutting_down = False

    def start(self):
        _logger.debug('Starting Janus')
        if os.getenv('JANUS_SERVER', '').strip() != '':
            _logger.warning('Using an external Janus gateway. Not starting the built-in Janus gateway.')
            return

        if not pi_version():
            _logger.warning('No external Janus gateway. Not on a Pi. Skipping Janus connection.')
            return

        def ensure_janus_config():
            janus_conf_tmp = os.path.join(JANUS_DIR, 'etc/janus/janus.jcfg.template')
            janus_conf_path = os.path.join(JANUS_DIR, 'etc/janus/janus.jcfg')
            with open(janus_conf_tmp, "rt") as fin:
                with open(janus_conf_path, "wt") as fout:
                    for line in fin:
                        line = line.replace('{JANUS_HOME}', JANUS_DIR)
                        line = line.replace('{TURN_API}', _turnRegistryApi)
                        line = line.replace('{TURN_API_KEY}', _turnRegistryApiKey)
                        fout.write(line)

            streaming_conf_tmp = os.path.join(JANUS_DIR, 'etc/janus/janus.plugin.streaming.jcfg.template')
            streaming_conf_path = os.path.join(JANUS_DIR, 'etc/janus/janus.plugin.streaming.jcfg')
            with open(streaming_conf_tmp, "rt") as fin:
                with open(streaming_conf_path, "wt") as fout:
                    for line in fin:
                        line = line.replace('{VIDEO_ENABLED}', 'true')
                        fout.write(line)

        def run_janus():
            janus_backoff = ExpoBackoff(60, max_attempts=20)
            janus_cmd = os.path.join(JANUS_DIR, 'run_janus.sh')
            _logger.debug('Popen: {}'.format(janus_cmd))
            self.janus_proc = subprocess.Popen(janus_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            while not self.shutting_down:
                line = to_unicode(self.janus_proc.stdout.readline(), errors='replace')
                if line:
                    _logger.debug('JANUS: ' + line.rstrip())
                elif not self.shutting_down:
                    self.janus_proc.wait()
                    msg = 'Janus quit! This should not happen. Exit code: {}'.format(self.janus_proc.returncode)
                    self.plugin.sentry.captureMessage(msg, tags=get_tags())
                    janus_backoff.more(Exception(msg))
                    self.janus_proc = subprocess.Popen(janus_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        ensure_janus_config()
        janus_proc_thread = Thread(target=run_janus)
        janus_proc_thread.daemon = True
        janus_proc_thread.start()

        self.wait_for_janus()

    def pass_to_janus(self, msg):
        if self.janus_ws and self.janus_ws.connected():
            self.janus_ws.send(msg)

    @backoff.on_exception(backoff.expo, Exception, max_tries=10)
    def wait_for_janus(self):
        time.sleep(1)
        socket.socket().connect((JANUS_SERVER, JANUS_WS_PORT))

    def shutdown(self):
        self.shutting_down = True

        if self.janus_ws is not None:
            self.janus_ws.close()

        self.janus_ws = None

        if self.janus_proc:
            try:
                self.janus_proc.terminate()
            except Exception:
                pass

        self.janus_proc = None

    def process_janus_msg(self, raw_msg):
        try:
            msg = json.loads(raw_msg)

            # when plugindata.data.thespaghettidetective is set, this is a incoming message from webrtc data channel
            # https://github.com/TheSpaghettiDetective/janus-gateway/commit/e0bcc6b40f145ce72e487204354486b2977393ea
            to_plugin = msg.get(
                'plugindata', {}
            ).get(
                'data', {}
            ).get(
                'thespaghettidetective', {}
            )

            if to_plugin:
                _logger.debug('Processing WebRTC data channel msg from client:')
                _logger.debug(msg)
                self.plugin.client_conn.on_message_to_plugin(to_plugin)
                return

            _logger.debug('Relaying Janus msg')
            _logger.debug(msg)
            self.plugin.send_ws_msg_to_server(dict(janus=raw_msg))
        except:
            self.plugin.sentry.captureException(tags=get_tags())