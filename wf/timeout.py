import time
import logging
import errno
import os
import signal

log = logging.getLogger(__name__)


class TimeoutError(Exception):
    pass


"""
timeout in seconds. None - wait indefinitely
"""
def with_timeout(func, args=[], kwargs={}, timeout=None, error_message=os.strerror(errno.ETIME)):
    def _handle_timeout(signum, frame):
        raise TimeoutError(error_message)

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(0 if timeout is None else timeout)
    try:
        result = func(*args, **kwargs)
    finally:
        signal.alarm(0)
    return result


"""
timeout in seconds. None - wait indefinitely
"""
def attempt(func, args=[], kwargs={}, timeout=None, retries=3, retry_delay=0):
    while True:
        try:
            return with_timeout(func, args=args, kwargs=kwargs, timeout=timeout)
        except Exception, exc:
	    log.warning("%s (args:%s kwargs:%s) failed with exception: %s" % (func, args, kwargs, exc))
	    time.sleep(retry_delay)
	    log.warning("%d retries remaining" % retries)
	    retries -= 1
            if retries < 0: 
	        log.exception(exc)
	        raise exc
