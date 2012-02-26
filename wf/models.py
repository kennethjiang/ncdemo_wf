from django.db import models

# Create your models here.
class VMInstance(models.Model):
    instance_id = models.CharField(max_length=128)
    internal_ip = models.CharField(max_length=32)
    admin_password = models.CharField(max_length=128)

    class Meta:
        db_table = 'vm_instances'


def new_vminstance(instance_id, ip, admin_pwd):
    i = VMInstance()
    i.instance_id = instance_id
    i.internal_ip = ip
    i.admin_password = admin_pwd
    i.save()
    return i
