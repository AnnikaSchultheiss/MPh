﻿"""Manages the local Comsol session."""
__license__ = 'MIT'


########################################
# Components                           #
########################################
from .client import Client             # client class
from .server import Server             # server class


########################################
# Dependencies                         #
########################################
import jpype                           # Java bridge
import atexit                          # exit handler
import sys                             # system specifics
import threading                       # multi-threading
from logging import getLogger          # event logging


########################################
# Globals                              #
########################################
client = None                          # client instance
server = None                          # server instance
logger = getLogger(__package__)        # event logger


########################################
# Start                                #
########################################

def start(cores=None, version=None):
    """
    Starts a local Comsol session.

    This convenience function starts a local Comsol server, creates a
    client instance, connects it to that server, and returns the client
    instance. This covers the common use case of starting a local Comsol
    session in client–server mode.

    Example:
    ```python
        import mph
        client = mph.start(cores=1)
        model = client.load('model.mph')
        model.solve()
        model.save()
        client.remove(model)
    ```

    With regard to cross-platform support, using client–server server
    mode is preferable to the alternative of creating a stand-alone
    client (and thus no separate server).

    Due to limitations of the Java bridge, provided by the JPype
    library, only one client can be instantiated at a time. This is
    because JPype cannot manage more than one Java virtual machine
    within the same Python session. So `start()` can only be called
    once. Subsequent calls will raise `NotImplementedError`. Separate
    Python processes would have to be started, or spawned, to work
    around this limitation.

    The number of `cores` (threads) the server instance uses can
    be restricted by specifying a number. Otherwise all available
    cores will be used.

    A specific Comsol `version` can be selected if several are
    installed, for example `version='5.3a'`. Otherwise the latest
    version is used, and reported via the `.version` attribute.
    """
    global client, server
    if client or server:
        error = 'Only one Comsol session can be started in the same process.'
        logger.critical(error)
        raise NotImplementedError(error)
    logger.info('Starting local client-server session.')
    server = Server(cores=cores, version=version)
    client = Client(cores=cores, version=version, port=server.port)
    return client


########################################
# Stop                                 #
########################################

def exit_hook(code=None):
    """Monkey-patches `sys.exit()` to preserve exit code at shutdown."""
    global exit_code
    if isinstance(code, int):
        exit_code = code
    exit_function(code)


def exception_hook_sys(exc_type, exc_value, exc_traceback):
    """Sets exit code to 1 if exception raised in main thread."""
    global exit_code
    exit_code = 1
    exception_handler_sys(exc_type, exc_value, exc_traceback)


def exception_hook_threads(info):
    """Sets exit code to 1 if exception raised in any other thread."""
    global exit_code
    exit_code = 1
    exception_handler_threads(info)


exit_code = 0
exit_function = sys.exit
sys.exit = exit_hook

exception_handler_sys = sys.excepthook
sys.excepthook = exception_hook_sys

# Only available as of Python 3.8, see bugs.python.org/issue1230540.
if hasattr(threading, 'excepthook'):
    exception_handler_threads = threading.excepthook
    threading.excepthook = exception_hook_threads


@atexit.register
def cleanup():
    """
    Cleans up resources at the end of the Python session.

    This function is not part of the public API. It runs automatically
    at the end of the Python session and is not intended to be called
    directly from application code.

    Stops the local server instance possibly created by `start()` and
    shuts down the Java Virtual Machine hosting the client instance.
    """
    if client:
        try:
            client.disconnect()
        except Exception:
            error = 'Error while disconnecting client at session clean-up.'
            logger.error(error, exc_info=True)
    if server and server.running():
        server.stop()
    if jpype.isJVMStarted():
        logger.info('Exiting the Java virtual machine.')
        sys.stdout.flush()
        sys.stderr.flush()
        jpype.java.lang.Runtime.getRuntime().exit(exit_code)
        # No code is reached from here on due to the hard exit of the JVM.
        logger.info('Java virtual machine has exited.')