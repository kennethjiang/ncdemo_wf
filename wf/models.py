import logging
from django.db import models
from django.db import connection


log = logging.getLogger(__name__)


# Create your models here.
class VMInstance(models.Model):
    instance_id = models.CharField(max_length=128)
    hostname = models.CharField(max_length=128)
    internal_ip = models.CharField(max_length=32)
    admin_password = models.CharField(max_length=128)
    server_type = models.IntegerField(default=1)
    company_service_id = models.IntegerField()
    state = models.IntegerField(default=2)
    image_id = models.IntegerField(default=65)
    creation_date = models.DateField(auto_now=True)

    class Meta:
        db_table = 'vm_instances'


class CompanyService(models.Model):
    id = models.IntegerField(primary_key=True)
    service_id = models.IntegerField()
    status = models.IntegerField(default=2)
    admin_url = models.CharField(max_length=1024)

    class Meta:
        db_table = 'company_services'


def new_vminstance(instance_id, ip, admin_pwd, company_service_ids, hostname, service_id):

    sids = []
    #find out from a list of company_service_id which one belong to  this service_id
    cs = CompanyService.objects.filter(id__in=company_service_ids, service_id__in=service_id)
    for c in cs:
	c.admin_url = "https://%s/ecp" % ip
	if c.service_id == 13:
	    c.admin_url = "http://%s/wiki/%s" % (ip,hostname)
	if c.service_id == 15:
	    c.admin_url = "http://%s/wp/%s" % (ip,hostname)
	c.status = 2
	c.save()
        sids.append(c.service_id)
        i = VMInstance.objects.create()
        i.instance_id = instance_id
        i.internal_ip = ip
        i.admin_password = admin_pwd
        i.hostname = hostname
        i.company_service_id = c.id
        i.save()

    log.debug(connection.queries)
    return sids


def change_vminstance_status(ip, state):
  for i in VMInstance.objects.filter(internal_ip=ip):
    if i is None:
        return
    i.state = state
    i.save()
    cs = CompanyService.objects.get(id=i.company_service_id)
    cs.status = state
    cs.save()
    log.debug(connection.queries)

def change_service_status(company_service_ids, state):
    for i in VMInstance.objects.filter(company_service_id__in = company_service_ids):
        i.state = state
	i.save()

    for cs in CompanyService.objects.filter(id__in = company_service_ids):
        cs.status = state
	cs.save()
