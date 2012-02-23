import logging
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
def deploy_service_domain(domain_name):

    addc_admin_pwd = win.new_password()
    exch_admin_pwd = win.new_password()

    #create addc
    addc_ip = timeout.attempt(iaas.create_instance, 
        args=["dc."+domain_name, ADDC_IMG_ID, ADDC_FLAVOR_ID],
	timeout=60, retries=0)

    #create exchange server
    exch_ip = timeout.attempt(iaas.create_instance, 
        args=["mail."+domain_name, EXCH_IMG_ID, EXCH_FLAVOR_ID],
	timeout=60, retries=0)

    #delayed task to promote to ADDC
    promote_addc.delay(domain_name=domain_name, ip=addc_ip, pwd=addc_admin_pwd)
    
    #delayed task to "preconfigured" exchange server (whatever can be done without having to join domain
    exch_pre_join_domain.delay(exch_ip, exch_admin_pwd)
    

"""
Task that will promote a Windows 2008 server to ADDC
domain_name: name of the to-be-created domain, assumed to end with ".com"
ip: ip address of the server
"""
@task(time_limit=120*60)
def promote_addc(domain_name, ip, pwd):

    #wait for server to boot
    win.wait_for_server(ip, timeout=5*60)

    #change default password
    timeout.attempt(win.change_password, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'old_pwd': ADMIN_INI_PWD, 'new_pwd': pwd},
	timeout=15, retries=2)

    # change hostname to "dc"
    timeout.attempt(win.rename_host, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'new_name': 'dc'},
	timeout=60, retries=2)

    # promote it to ADDC. SSH command will return "1" for unknown reason even in case of success
    # Retry will test if previous attempt was successful or not. 
    # However, there should be a delay between retries to give server time to start booting
    timeout.attempt(win.promote_addc, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'domain_name': domain_name},
	timeout=10*60, retries=2, retry_delay=15)


"""
Task that will do all configuration that can be done prior to joinging domain on a Exchange Server 
"""
@task(time_limit=120*60)
def exch_pre_join_domain(ip, pwd):

    #wait for server to boot
    win.wait_for_server(ip, timeout=5*60)

    #change default password
    timeout.attempt(win.change_password, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'old_pwd': ADMIN_INI_PWD, 'new_pwd': pwd},
	timeout=15, retries=2)

    # change hostname to "mail"
    timeout.attempt(win.rename_host, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd, 'new_name': 'mail'},
	timeout=60, retries=2)

    # install IIS, required by exchange 2010
    timeout.attempt(win.install_iis, kwargs={
        'ip': ip, 'username': ADMIN_USER, 'password': pwd},
	timeout=20*60, retries=2)

