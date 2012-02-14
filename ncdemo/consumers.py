from kombu.messaging import Consumer
from kombu.mixins import ConsumerMixin
from kombu import Connection, Exchange, Queue
from pprint import pformat


def deploy_project(body, message):
        print("Got task: %r" % (body, ))
        message.ack()

AMQP_EXCH = 'ncdemo_orchestration'
AMQP_QUEUES = {
'deploy_project': deploy_project,
}

class Consumers(ConsumerMixin):

    def __init__(self, connection):
        self.connection = connection

    def on_task(self, body, message):
        print("Got task: %r" % (body, ))
        message.ack()

    def get_consumers(self, Consumer, default_channel):
        exchange = Exchange(AMQP_EXCH, type="direct")
	return [Consumer(queues=[Queue(k, exchange, k)], callbacks=[c]) for k,c in AMQP_QUEUES.items()]


def start_all_consumers(amqp_url='amqp://guest:guest@127.0.0.1:5672/'):

    with Connection(amqp_url) as connection:
	Consumers(connection).run()
