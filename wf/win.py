import socket
import time
import re
import logging
import os
import errno

from wf.timeout import TimeoutError, attempt

log = logging.getLogger(__name__)


def rename_host(ip, username, password, new_name):
    
    wait_for_server(ip)

    # guarding condition to make it idempotent
    log.info("Checking if %s already has the desired name %s" % (ip, new_name))
    (out, err) = ssh(ip, username, password, 'hostname', timeout=20)
    if re.search("^{hostname}\s*$".format(hostname=new_name), out, re.M):
        log.info("%s already has the desired name %s. No more action needed" % (ip, new_name))
        return 

    log.info("Changing hostname of %s to %s.  Server will automatically reboot afterward" % (ip, new_name))
    ssh(ip, username, password, 'netdom renamecomputer localhost /NewName:%s /reboot:5 /Force' % new_name, timeout=20)
    wait_for_reboot(ip)


def change_password(ip, username, old_pwd, new_pwd):
    # guarding condition to make it idempotent
    try:
        log.info("Checking if administrator of %s already has new password %s" % (ip, new_pwd))
        ssh(ip, username, new_pwd, 'echo ""', timeout=5)
	log.info("administrator of %s already has new password %s. No more action needed" % (ip, new_pwd))
    except:
        log.info("Changing amdin password of %s from %s to %s" % (ip, old_pwd, new_pwd))
        ssh(ip, username, old_pwd, 'net user administrator "%s"' % new_pwd, timeout=60)
 

def promote_addc(ip, username, password, domain_name):

    wait_for_server(ip)
    # guarding condition to make it idempotent
    try:
        log.info("Testing if %s is listening on 53(DNS). If so it's a domain controller already" % ip)
        if wait_for_server(host=ip, port=53, timeout=3):
	    log.info("%s is listening on 53(DNS). It's a domain controller already. No more action needed" % ip)
	    return
    except:
        log.info("Not accepting on 53. Moving ahead to promote %s to domain controller" % ip)

    # command to promote server to ADDC
    ssh(ip, username, password, 'dcpromo /unattend /InstallDns:yes /dnsOnNetwork:yes /replicaOrNewDomain:domain /newDomain:forest /newDomainDnsName:{domain} /DomainNetbiosName:{netbios} /CreateDNSDelegation:NO /databasePath:"%systemroot%\NTDS" /logPath:"%systemroot%\NTDS" /sysvolpath:"%systemroot%\SYSVOL" /safeModeAdminPassword:abcDEFG!@#12 /forestLevel:3 /domainLevel:3 /rebootOnCompletion:yes'.format(domain=domain_name, netbios=domain_name.replace('.com', '')), timeout=10*60)
    wait_for_reboot(ip)


def change_dnsserver(ip, username, password, dnsserver):
    
    wait_for_server(ip)

    # guarding condition to make it idempotent
    log.info("Checking if %s is already configured with the desired DNS server %s" % (ip, dnsserver))
    if desired_dnsserver_set(ip, username, password, dnsserver):
        log.info(" %s is already configured with the desired DNS server %s. No more action needed" % (ip, dnsserver))
        return 

    log.info("Changing %s's DNS server to %s" % (ip, dnsserver))
    ssh(ip, username, password, 'netsh interface ip set dns name="Local Area Connection" source=static addr=%s' % dnsserver, timeout=20)

    log.info("DNS change command would return 0 even when it failed. So I'd better verify it...")
    if not desired_dnsserver_set(ip, username, password, dnsserver):
        raise RemoteCommandError ("Yuck! I was told dns server has been changed to %s, it was actually not!" % dnsserver)


def desired_dnsserver_set(ip, username, password, dnsserver):
    (out, err) = ssh(ip, username, password, 'netsh interface ip show dnsservers name="Local Area Connection"', timeout=20)
    if re.search("DNS.*{dns}\s*$".format(dns=dnsserver), out, re.M):
        return True

    return False


def install_iis(ip, username, password):

    wait_for_server(ip)
    # guarding condition to make it idempotent
    try:
        log.info("Testing if %s is listening on 80. If so it already has IIS running" % ip)
        if wait_for_server(host=ip, port=80, timeout=3):
	    return
    except:
        log.info("Not accepting on 80. Moving ahead to install IIS on %s" % ip)

    # command to install IIS
    ssh(ip, username, password, 'PowerShell -NoExit -Command " & {Servermanagercmd -i rsat-adds,Web-Server,Web-Basic-Auth,Web-Windows-Auth,Web-Metabase,Web-Net-Ext,Web-Lgcy-Mgmt-Console,WAS-Process-Model,RSAT-Web-Server,Web-ISAPI-Ext,Web-Digest-Auth,Web-Dyn-Compression,NET-HTTP-Activation,RPC-Over-HTTP-Proxy -Restart}', timeout=20*60)
    wait_for_reboot(ip)


