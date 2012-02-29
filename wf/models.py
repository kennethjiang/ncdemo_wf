import logging
from django.db import models
from django.db import connection


log = logging.getLogger(__name__)


# Create your models here.
class VMInstance(models.Model):
    instance_id = models.CharField(max_length=128)
    internal_ip = models.CharField(max_length=32)
    admin_password = models.CharField(max_length=128)
    server_type = models.IntegerField(default=1)
    company_service_id = models.IntegerField()
    state = models.IntegerField(default=2)
    image_id = models.IntegerField(default=65)

    class Meta:
        db_table = 'vm_instances'


class CompanyService(models.Model):
    id = models.IntegerField(primary_key=True)
    service_id = models.IntegerField()
    status = models.IntegerField(default=2)
    admin_url = models.CharField(max_length=1024)

    class Meta:
        db_table = 'company_services'


def new_vminstance(instance_id, ip, admin_pwd, company_service_ids, service_id):
    (i, is_new) = VMInstance.objects.get_or_create(internal_ip=ip)
    i.instance_id = instance_id
    i.internal_ip = ip
    i.admin_password = admin_pwd

    #find out from a list of company_service_id which one belong to  this service_id
    cs = CompanyService.objects.filter(id__in=company_service_ids, service_id=service_id)
    if len(cs) > 0:
        c = cs[0]
	c.admin_url = "https://%s/ecp" % ip
	c.status = 2
	c.save()
        i.company_service_id = c.id

    i.save()
    log.debug(connection.queries)
    return i


def change_vminstance_status(ip, state):
    i = VMInstance.objects.get(internal_ip=ip)
    if i is None:
        return
    i.state = state
    i.save()
    cs = CompanyService.objects.get(id=i.i.company_service_id)
    cs.status = state
    cs.save()
    log.debug(connection.queries)

