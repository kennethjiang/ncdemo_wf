import socket
import time
import re
import logging
import errno
import os
import signal
from django.conf import settings

from wf.exceptions import TimeoutError, RemoteCommandError

log = logging.getLogger(__name__)

def rename_host(ip, username, password, new_name):
    # Change hostname.  Server will automatically reboot afterward
    ssh(ip, username, password, 'netdom renamecomputer localhost /NewName:%s /reboot:5 /Force', timeout=60)
    #now it'll take a while before Windows start rebooting process
    time.sleep(15)
    wait_for_server(ip, timeout=5*60)
    # now verify if hostname was changed successfully
    (out, err) = ssh(ip, username, password, 'hostname', timeout=60)
    if ! re.search("^%s$" % new_name, out, re.M):
        raise RemoteCommandError("command failed on host: %s")

def change_password(ip, username, old_pwd, new_pwd):
    ssh(ip, username, old_pwd, 'net user administrator "%s"' % new_pwd, timeout=60)
    time.sleep(15) 
    # now verify if hostname was changed successfully    (out, err) = ssh(ip, username, password, 'hostname', timeout=15)    if ! re.search("^%s$" % new_name, out, re.M):        raise RemoteCommandError("command failed on host: %s")
 
    ssh(ip, username, password, 'net user administrator "abcDEFG!@#12" && netdom renamecomputer localhost /NewName:dc /reboot:5 /Force', timeout=30)
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
        import StringIO

        remote_cmd = [join(abspath(dirname(__file__)), '..', 'bin', 'remote_command.sh'), host, username, password, cmd]

	log.debug("Running system command %s" % remote_cmd)
	p = Popen(remote_cmd, shell=False, stdout=PIPE, stderr=PIPE)
	out = StringIO.StringIO()
	out.write(p.stdout.read())
	err = StringIO.StringIO()
	err.write(p.stderr.read())
	log.debug("STDOUT OF REMOTE:\n%s" % out)
	log.debug("STDERR OF REMOTE:\n%s" % err)
	if( 0 != p.wait() ):
            raise RemoteCommandError ("Process exist with return code %d" % p.poll())
	return (out.getvalue(), err.getvalue())

    with_timeout(run_ssh, args=[host, username, password, cmd], seconds=timeout)
            

def timeout(func, args=[], kwargs={}, timeout=0, error_message=os.strerror(errno.ETIME)):
    def _handle_timeout(signum, frame):
        raise TimeoutError(error_message)

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(timeout)
    try:
        result = func(*args, **kwargs)
    finally:
        signal.alarm(0)
    return result

def attempt(func, args=[], kwargs={}, timeout=0, retry=3):
    while (--retry >= 0):
        try:
            return timeout(func, args=args, kwargs=kwargs, timeout=timeout)
        except: Exception, exc
	    log.exception(exc)
            raise exc
       