def tcpportsharing_auto(ip, username, password):
    wait_for_server(ip)

    # guarding condition to make it idempotent
    log.info("Checking if NetTcpPortSharing is already set to auto on %s" % ip)
    (out, err) = ssh(ip, username, password, 'sc qc NetTcpPortSharing', timeout=20)
    if re.search("START_TYPE.*AUTO_START\s*$", out, re.M):
        log.info("NetTcpPortSharing is already set to auto on %s. No more action needed" % ip)
        return 
    log.info("setting NetTcpPortSharing service to auto on %s" % ip)
    ssh(ip, username, password, 'sc config NetTcpPortSharing start= auto')


def join_domain(ip, local_admin, local_password, domain_name, domain_admin, domain_password):
    wait_for_server(ip)

    # guarding condition to make it idempotent
    try:
        log.info("Checking if %s is already in domain %s by trying to log into with domain administrator" % (ip, domain_name))
        ssh(ip, domain_admin, domain_password, 'echo ""', timeout=5)
	log.info("%s is already in domain %s. No more action needed" % (ip, domain_name))
	return
    except:
        log.info("Running command to join %s to domain %s" % (ip, domain_name))
        ssh(ip, local_admin, local_password, 'netdom join localhost /domain:"{domain}" /userd:"{d_adm}" /passwordd:"{d_pwd}" /usero:"{l_adm}" /passwordo:"{l_pwd}" /reboot:1'.format(domain=domain_name, d_adm=domain_admin, d_pwd=domain_password, l_adm=local_admin, l_pwd=local_password), timeout=20)
	wait_for_reboot(ip)


def install_exchange_server(ip, username, password):

    wait_for_server(ip)
    # guarding condition to make it idempotent
    try:
        log.info("Testing if %s is listening on 587. If so it already has Exchange Server running" % ip)
        if wait_for_server(host=ip, port=587, timeout=5):
	    return
    except:
        log.info("Not accepting on 587. Moving ahead to install Exchange Server on %s" % ip)

    # command to install Exchange Server
    ssh(ip, username, password, 'c:\exchange2010_64\Setup.com /mode:Install /roles:ClientAccess,HubTransport,Mailbox,ManagementTools /OrganizationName:LouisTeam', timeout=75*60)
    wait_for_reboot(ip)


def wait_for_server(host, port=22, protocol=socket.SOCK_STREAM, timeout=None, retry_delay=1):
    start = time.time()
    while (timeout is None or time.time() < (start + timeout)):
        try:
	    log.debug("trying to connect to %s:%d" % (host, port))
            s = socket.socket(socket.AF_INET, protocol)
            s.settimeout(timeout)
            s.connect((host, port))
	    log.debug("connected! %s is alive!" % host)
            s.shutdown(2)
	    return True
        except Exception, exc:
	    log.debug("Unable to connect. Error: %s" % exc)
            time.sleep(retry_delay)
    raise TimeoutError(os.strerror(errno.ETIME))


def wait_for_reboot(ip):
    log.info("Sleeping for 15 seconds because it'll take a while before Windows start rebooting process")
    time.sleep(15)
    wait_for_server(ip, timeout=5*60)


"""
timeout in seconds. None - wait indefinitely
"""
def ssh(host, username, password, cmd, timeout=None):

        from subprocess import Popen, PIPE
        from os.path import join, abspath, dirname
        import StringIO

        remote_cmd = [join(abspath(dirname(__file__)), '..', 'bin', 'remote_command.sh'), host, username, password, cmd, '-1' if timeout is None else str(timeout)]

	log.info("Running system command %s" % remote_cmd)
	p = Popen(remote_cmd, shell=False, stdout=PIPE, stderr=PIPE)
	ret = p.wait()
	out = StringIO.StringIO()
	out.write(p.stdout.read())
	err = StringIO.StringIO()
	err.write(p.stderr.read())
	log.debug("STDOUT OF REMOTE:\n%s" % out.getvalue())
	log.debug("STDERR OF REMOTE:\n%s" % err.getvalue())
	if( 0 != ret ):
            raise RemoteCommandError ("Process exist with return code %d" % ret)
	return (out.getvalue(), err.getvalue())


def new_password():
    import random
    import string

    def random_string(charset, length):
        return [random.choice(charset) for x in range(length)]

    l = random_string(string.letters, 4) + random_string(string.digits, 3) + random_string("!#$%+,-.:<=>@^_~", 3)
    random.shuffle(l)
    return ''.join(l)


class RemoteCommandError(Exception):
    pass

