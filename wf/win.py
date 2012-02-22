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
    # guarding condition to make it idempotent
    (out, err) = ssh(ip, username, password, 'hostname', timeout=20)
    if re.search("^%s$" % new_name, out, re.M):
        return 

    # Change hostname.  Server will automatically reboot afterward
    ssh(ip, username, password, 'netdom renamecomputer localhost /NewName:%s /reboot:5 /Force', timeout=20)
    #now it'll take a while before Windows start rebooting process
    time.sleep(15)
    wait_for_server(ip, timeout=5*60)


def change_password(ip, username, old_pwd, new_pwd):
    # guarding condition to make it idempotent
    try:
        ssh(ip, username, new_pwd, 'echo ""', timeout=5)
    except:
        ssh(ip, username, old_pwd, 'net user administrator "%s"' % new_pwd, timeout=20)
 

def promote_addc(ip, username, password, domain_name):
    # guarding condition to make it idempotent
    try:
        log.info("Testing if %s is listening on 53(DNS). If so it's a domain controller already" % ip)
        if wait_for_server(host=ip, port=53, timeout=3):
	    return
    except:
        log.info("Not accepting on 53. Moving ahead to promote %s to domain controller" % ip)

    # command to promote server to ADDC
    ssh(ip, username, password, 'dcpromo /unattend /InstallDns:yes /dnsOnNetwork:yes /replicaOrNewDomain:domain /newDomain:forest /newDomainDnsName:%s /DomainNetbiosName:%s /CreateDNSDelegation:NO /databasePath:"%systemroot%\NTDS" /logPath:"%systemroot%\NTDS" /sysvolpath:"%systemroot%\SYSVOL" /safeModeAdminPassword:abcDEFG!@#12 /forestLevel:3 /domainLevel:3 /rebootOnCompletion:yes' % (domain_name, domain_name.replace('.com', '')), timeout=10*60)


def wait_for_server(host, port=22, protocol=socket.SOCK_STREAM, timeout=None, retry_delay=1):
    #log = wait_for_server.get_logger()
    s = socket.socket(socket.AF_INET, protocol)
    s.settimeout(timeout)
    start = time.time()
    while (timeout is None or time.time() < (start + timeout)):
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

"""
timeout in seconds. None - wait indefinitely
"""
def ssh(host, username, password, cmd, timeout=None):

        from subprocess import Popen, PIPE
        from os.path import join, abspath, dirname
        import StringIO

        remote_cmd = [join(abspath(dirname(__file__)), '..', 'bin', 'remote_command.sh'), host, username, password, cmd, '-1' if timeout is None else str(timeout)]

	log.debug("Running system command %s" % remote_cmd)
	p = Popen(remote_cmd, shell=False, stdout=PIPE, stderr=PIPE)
	out = StringIO.StringIO()
	out.write(p.stdout.read())
	err = StringIO.StringIO()
	err.write(p.stderr.read())
	log.debug("STDOUT OF REMOTE:\n%s" % out.getvalue())
	log.debug("STDERR OF REMOTE:\n%s" % err.getvalue())
	if( 0 != p.wait() ):
            raise RemoteCommandError ("Process exist with return code %d" % p.poll())
	return (out.getvalue(), err.getvalue())

"""
timeout in seconds. 0 - wait indefinitely
"""
def with_timeout(func, args=[], kwargs={}, timeout=0, error_message=os.strerror(errno.ETIME)):
    def _handle_timeout(signum, frame):
        raise TimeoutError(error_message)

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(timeout)
    try:
        result = func(*args, **kwargs)
    finally:
        signal.alarm(0)
    return result


"""
timeout in seconds. 0 - wait indefinitely
"""
def attempt(func, args=[], kwargs={}, timeout=0, retries=3):
    while True:
        try:
            return with_timeout(func, args=args, kwargs=kwargs, timeout=timeout)
        except Exception, exc:
	    log.exception(exc)
	    retries -= 1
            if retries < 0: 
	        raise exc
