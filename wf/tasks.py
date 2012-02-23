import socket
import time
import logging
from celery.decorators import task
from django.conf import settings

from novaclient.v1_1 import client

from wf.exceptions import TimeoutError 

log = logging.getLogger(__name__)

@task
def deploy_service_domain(domain_name):
    pass

"""
Task that will promote a Windows 2008 server to ADDC
domain_name: name of the to-be-created domain, assumed to end with ".com"
ip: ip address of the server
"""
@task(default_retry_delay=10, max_retries=2, soft_time_limit=10*60, time_limit=20*60)
def promote_addc(domain_name, ip):
    try:

        #wait for the server to boot
        wait_for_server(ip, timeout=5*60)
	# change password. Change hostname to "dc". Server will automatically reboot afterward
        ssh(ip, 'administrator', 'abcDEFG!@#12', 'net user administrator "abcDEFG!@#12" && netdom renamecomputer localhost /NewName:dc /reboot:5 /Force', timeout=30)
	#now it could take as long as 60s before Windows start rebooting process
	time.sleep(60)
	wait_for_server(ip, timeout=2*60)
	# command to promote server to ADDC
        ssh(ip, 'administrator', 'abcDEFG!@#12', 'dcpromo /unattend /InstallDns:yes /dnsOnNetwork:yes /replicaOrNewDomain:domain /newDomain:forest /newDomainDnsName:%s /DomainNetbiosName:%s /CreateDNSDelegation:NO /databasePath:"%systemroot%\NTDS" /logPath:"%systemroot%\NTDS" /sysvolpath:"%systemroot%\SYSVOL" /safeModeAdminPassword:abcDEFG!@#12 /forestLevel:3 /domainLevel:3 /rebootOnCompletion:yes' % (domain_name, domain_name.replace('.com', '')), timeout=2*60)

    except Exception, exc:
        log.exception("Error in the process of promoting %s to ADDC" % (ip, exc))
        deploy_addc.retry(exc=exc)

@task(default_retry_delay=60, max_retries=3)
def create_instance(name, image, flavor, userdata=None, key_name=None, security_groups=[]):
    #log = create_instance.get_logger()
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
    #log = delete_instance.get_logger()
    try:
        log.debug("calling nova_client.servers.delete() with: server = %d" % id)
        return nova_client().servers.delete(server=id)
    except Exception, exc:
        log.exception("Error calling Nova: %s" % exc)
        delete_instance.retry(exc=exc)

def wait_for_server(host, port=22, protocol=socket.SOCK_STREAM, timeout=-1, retry_delay=1):
    #log = wait_for_server.get_logger()
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
    raise TimeoutError(os.strerror(errno.ETIME))

def nova_client():
    return client.Client(
        getattr(settings, 'NOVA_USER', 'admin'),
        getattr(settings, 'NOVA_PASSWORD', 'admin'),
        getattr(settings, 'NOVA_TENANT', 'admin'),
        getattr(settings, 'NOVA_AUTH_URL', 'http://localhost:5000/v2.0/'),
    )



def ssh(host, username, password, cmd, timeout=60):

    def run_ssh(host, username, password, cmd):
        from subprocess import Popen, PIPE
        from os.path import join, abspath, dirname
        remote_cmd = [join(abspath(dirname(__file__)), '..', 'bin', 'remote_command.sh'), host, username, password, cmd]
	log.debug("Running system command %s" % remote_cmd)
	p = Popen(remote_cmd, shell=False, stdout=PIPE, stderr=PIPE)
	log.debug("STDOUT OF REMOTE:\n")
	log.debug(p.stdout.read())
	log.debug("STDERR OF REMOTE:\n")
	log.debug(p.stderr.read())
	if( 0 != p.wait() ):
            raise ReturnCodeNotZeroError ("Process exist with return code %d" % p.poll())

    with_timeout(run_ssh, args=[host, username, password, cmd], seconds=timeout)
            
import errno
import os
import signal

def with_timeout(func, args=[], kwargs={}, seconds=10, error_message=os.strerror(errno.ETIME)):
    def _handle_timeout(signum, frame):
        raise TimeoutError(error_message)

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(seconds)
    try:
        result = func(*args, **kwargs)
    finally:
        signal.alarm(0)
    return result

