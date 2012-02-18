import socket
import time
from celery.decorators import task
import logging
from django.conf import settings

from novaclient.v1_1 import client

#log = logging.getLogger(__name__)

@task(default_retry_delay=60, max_retries=3)
def create_instance(name, image, flavor, userdata=None, key_name=None, security_groups=[]):
    log = create_instance.get_logger()
    try:
        log.debug("calling nova_client.servers.create() with: name = %s, image = %d, flavor = %d, userdata = %s, key_name = %s, security_groups = %s)" % (name, image, flavor, userdata, key_name, security_groups))
        return nova_client().servers.create(
            name=name, 
	    image=image, 
	    flavor=flavor, 
	    userdata=userdata, 
	    key_name=key_name, 
	    security_groups=security_groups)
    except Exception, exc:
        log.exception("Error calling Nova: %s" % exc)
        create_instance.retry(exc=exc)

@task(default_retry_delay=60, max_retries=10)
def delete_instance(id):
    log = delete_instance.get_logger()
    try:
        log.debug("calling nova_client.servers.delete() with: server = %d" % id)
        return nova_client().servers.delete(server=id)
    except Exception, exc:
        log.exception("Error calling Nova: %s" % exc)
        delete_instance.retry(exc=exc)

@task(soft_time_limit=10*60, time_limit=60*60)
def wait_for_server(host, port=22, protocol=socket.SOCK_STREAM, retry_delay=1, timeout=-1):
    log = wait_for_server.get_logger()
    s = socket.socket(socket.AF_INET, protocol)
    start = time.time()
    while (timeout < 0 or time.time() < (start + timeout)):
        try:
	    log.debug("trying to connect to %s:%d" % (host, port))
            s.connect((host, port))
	    log.debug("connected!")
            s.shutdown(2)
            return True
        except Exception, exc:
	    log.debug("Unable to connect. Error:\n %s" % exc)
            time.sleep(retry_delay)
    return False # timed out

def nova_client():
    return client.Client(
        getattr(settings, 'NOVA_USER', 'admin'),
        getattr(settings, 'NOVA_PASSWORD', 'admin'),
        getattr(settings, 'NOVA_TENANT', 'admin'),
        getattr(settings, 'NOVA_AUTH_URL', 'http://localhost:5000/v2.0/'),
    )
