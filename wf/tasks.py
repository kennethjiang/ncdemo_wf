import logging
from celery.contrib import rdb
from celery.decorators import task
from django.conf import settings

import timeout 
import iaas
import win

log = logging.getLogger(__name__)

ADDC_IMG_ID = getattr(settings, 'ADDC_IMAGE_ID')
EXCH_IMG_ID = getattr(settings, 'EXCH_IMAGE_ID')
ADDC_FLAVOR_ID = getattr(settings, 'ADDC_FLAVOR_ID')
EXCH_FLAVOR_ID = getattr(settings, 'EXCH_FLAVOR_ID')
ADMIN_USER = 'administrator'
ADMIN_INI_PWD = getattr(settings, 'ADMIN_INI_PASSWORD')

"""
Task that will deploy a Windows domain, including a domain controller and an
exchange server.
domain_name: name of the to-be-created domain, assumed to end with ".com"
"""
@task(time_limit=120*60)
def deploy_service_domain(domain_name, services_requested):

    #added domain name to host name as Windows doesn't allow 2 servers to have the same host name on the local network (otherwise adding server to domain will fail)
    addc_hostname = "dc-"+domain_name.replace('.com', '')
    exch_hostname = "mail-"+domain_name.replace('.com', '')

    addc_admin_pwd = "abcDEFG!@#12" #win.new_password()
    exch_admin_pwd = "abcDEFG!@#12" #win.new_password()

    #create addc
    addc_ip = timeout.attempt(iaas.create_instance, 
        args=[addc_hostname, ADDC_IMG_ID, ADDC_FLAVOR_ID],
	timeout=60, retries=0)

    #create exchange server
    exch_ip = timeout.attempt(iaas.create_instance, 
        args=[exch_hostname, EXCH_IMG_ID, EXCH_FLAVOR_ID],
	timeout=60, retries=0)

    #delayed task to promote to ADDC
    promote_addc(domain_name=domain_name, ip=addc_ip, pwd=addc_admin_pwd)
    
    deploy_exchange_server.delay(ip=exch_ip, pwd=exch_admin_pwd, domain=domain_name, addc_ip=addc_ip, domain_pwd=addc_admin_pwd)
    

"""
Task that will promote a Windows 2008 server to ADDC
domain_name: name of the to-be-created domain, assumed to end with ".com"
ip: ip address of the server
"""
@task(time_limit=120*60)
def promote_addc(domain_name, ip, pwd):

    #wait for server to boot
    win.wait_for_server(ip, timeout=20*60)

    #change default password
    timeout.attempt(win.change_password, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'old_pwd': ADMIN_INI_PWD, 'new_pwd': pwd},
	timeout=60, retries=5)

    # change hostname to "dc"
    timeout.attempt(win.rename_host, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'new_name': 'dc-'+domain_name.replace('.com', '')},
	timeout=2*60, retries=5)

    # promote it to ADDC. SSH command will return "1" for unknown reason even in case of success
    # Retry will test if previous attempt was successful or not. 
    # However, there should be a delay between retries to give server time to start booting
    timeout.attempt(win.promote_addc, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'domain_name': domain_name},
	timeout=10*60, retries=2, retry_delay=15)


"""
Task that will perform all configuration needed to deploy an Exchange Server
"""
@task(time_limit=120*60)
def deploy_exchange_server(ip, pwd, domain, addc_ip, domain_pwd):

    #Steps of  "preconfiguring" exchange server (whatever can be done without having to join domain
    #wait for server to boot
    win.wait_for_server(ip, timeout=20*60)

    #change default password
    timeout.attempt(win.change_password, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'old_pwd': ADMIN_INI_PWD, 'new_pwd': pwd},
	timeout=60, retries=5)

    # change hostname to "mail-domain"
    timeout.attempt(win.rename_host, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'new_name': 'mail-'+domain.replace('.com', '')},
	timeout=2*60, retries=5)

    
    # wait for the ADDC to be available
    log.info("Testing if %s is listening on 53(DNS). If so it's a domain controller already" % addc_ip)
    win.wait_for_server(host=addc_ip, port=53)
    log.info("Connected to %s on 53(DNS). ADDC is live." % ip)

    # now kick off steps that can be done only after domain controller is available
    domain_user = '%s\%s' % (domain, ADMIN_USER)

    #change dns server to point to domain controller
    timeout.attempt(win.change_dnsserver, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'dnsserver': addc_ip},
	timeout=60, retries=5)

    #join this server to domain
    timeout.attempt(win.join_domain, kwargs={
        'ip': ip, 
	'local_admin': ADMIN_USER,
	'local_password': pwd,
	'domain_name': domain,
	'domain_admin': domain_user,
	'domain_password': domain_pwd},
	timeout=60, retries=1)

    # install IIS, required by exchange 2010
    timeout.attempt(win.install_iis, kwargs={
        'ip': ip, 'username': domain_user, 'password': domain_pwd},
	timeout=45*60, retries=2)

    # Set TcpPortSharing service to auto_start
    timeout.attempt(win.tcpportsharing_auto, kwargs={
        'ip': ip, 'username': domain_user, 'password': domain_pwd},
	timeout=60, retries=2)

    # now the longest, if not hardest part, setting up Exchange Server
    timeout.attempt(win.install_exchange_server, kwargs={
        'ip': ip, 'username': domain_user, 'password': domain_pwd},
	timeout=90*60, retries=0)


@task
def reset_testing_env():
    iaas.reset_testing_env((ADDC_IMG_ID, EXCH_IMG_ID))
