import socket
import time
import logging
from django.conf import settings

from novaclient.v1_1 import client

import models

log = logging.getLogger(__name__)

"""
Call nova API to create an VM, then wait until an IP is assigned to that VM
return: interal IP address of the new VM
"""
def create_instance(name, image, flavor, userdata=None, key_name=None, security_groups=[]):
    #log = create_instance.get_logger()
    log.info("calling nova_client.servers.create() with: name = %s, image = %d, flavor = %d, userdata = %s, key_name = %s, security_groups = %s)" % (name, image, flavor, userdata, key_name, security_groups))
    node = nova_client().servers.create(
            name=name, 
	    image=image, 
	    flavor=flavor, 
	    userdata=userdata, 
	    key_name=key_name, 
	    security_groups=security_groups)
	

    log.info("waiting for VM to be assigned an internal IP address")
    while True:
        n = nova_client().servers.get(node.id)
	if n.networks and n.networks.has_key('internal') and len(n.networks['internal']) > 0:
            #assuming VM always has 1 internal IP
	    ip = n.networks['internal'][0]
            instance = models.new_vminstance(node.id, ip, '')
	    instance.save()
	    log.debug("IP address is %s" % ip)
	    return ip
	log.debug("no IP address assigned yet. waiting for 3s")
	time.sleep(3)


def reset_testing_env(img_list):
    for i in models.VMInstance.objects.all():
        if nova_client().servers.get(i.instance_id).image['id'] in [str(x) for x in img_list]:
            nova_client().servers.delete(i.instance_id)
	    i.delete()

def nova_client():
    return client.Client(
        getattr(settings, 'NOVA_USER', 'admin'),
        getattr(settings, 'NOVA_PASSWORD', 'admin'),
        getattr(settings, 'NOVA_TENANT', 'admin'),
        getattr(settings, 'NOVA_AUTH_URL', 'http://localhost:5000/v2.0/'),
    )
